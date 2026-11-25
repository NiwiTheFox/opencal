"""Build a synthetic 512 KB EDC15P-like file for tests (no vehicle firmware)."""
from __future__ import annotations

import struct

from opencal.core import checksum

BASE = 0x70000


def _axis(aid, values):
    return struct.pack("<HH", aid, len(values)) + b"".join(struct.pack("<H", v) for v in values)


def _table(xid, xv, yid, yv, fn):
    body = _axis(xid, xv) + _axis(yid, yv)
    for x in xv:
        for y in yv:
            body += struct.pack("<H", int(fn(x, y)) & 0xFFFF)
    return body


RPM = [800, 1000, 1250, 1500, 1750, 2000, 2250, 2500, 2750, 3000, 3250, 3500, 3750, 4000, 4500, 5000]
AIR = [3000, 3500, 4000, 4500, 5000, 5500, 6000, 6500, 7500, 8500, 9000, 10000, 10500]
PEDAL = [0, 500, 1000, 2000, 4000, 6000, 8000, 10000]
IQAX = [0, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500]
ATM = [800, 900, 1000]


def build() -> bytearray:
    b = bytearray((i * 7 + 3) & 0xFF for i in range(0x80000))   # pseudo code area
    b[0x40000:0x80000] = b"\xC3" * 0x40000                        # empty banks
    region = bytearray(b"\x00" * 0x10000)
    b[BASE - 0x4000:BASE + 0xC000] = region
    b[BASE + 8:BASE + 12] = b"V4.1"
    # codeblock id pointer at base+0x1002 -> base+0x1200 holds id 3
    struct.pack_into("<H", b, BASE + 0x1000, 0x2000)
    struct.pack_into("<H", b, BASE + 0x1002, 0x1200)
    struct.pack_into("<H", b, BASE + 0x1200, 3)
    info = b"038906019XX 1,9l R4 EDC  SG  9999 "
    b[BASE + 0x3000:BASE + 0x3000 + len(info)] = info
    t = BASE - 0x3000
    tables = [
        ("smoke", _table(0xF948, RPM, 0xDA72, AIR, lambda x, y: min(y * 0.4 + 800, 5000))),
        ("driver_wish", _table(0xEC2C, RPM[:12], 0xC0B4, PEDAL, lambda x, y: y * 0.55)),
        ("torque_limiter", _table(0xC02C, ATM, 0xEC2C, RPM, lambda x, y: 4400 - abs(y - 2000) // 2)),
    ]
    out = {}
    for name, blob in tables:
        out[name] = t
        b[t:t + len(blob)] = blob
        t += len(blob) + 16
    t = BASE + 0x6000
    blob = _table(0xEC2C, RPM, 0xC032, IQAX, lambda x, y: 1000 + min(x, 2500) * 0.4)
    b[t:t + len(blob)] = blob
    # SVBL pattern + value
    p = BASE + 0x1B00
    b[p:p + 16] = bytes([0xD2, 0x00, 0xFC, 0x03, 0, 0, 0, 0, 0x04, 0x00, 0x11, 0x22, 0x33, 0xC3, 0, 0])
    struct.pack_into("<H", b, p + 16, 2350)
    # checksum stores: make all tdi41_2002 blocks valid
    checksum.fix(b, "tdi41_2002")
    return b


if __name__ == "__main__":
    with open("synthetic_edc15p.bin", "wb") as fh:
        fh.write(build())
