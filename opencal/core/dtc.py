"""Fault-code (DTC) switching on an EcuFile, using the ported classic DTC engine.

Two record formats exist:

* classic: one 5-byte monitoring record per code and codeblock;
* fault path (older "compact" software): a path of several 6-byte segments
  (5 data bytes + padding) shared by up to eight codes.

Disabling writes the neutral record ``FF FF 00 00 00`` into every segment.
Enabling restores the exact original bytes; when the original was already
disabled it copies an enabled twin with the same segment layout.
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

    @property
    def shared_with(self) -> list[int]:
        """Other codes switched together with this one (shared fault paths)."""
        out = set()
        for r in self.records:
            out.update(c for c in r.get("path_codes", []) if c != self.vag_code)
        return sorted(out)


def _segments(r) -> list[int]:
    return r.get("segments") or [r["address"]]


def _read(buf, segs) -> bytes:
    return b"".join(bytes(buf[a:a + 5]) for a in segs)


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
    done: set[int] = set()
    with f.begin() as tx:
        for code in vag_codes:
            g = gs.get(code)
            if g is None:
                continue
            for r in g.records:
                segs = _segments(r)
                if r["address"] in done:          # a shared path already handled
                    continue
                cur = _read(f.buf, segs)
                off = DISABLED * len(segs)
                if not enable:
                    if cur != off:
                        for a in segs:
                            tx.write(a, DISABLED, f"DTC {g.code} / {code} disabled")
                        changed += 1
                    done.add(r["address"])
                    continue
                if cur != off:
                    continue
                orig = _read(f.original, segs)
                if orig == off:
                    twin = next((t for t in g.records if len(_segments(t)) == len(segs)
                                 and _read(f.buf, _segments(t)) != DISABLED * len(segs)), None)
                    if twin is None:
                        raise EcuFileError(f"{g.code}: no stock record to restore from (disabled in the original too).")
                    orig = _read(f.buf, _segments(twin))
                for i, a in enumerate(segs):
                    tx.write(a, orig[i * 5:i * 5 + 5], f"DTC {g.code} / {code} restored")
                changed += 1
                done.add(r["address"])
    return changed
