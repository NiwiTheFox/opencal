"""An opened EDC15 flash file: identity, codeblocks, maps, edits, checksums."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import numpy as np

from . import checksum as cks
from . import maps as M

FLASH_SIZE = 0x80000
BANK_BASES = (0x50000, 0x60000, 0x70000)   # codeblock data pages of a 512 KB file
EMPTY = 0xC3


class EcuFileError(Exception):
    pass


class ChecksumLayoutUnknown(EcuFileError):
    """Raised instead of guessing which checksum algorithm the ECU uses."""


@dataclass
class Codeblock:
    base: int                  # page base (0x50000, 0x60000, 0x70000)
    id: int | None             # codeblock id the ECU compares with its coding
    populated: bool
    gearbox: str = ""          # "manual" / "automatic" from the info string
    id_address: int | None = None

    @property
    def start(self) -> int:
        return self.base - 0x4000

    @property
    def end(self) -> int:
        return self.base + 0xC000

    def contains(self, addr: int) -> bool:
        return self.start <= addr < self.end


@dataclass
class Edit:
    address: int
    before: bytes
    after: bytes
    note: str


@dataclass
class FileInfo:
    part_number: str = ""
    software: str = ""
    bosch_number: str = ""
    description: str = ""
    ecu_type: str = ""
    size: int = 0


def _ascii(buf, a, n) -> str:
    return bytes(buf[a:a + n]).decode("ascii", "replace").strip()


def read_info(buf) -> FileInfo:
    info = FileInfo(size=len(buf))
    raw = bytes(buf)
    i = raw.rfind(b"EDC  ")
    if i > 20:
        info.part_number = _ascii(raw, i - 20, 12)
        info.description = _ascii(raw, i - 8, 12)
        info.software = _ascii(raw, i + 5, 8).replace(" ", "")
    m = re.search(rb"0281\d{6}", raw)
    if m:
        info.bosch_number = m.group().decode()
    if len(raw) == FLASH_SIZE:
        info.ecu_type = "EDC15P" if b"V4.1" in raw else "EDC15"
    elif len(raw) == 0x40000:
        info.ecu_type = "EDC15V (256 KB)"
    else:
        info.ecu_type = f"unknown ({len(raw)} bytes)"
    return info


def find_codeblocks(buf) -> list[Codeblock]:
    out = []
    if len(buf) != FLASH_SIZE:
        return out
    for base in BANK_BASES:
        populated = bytes(buf[base + 8:base + 12]) == b"V4.1"
        cb = Codeblock(base, None, populated)
        if populated:
            ptr = M.u16(buf, base + 0x1002) + base
            if base <= ptr < base + 0x10000 - 1:
                cid = M.u16(buf, ptr)
                if cid < 0x100:
                    cb.id, cb.id_address = cid, ptr
            seg = bytes(buf[cb.start:cb.end])
            if b"EDC  AG" in seg:
                cb.gearbox = "automatic"
            elif b"EDC  SG" in seg:
                cb.gearbox = "manual"
        out.append(cb)
    return out


class EcuFile:
    def __init__(self, data: bytes | bytearray, path: str | None = None):
        if len(data) not in (FLASH_SIZE, 0x40000):
            raise EcuFileError(f"Not an EDC15 flash: {len(data)} bytes (expected 512 KB)")
        self.buf = bytearray(data)
        self.original = bytes(data)
        self.path = path
        self.history: list[Edit] = []
        self.redo_stack: list[Edit] = []
        # Locked from the file as loaded; None = the original does not fully
        # verify under any known layout, so correcting needs a user decision.
        self.checksum_layout: str | None = cks.strict_layout(self.buf)
        self.listeners: list = []
        self.rescan()

    # ----------------------------------------------------------- loading --
    @classmethod
    def load(cls, path: str) -> "EcuFile":
        with open(path, "rb") as f:
            return cls(f.read(), path)

    @property
    def name(self) -> str:
        return os.path.basename(self.path) if self.path else "untitled.bin"

    def rescan(self) -> None:
        self.info = read_info(self.buf)
        self.codeblocks = find_codeblocks(self.buf)
        start = 0x40000 if len(self.buf) == FLASH_SIZE else 0x20000
        self.maps = M.scan(self.buf, start, len(self.buf))
        bank_ids = {cb.base: cb.id for cb in self.codeblocks if cb.populated}
        M.identify(self.buf, self.maps, bank_ids)
        self._by_key = {m.key: m for m in self.maps}

    # ------------------------------------------------------------ queries --
    def map(self, key: str) -> M.Map | None:
        return self._by_key.get(key.upper().rjust(5, "0"))

    def find(self, kind: str, bank: int | None = None) -> list[M.Map]:
        return [m for m in self.maps if m.kind == kind and (bank is None or m.bank == bank)]

    def first(self, kind: str, bank: int | None = None) -> M.Map | None:
        r = self.find(kind, bank)
        return r[0] if r else None

    @property
    def populated_banks(self) -> list[Codeblock]:
        return [cb for cb in self.codeblocks if cb.populated]

    @property
    def active_bank(self) -> int:
        """The bank tools edit by default: the original calibration's bank."""
        banks = self.populated_banks
        if not banks:
            return 0x70000
        orig = [cb for cb in banks if bytes(self.original[cb.base + 8:cb.base + 12]) == b"V4.1"]
        return (orig or banks)[-1].base

    def checksum(self) -> cks.ChecksumReport | None:
        if self.checksum_layout:
            return cks.verify(self.buf, self.checksum_layout)
        return cks.detect(self.buf)

    @property
    def checksum_uncertain(self) -> bool:
        return self.checksum_layout is None and len(self.buf) == FLASH_SIZE

    def set_checksum_layout(self, layout: str) -> None:
        if layout not in cks.LAYOUTS:
            raise EcuFileError(f"Unknown checksum layout {layout}")
        self.checksum_layout = layout

    @property
    def dirty(self) -> bool:
        return bytes(self.buf) != self.original

    # -------------------------------------------------------------- edits --
    def write(self, address: int, data: bytes, note: str = "") -> None:
        data = bytes(data)
        before = bytes(self.buf[address:address + len(data)])
        if before == data:
            return
        self.buf[address:address + len(data)] = data
        self.history.append(Edit(address, before, data, note))
        self.redo_stack.clear()
        self._notify()

    def begin(self):
        return _Transaction(self)

    def write_map(self, m: M.Map, values, note: str | None = None) -> None:
        raw = m.to_raw(values)
        data = (np.asarray(raw, np.int64).reshape(m.rows, m.cols) & 0xFFFF).astype("<u2").tobytes()
        self.write(m.address, data, note or f"{m.label()} edited")

    def write_map_raw(self, m: M.Map, raw, note: str | None = None) -> None:
        data = (np.asarray(raw, np.int64).reshape(m.rows, m.cols) & 0xFFFF).astype("<u2").tobytes()
        self.write(m.address, data, note or f"{m.label()} edited")

    def write_axis(self, ax: M.Axis, values, note: str = "axis edited") -> None:
        raw = ax.to_raw(values)
        self.write(ax.address, (raw & 0xFFFF).astype("<u2").tobytes(), note)

    def undo(self) -> Edit | None:
        if not self.history:
            return None
        e = self.history.pop()
        self.buf[e.address:e.address + len(e.before)] = e.before
        self.redo_stack.append(e)
        self._notify()
        return e

    def redo(self) -> Edit | None:
        if not self.redo_stack:
            return None
        e = self.redo_stack.pop()
        self.buf[e.address:e.address + len(e.after)] = e.after
        self.history.append(e)
        self._notify()
        return e

    def restore_map(self, m: M.Map) -> None:
        self.write(m.address, self.original[m.address:m.end], f"{m.label()} restored to original")

    def _notify(self):
        for fn in list(self.listeners):
            fn(self)

    # ------------------------------------------------------------- saving --
    def fix_checksums(self) -> cks.ChecksumReport | None:
        if self.checksum_layout is None:
            raise ChecksumLayoutUnknown(
                "The checksums of this file did not verify when it was opened, so the layout the ECU uses "
                "is uncertain. Choose a layout (Actions > Checksums) before correcting.")
        before = bytes(self.buf)
        rep = cks.fix(self.buf, self.checksum_layout)
        if bytes(self.buf) != before:
            after = bytes(self.buf)
            self.buf[:] = before
            # record each changed checksum word as an edit so undo works
            with self.begin() as tx:
                for b in (rep.blocks if rep else []):
                    a = b.store
                    tx.write(a, after[a:a + 4], "checksum corrected")
        return rep

    def save(self, path: str | None = None, fix_checksums: bool = True) -> cks.ChecksumReport | None:
        rep = self.fix_checksums() if fix_checksums else self.checksum()
        if fix_checksums and rep is not None and not rep.all_ok:
            raise EcuFileError("Checksums could not be fixed, so nothing was saved.")
        path = path or self.path
        if not path:
            raise EcuFileError("No file name")
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(self.buf)
        os.replace(tmp, path)
        self.path = path
        return rep

    # ------------------------------------------------------------ compare --
    def changed_maps(self, reference: bytes | None = None) -> list[tuple[M.Map, float]]:
        """Maps whose data differ from ``reference`` (default: original)."""
        ref = reference if reference is not None else self.original
        out = []
        for m in self.maps:
            a = bytes(self.buf[m.address:m.end])
            b = bytes(ref[m.address:m.end])
            if a != b:
                va = m.values(self.buf)
                vb = m.values(ref)
                with np.errstate(divide="ignore", invalid="ignore"):
                    pct = np.where(vb != 0, (va - vb) / np.abs(vb) * 100, 0)
                out.append((m, float(np.max(np.abs(pct))) if pct.size else 0.0))
        return out

    def diff_ranges(self, reference: bytes | None = None) -> list[tuple[int, int]]:
        ref = reference if reference is not None else self.original
        a = np.frombuffer(bytes(self.buf), np.uint8)
        b = np.frombuffer(bytes(ref[:len(a)]), np.uint8)
        d = np.flatnonzero(a != b)
        if d.size == 0:
            return []
        out = []
        s = p = int(d[0])
        for x in d[1:]:
            x = int(x)
            if x > p + 16:
                out.append((s, p + 1))
                s = x
            p = x
        out.append((s, p + 1))
        return out


class _Transaction:
    """Group several writes into one undo step."""

    def __init__(self, f: EcuFile):
        self.f = f
        self.edits: list[Edit] = []

    def write(self, address, data, note=""):
        data = bytes(data)
        before = bytes(self.f.buf[address:address + len(data)])
        if before != data:
            self.f.buf[address:address + len(data)] = data
            self.edits.append(Edit(address, before, data, note))

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is not None:
            for e in reversed(self.edits):
                self.f.buf[e.address:e.address + len(e.before)] = e.before
            return False
        if not self.edits:
            return False
        lo = min(e.address for e in self.edits)
        hi = max(e.address + len(e.after) for e in self.edits)
        after = bytes(self.f.buf[lo:hi])
        tmp = bytearray(after)
        for e in reversed(self.edits):
            tmp[e.address - lo:e.address - lo + len(e.before)] = e.before
        note = self.edits[0].note if len({e.note for e in self.edits}) == 1 else f"{len(self.edits)} changes"
        self.f.history.append(Edit(lo, bytes(tmp), after, note))
        self.f.redo_stack.clear()
        self.f._notify()
        return False
