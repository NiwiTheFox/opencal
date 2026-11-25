"""Bosch EDC15P/V (VAG TDI v4.1) flash checksums.

Three layouts are known for 512 KB EDC15P/V files:

* ``tdi41``      - 11 blocks, fixed boundaries, seeds chained per block.
* ``tdi41v2``    - 7 blocks, variant layout used by some later files.
* ``tdi41_2002`` - 2002+ files: two code checksums plus three per
                   calibration bank, located by the ``V4.1`` marker.

The arithmetic follows the algorithm published with the freeware VAG EDC15P
Suite (MTX Electronics, 2007-2012). It is reimplemented here in Python.
"""
from __future__ import annotations

from dataclasses import dataclass, field

M16 = 0xFFFF


def _w(buf, a: int) -> int:
    return buf[a] | (buf[a + 1] << 8)


def _rd32(buf, a: int) -> int:
    return buf[a] | (buf[a + 1] << 8) | (buf[a + 2] << 16) | (buf[a + 3] << 24)


def _wr32(buf, a: int, v: int) -> None:
    buf[a] = v & 0xFF
    buf[a + 1] = (v >> 8) & 0xFF
    buf[a + 2] = (v >> 16) & 0xFF
    buf[a + 3] = (v >> 24) & 0xFF


@dataclass
class ChecksumBlock:
    start: int
    end: int          # exclusive end of the summed area
    store: int        # address of the stored little-endian 32-bit value
    stored: int
    calculated: int
    skipped: bool = False

    @property
    def ok(self) -> bool:
        return self.skipped or self.stored == self.calculated


@dataclass
class ChecksumReport:
    layout: str
    blocks: list[ChecksumBlock] = field(default_factory=list)

    @property
    def checked(self) -> list[ChecksumBlock]:
        return [b for b in self.blocks if not b.skipped]

    @property
    def n_ok(self) -> int:
        return sum(1 for b in self.checked if b.ok)

    @property
    def n_total(self) -> int:
        return len(self.checked)

    @property
    def all_ok(self) -> bool:
        return self.n_total > 0 and self.n_ok == self.n_total

    def summary(self) -> str:
        return f"{self.layout}: {self.n_ok} of {self.n_total} correct"


# ---------------------------------------------------------------- tdi41 ----

def _tdi41_calc(buf, start: int, end: int, a: int, b: int) -> int:
    p = start
    while True:
        v2 = 0
        a ^= _w(buf, p)
        p += 2
        s = b & 0xF
        if s:
            a = ((a << s) | (a >> (16 - s))) & M16
            v2 = a & 1
        b = (b - _w(buf, p) - v2) & M16
        p += 2
        b ^= a
        if p == end:
            break
        a = (a - _w(buf, p)) & M16
        p += 2
        a = (a + 0xDAAC) & M16
        b ^= _w(buf, p)
        p += 2
        s = a & 0xF
        if s:
            b = ((b >> s) | (b << (16 - s))) & M16
        if p == end:
            break
    a = (a - 0x8631 + 0xDAAC) & M16
    b ^= 0xDF9B
    return (b << 16) | a


def _empty(buf, start: int, end: int) -> bool:
    return all(x == 0xC3 for x in buf[start:end - 4])


def _chain_layout(name, buf, bounds, skip_empty):
    rep = ChecksumReport(name)
    first = True
    a = b = 0
    for s, e in zip(bounds, bounds[1:]):
        if not first:
            a |= 0x8631
            b |= 0xEFCD
        if skip_empty and _empty(buf, s, e):
            rep.blocks.append(ChecksumBlock(s, e - 4, e - 4, 0, 0, skipped=True))
            continue
        stored = _rd32(buf, e - 4)
        calc = _tdi41_calc(buf, s, e - 4, a, b)
        blk = ChecksumBlock(s, e - 4, e - 4, stored, calc)
        if stored == 0xC3C3C3C3:
            blk.skipped = True
        rep.blocks.append(blk)
        first = False
    return rep


TDI41_BOUNDS = [0x10000, 0x14000, 0x4C000, 0x50000, 0x50B80, 0x5C000,
                0x60000, 0x60B80, 0x6C000, 0x70000, 0x70B80, 0x7C000]
TDI41V2_BOUNDS = [0x10000, 0x14000, 0x58000, 0x58B80, 0x64000, 0x70000,
                  0x70B80, 0x7C000]


def tdi41(buf) -> ChecksumReport:
    return _chain_layout("tdi41", buf, TDI41_BOUNDS, skip_empty=False)


def tdi41v2(buf) -> ChecksumReport:
    return _chain_layout("tdi41v2", buf, TDI41V2_BOUNDS, skip_empty=True)


# ----------------------------------------------------------- tdi41 2002 ----

def _c2002(buf, start, end, sa, sb, sc, sd, first_pass):
    count = start // 2
    end_count = end // 2
    p = start
    v1 = v2 = 0
    v7 = 0
    if count != end_count:
        v1, v2 = sa, sb
        if start == 0x8000:
            v1 ^= 0xD565
            v2 = (v2 + 0x308A) & M16
        while True:
            v1 ^= _w(buf, p)
            v3 = v2 & 0xF
            count += 1
            p += 2
            v4 = 0
            while v3 > 0:
                v4 = v1 >> 15
                v1 = ((v1 * 2) + v4) & M16
                v3 -= 1
            v2 = (v2 - ((v4 + _w(buf, p)) & M16)) & M16
            v2 = (v1 ^ v2) & M16
            p += 2
            count += 1
            if count > end_count:
                break
            v5 = _w(buf, p)
            p += 4
            v1 = (v1 + ((0xFFFF - v5 + 0xDAAD) & M16)) & M16
            v6 = buf[p - 1] << 8
            v2 ^= (v6 + buf[p - 2]) & M16
            v4 = v1 & 0xF
            count += 2
            while v4 > 0:
                v6 = (v6 | 0xFFFF) & v2
                v6 <<= 15
                v2 = ((v2 >> 1) + v6) & M16
                v4 -= 1
            if count > end_count:
                break
    if start == 0:
        v1 = (v1 - 0x79CF) & M16
        v2 = (v2 - 0x1033) & M16
    if not first_pass:
        v5 = sd
        v1 = (v1 - sc) & M16
        v6 = (sc | 0xFFFF) & 0xDAAD
        v1 = (v1 + ((v6 - 1) & M16)) & M16
        v7 &= 0xFFFF
        n = sc & 0xF
        while n > 0:
            n -= 1
            v7 = (v7 | 0xFFFF) & v5
            v7 *= 2
            v5 = ((v5 >> 15) + v7) & M16
        return (v1 + (((v5 ^ v2) & M16) << 16)) & 0xFFFFFFFF
    return (v1 + (v2 << 16)) & 0xFFFFFFFF


def tdi41_2002(buf) -> ChecksumReport:
    rep = ChecksumReport("tdi41_2002")
    n = len(buf)
    s1 = _c2002(buf, 0x14000, 0x4BFFE, 0x8631, 0xEFCD, 0, 0, True)
    s2 = _c2002(buf, 0, 0x7FFE, 0, 0, 0, 0, True)
    s1l, s1m = s1 & M16, s1 >> 16
    s2l, s2m = s2 & M16, s2 >> 16

    def add(start, end, store, *seeds):
        calc = _c2002(buf, start, end, *seeds, False)
        rep.blocks.append(ChecksumBlock(start, end, store, _rd32(buf, store), calc))

    add(0x8000, 0xFFFB, 0xFFFC, s2l, s2m, 0x4531, 0x3550)
    add(0x10000, 0x13FFB, 0x13FFC, 0, 0, 0x8631, 0xEFCD)
    st = 0x4FFFB
    while st + 5 < n:
        if bytes(buf[st + 13:st + 17]) == b"V4.1":
            sd = (s1l, s1m, s1l, s1m)
            add(st - 0x3FFB, st, st + 1, *sd)
            add(st + 5, st + 0xB80, st + 0xB81, *sd)
            add(st + 0xB85, st + 0xC000, st + 0xC001, *sd)
        st += 0x10000
    return rep


LAYOUTS = {"tdi41": tdi41, "tdi41v2": tdi41v2, "tdi41_2002": tdi41_2002}


def detect(buf) -> ChecksumReport | None:
    """Return the report of the layout that fits the file best.

    A layout fits when most of its blocks already verify; an edited file has
    only a few wrong blocks. Returns None for files of an unknown layout.
    """
    if len(buf) != 0x80000:
        return None
    best = None
    pref = {"tdi41_2002": 2, "tdi41": 1, "tdi41v2": 0}
    for fn in LAYOUTS.values():
        rep = fn(buf)
        if rep.n_total == 0:
            continue
        score = (rep.n_ok / rep.n_total, rep.n_total, pref[rep.layout])
        if best is None or score > best[0]:
            best = (score, rep)
    if best is None or best[1].n_ok == 0:
        return None
    return best[1]


def verify(buf, layout: str | None = None) -> ChecksumReport | None:
    if layout:
        return LAYOUTS[layout](buf)
    return detect(buf)


def fix(buf: bytearray, layout: str | None = None) -> ChecksumReport | None:
    """Correct every checksum in place and return the report after fixing.

    Blocks are chained (later seeds depend on earlier data in tdi41_2002),
    so the pass repeats until nothing changes.
    """
    rep = verify(buf, layout)
    if rep is None:
        return None
    fn = LAYOUTS[rep.layout]
    for _ in range(4):
        changed = False
        for blk in fn(buf).blocks:
            if not blk.skipped and blk.stored != blk.calculated:
                _wr32(buf, blk.store, blk.calculated)
                changed = True
        if not changed:
            break
    return fn(buf)
