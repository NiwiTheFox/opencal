"""Multimap facts: calibration banks, and code changes against a stock reference.

A multimap file carries several full calibrations (codeblocks). Switching
while driving (cruise stalk, pedal) needs a code patch that picks the bank at
runtime; such patches typically hook the codeblock selection and place their
routine in unused (0xC3-filled) flash. OpenCal preserves any such patch: it
only edits calibration banks, never the code area, unless you ask it to.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .ecufile import EcuFile

CODE_END = 0x40000          # below this: program code, above: calibration pages
EMPTY = 0xC3


@dataclass
class CodePatch:
    ranges: list = field(default_factory=list)   # (start, end) differing ranges in code
    in_free_flash: int = 0                         # bytes written where the stock file was empty
    hooks: int = 0                                 # small edits inside stock code

    @property
    def present(self) -> bool:
        return bool(self.ranges)


def bank_summary(f: EcuFile) -> list[tuple[int, int | None]]:
    return [(cb.base, cb.id) for cb in f.populated_banks]


def code_patch(f: EcuFile, reference: bytes) -> CodePatch:
    """Compare the code area with a stock file of the same software."""
    p = CodePatch()
    if len(reference) != len(f.buf):
        return p
    a = bytes(f.buf[:CODE_END])
    b = reference[:CODE_END]
    i = 0
    n = len(a)
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and (a[j] != b[j] or a[j:j + 8] != b[j:j + 8]):
                j += 1
            p.ranges.append((i, j))
            if all(x == EMPTY for x in b[i:j]):
                p.in_free_flash += j - i
            else:
                p.hooks += 1
            i = j
        else:
            i += 1
    # checksum words are expected to change: ignore 4-byte runs at known stores
    p.ranges = [(s, e) for s, e in p.ranges if not (e - s <= 4 and (e & 0xFFF) in (0x000, 0xFFC, 0xFFE, 0xFFF))]
    return p


def describe(f: EcuFile, reference: bytes | None = None) -> str:
    banks = bank_summary(f)
    s = f"{len(banks)} bank(s), ids {', '.join(str(i) for _, i in banks)}" if banks else "no V4.1 banks"
    if reference is not None:
        p = code_patch(f, reference)
        if p.present:
            s += f"; code patch vs stock: {len(p.ranges)} range(s), {p.in_free_flash} bytes in free flash, {p.hooks} hook(s)"
        else:
            s += "; code identical to stock"
    return s
