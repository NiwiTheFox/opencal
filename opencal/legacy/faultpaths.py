"""GPL-3.0-only. Port of ZedSuite edc15-fault-paths.ts (C) 2026 ZedPerf.
OpenCal requires exact record spans and padding; no rounded/truncated triplet runs.
"""
import struct
from .layouts import detect


def records(data):
    from .edc15 import DTC_DATABASE
    from .dtc import DISABLED
    layout=detect(data)
    if layout['generation'] not in ('compact','standard'):raise ValueError('Fault-path layout not recognised.')
    result=[]
    for block in layout['blocks']:
        start,end=block['start'],block['end'];markers=[]
        for p in range(start,end-27):
            if data[p]!=0xc3:continue
            slots=struct.unpack_from('<8H',data,p+1)
            if all(c==0 or 16384<=c<=20000 and str(c) in DTC_DATABASE for c in slots):markers.append((p,slots))
        bank=[]
        for index,(p,slots) in enumerate(markers):
            codes=sorted(set(c for c in slots if c))
            if not codes:continue
            begin=p+27
            if index+1<len(markers):
                span=markers[index+1][0]-3-begin
                if span<=0 or span%6 or span>96:continue
                count=span//6
            else:
                count=0
                while count<16 and begin+count*6+6<=end and data[begin+count*6+5]==0 and data[begin+count*6]!=0x23:count+=1
            segments=[begin+i*6 for i in range(count)]
            if not segments or any(data[a+5]!=0 for a in segments):continue
            raw=b''.join(bytes(data[a:a+5]) for a in segments)
            for code in codes:
                info=DTC_DATABASE[str(code)]
                slot=next(i for i,c in enumerate(slots) if c==code)
                bank.append({'address':begin,'code_address':p+1+slot*2,'vag_code':code,'code':info['code'],
                             'description':info['description']+' (shared fault path)','system':info['system'],
                             'enabled':raw!=DISABLED*len(segments),'raw':raw.hex(),'segments':segments,
                             'path_codes':codes,'path_address':p,'codeblock_base':block['base'],'verification':'candidate'})
        if len({r['vag_code'] for r in bank})<20:raise ValueError('Insufficient complete fault-path records in every codeblock.')
        result.extend(bank)
    if not result:raise ValueError('No complete fault-path DTC table found.')
    return result
