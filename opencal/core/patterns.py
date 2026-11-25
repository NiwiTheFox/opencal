"""Single values and switches found by byte pattern rather than axis headers."""
from __future__ import annotations

from dataclasses import dataclass


def find_all(buf, pattern: bytes, mask: list[int] | None = None, start: int = 0, end: int | None = None):
    data = bytes(buf)
    end = len(data) - len(pattern) if end is None else end
    if mask is None:
        i = data.find(pattern, start)
        while 0 <= i <= end:
            yield i
            i = data.find(pattern, i + 1)
        return
    # anchor on the first fixed byte, then verify the rest
    first = next(k for k, v in enumerate(mask) if v)
    i = data.find(pattern[first:first + 1], start + first)
    while i >= 0 and i - first <= end:
        s = i - first
        if all(not mask[k] or data[s + k] == pattern[k] for k in range(len(pattern))):
            yield s
        i = data.find(pattern[first:first + 1], i + 1)


@dataclass
class Scalar:
    kind: str
    name: str
    address: int
    unit: str = ""
    factor: float = 1.0
    description: str = ""

    def raw(self, buf) -> int:
        return buf[self.address] | (buf[self.address + 1] << 8)

    def value(self, buf) -> float:
        return self.raw(buf) * self.factor


SVBL_1 = (bytes([0xD2, 0x00, 0xFC, 0x03, 0, 0, 0, 0, 0x04, 0x00, 0xFF, 0xFF, 0xFF, 0xC3, 0, 0]),
          [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1], 16)
SVBL_2 = (bytes([0xDF, 0x7A, 0x28, 0, 0, 0, 0, 0, 0xDF, 0x7A]), None, -2)
MAPMAF = (bytes([0x41, 0x02, 0, 0, 0x00, 0x01, 0x01, 0x00]), [1, 1, 0, 0, 1, 1, 1, 1], 2)
LAUNCH = (bytes([0xFF, 0xFF, 0x02, 0x00, 0x80, 0x00, 0x00, 0x0A, 0xFF, 0xFF, 0x02, 0x00, 0x00, 0x00, 0x70, 0x17]),
          [0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1])


def find_scalars(buf) -> list[Scalar]:
    out: list[Scalar] = []
    seen = set()
    for pat, mask, off in (SVBL_1, SVBL_2):
        for i in find_all(buf, pat, mask, 0x40000):
            a = i + off
            if buf[a] | (buf[a + 1] << 8) == 0xC300:
                a -= 2
            if a in seen:
                continue
            seen.add(a)
            out.append(Scalar("svbl", "SVBL (single value boost limit)", a, "mbar",
                              description="Hard boost limit. Above it the ECU cuts to limp mode."))
            for j in find_all(buf, MAPMAF[0], MAPMAF[1], max(0, a - 0x100), a):
                out.append(Scalar("map_maf", "MAP/MAF switch (0 = MAF, 257 = MAP)", j + MAPMAF[2],
                                  description="Which sensor limits the fuel: 0 uses airflow, 0x101 boost."))
                break
    return out


def launch_sites(buf) -> list[int]:
    return list(find_all(buf, LAUNCH[0], LAUNCH[1], 0x40000))
