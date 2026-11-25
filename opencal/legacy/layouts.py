"""GPL-3.0-only; bounded ZedSuite edc15p/layout.rs layout port.
Copyright 2026 ZedPerf. Modified for OpenCal; unknown files never get fallback banks.
"""
from .checksums import SIGNATURE,standard_bases

def detect(data):
    if len(data)!=0x80000:return {'generation':'unknown','blocks':[]}
    compact=[b for b in (0x58000,0x64000,0x70000) if data[b+1:b+12]==SIGNATURE]
    if any(b in compact for b in (0x58000,0x64000)):
        return {'generation':'compact','blocks':[{'base':b,'start':b,'end':b+0xc000} for b in compact]}
    bases=standard_bases(data)
    if bases:return {'generation':'standard','blocks':[{'base':b,'start':b-0x4000,'end':b+0xc000} for b in bases]}
    early=[{'base':e-0x8000,'start':e-0x8000,'end':e} for e in range(0x8000,len(data)+1,0x8000) if data[e-8:e-4]==bytes.fromhex('3c 3c 41 e4')]
    return {'generation':'early' if len(early)>=2 else 'unknown','blocks':early if len(early)>=2 else []}
