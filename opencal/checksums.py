"""GPL-3.0-only. Adapted 2026-10-18 from ZedSuite by ZedPerf (C) 2026.

Source: src/lib/ecu/bosch/checksums/edc15p-checksum.ts (EDCSuite-derived).
See third_party/zedsuite and NOTICE. Only standard V4.1 / 2002 is enabled.
Unknown formats fail closed; original bytes are never modified.
"""
import struct

SIGNATURE = bytes.fromhex('67 FF FF FF FF FF FF 56 34 2E 31')


def standard_bases(data):
    if len(data) != 0x80000 or any(data[p:p+11] == SIGNATURE for p in (0x58001,0x64001)):
        return []
    return [p for p in (0x50000,0x60000,0x70000) if data[p+1:p+12] == SIGNATURE]


def calculate_2002(data, start, end, a, b, c=0, d=0, first=True):
    """Exact 16-bit arithmetic port. end follows upstream inclusive word semantics."""
    if start < 0 or start % 2 or end >= len(data) or start > end:
        raise ValueError('Invalid checksum calculation range.')
    count, stop, pos = start//2, end//2, start
    x=y=0
    def word(off):
        return struct.unpack_from('<H',data,off)[0]
    if count != stop:
        x,y=a&65535,b&65535
        if start==0x8000: x^=0xD565; y=(y+0x308A)&65535
        while True:
            x=(x^word(pos))&65535; n=y&15; count+=1; pos+=2; carry=0
            for _ in range(n):
                carry=x>>15; x=(x*2+carry)&65535
            y=(y-carry-word(pos))&65535; y=(x^y)&65535
            pos+=2; count+=1
            if count>stop: break
            value=word(pos); pos+=4
            x=(x+65535-value+0xDAAD)&65535
            y=(y^word(pos-2))&65535
            count+=2
            for _ in range(x&15): y=((y>>1)+(y<<15))&65535
            if count>stop: break
    if start==0: x=(x-0x79CF)&65535; y=(y-0x1033)&65535
    if not first:
        x=(x-c+0xDAAD-1)&65535
        rot=d&65535
        for _ in range(c&15): rot=((rot>>15)+(rot*2))&65535
        return (x+((rot^y)<<16))&0xffffffff
    return (x+(y<<16))&0xffffffff


def inspect(data):
    bases=standard_bases(data)
    unknown={'status':'unverified','algorithm':'unknown','regions':[],
             'reason':'Requires exact 512 KiB standard V4.1 layout; compact and other variants are not enabled.'}
    if not bases: return unknown
    seed1=calculate_2002(data,0x14000,0x4BFFE,0x8631,0xEFCD)
    seed2=calculate_2002(data,0,0x7FFE,0,0)
    regions=[]
    def add(start,end,store,a,b,c,d):
        computed=calculate_2002(data,start,end,a,b,c,d,False)
        stored=struct.unpack_from('<I',data,store)[0]
        regions.append({'start':start,'end_inclusive':end,'store':store,'stored':stored,'computed':computed,'matches':stored==computed})
    add(0x8000,0xFFFB,0xFFFC,seed2&65535,seed2>>16,0x4531,0x3550)
    add(0x10000,0x13FFB,0x13FFC,0,0,0x8631,0xEFCD)
    for base in bases:
        a,b=seed1&65535,seed1>>16
        add(base-0x4000,base-5,base-4,a,b,a,b)
        add(base,base+0xB7B,base+0xB7C,a,b,a,b)
        add(base+0xB80,base+0xBFFB,base+0xBFFC,a,b,a,b)
    matched=sum(r['matches'] for r in regions)
    return {'status':'matched' if matched==len(regions) else 'mismatch', 'algorithm':'tdi41_2002',
            'found':len(regions),'matched':matched,'regions':regions,
            'seed_input_regions_inclusive':[[0,0x7fff],[0x14000,0x4bfff]],
            'reason':'Stored region sums compared with GPL ZedSuite-derived algorithm. This does not validate ECU execution or checksum-enforcement code.'}


def correct(data, original):
    baseline=inspect(original)
    if baseline['status']!='matched':
        raise ValueError('Correction requires an original with all supported checksum regions matching.')
    if standard_bases(data)!=standard_bases(original):
        raise ValueError('Codeblock layout changed; checksum correction refused.')
    report=inspect(data)
    result=bytearray(data)
    # These checksum fields are outside seed inputs and one another's protected ranges.
    for r in report['regions']:
        struct.pack_into('<I',result,r['store'],r['computed'])
    if inspect(result)['status']!='matched':
        raise ValueError('Checksum post-verification failed.')
    return bytes(result)
