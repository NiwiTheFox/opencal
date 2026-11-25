"""Fault-code (DTC) switching on an EcuFile, using the ported classic DTC engine.

Disabling writes the neutral record ``FF FF 00 00 00`` in every codeblock.
Enabling restores the exact original bytes; when the original was already
disabled it copies an enabled twin from another bank of the same software.
"""
from __future__ import annotations

from dataclasses import dataclass

from .ecufile import EcuFile, EcuFileError

DISABLED = bytes.fromhex("ffff000000")


@dataclass
class DtcGroup:
    vag_code: int
    code: str
    description: str
    system: str
    records: list
    enabled: int
    total: int

    @property
    def state(self) -> str:
        if self.enabled == self.total:
            return "Enabled"
        if self.enabled == 0:
            return "Disabled"
        return "Mixed"


def groups(f: EcuFile) -> list[DtcGroup]:
    from ..legacy import edc15
    try:
        recs = edc15.dtc_records(bytes(f.buf))
    except ValueError as e:
        raise EcuFileError(f"DTC disable is not available for this file: {e}")
    by: dict[int, DtcGroup] = {}
    for r in recs:
        g = by.get(r["vag_code"])
        if g is None:
            g = by[r["vag_code"]] = DtcGroup(r["vag_code"], r["code"], r["description"], r["system"], [], 0, 0)
        g.records.append(r)
        g.total += 1
        g.enabled += 1 if r["enabled"] else 0
    return sorted(by.values(), key=lambda g: (g.system, g.code))


def set_enabled(f: EcuFile, vag_codes: list[int], enable: bool) -> int:
    """Switch the given codes in every bank. Returns records changed."""
    gs = {g.vag_code: g for g in groups(f)}
    changed = 0
    with f.begin() as tx:
        for code in vag_codes:
            g = gs.get(code)
            if g is None:
                continue
            for r in g.records:
                a = r["address"]
                if not enable:
                    if r["enabled"]:
                        tx.write(a, DISABLED, f"DTC {g.code} / {code} disabled")
                        changed += 1
                    continue
                if r["enabled"]:
                    continue
                orig = bytes(f.original[a:a + 5])
                if orig != DISABLED:
                    tx.write(a, orig, f"DTC {g.code} / {code} restored")
                    changed += 1
                    continue
                twin = next((t for t in g.records if t["enabled"]), None)
                if twin is None:
                    raise EcuFileError(f"{g.code}: no stock record to restore from (disabled in the original too).")
                tx.write(a, bytes(f.buf[twin["address"]:twin["address"] + 5]), f"DTC {g.code} / {code} restored")
                changed += 1
    return changed
