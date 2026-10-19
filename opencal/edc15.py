"""GPL-3.0-only. Modified 2026-10-18 from ZedSuite (C) 2026 ZedPerf.

Conservative subset of EDC15P structure/pattern detection and classic DTC records.
Upstream has additional selector, orientation and family-specific passes not ported.
All detected maps remain candidates. See NOTICE and third_party/zedsuite.
"""
import json
import re
import struct
from pathlib import Path
from .checksums import SIGNATURE, standard_bases

DATA=Path(__file__).parent/'data'
PATTERNS=json.loads((DATA/'edc15p-patterns.json').read_text(encoding='utf-8'))
DTC_DATABASE=json.loads((DATA/'dtc-vag.json').read_text(encoding='utf-8'))
AXIS_IDS={0xDB,0xC0,0xC1,0xC2,0xC4,0xC5,0xE0,0xE4,0xE5,0xE9,0xEA,0xEB,0xEC,0xDA,0xDD,0xDE,0xF9,0xFE,0xE8}
SOURCE='ZedPerf/ZedSuite, GPL-3.0-only; conservative OpenCal port 2026-10-18'


def identity(data):
    bases=standard_bases(data)
    if not bases: return []
    strings=[]
    for match in re.finditer(rb'[\x20-\x7e]{8,}',data):
        value=match.group().decode('ascii')
        if re.search(r'0389060|02810\d{5}|EDC|SG\s*\d{4}',value):
            strings.append({'offset':match.start(),'text':value[:120]})
    return [{'family':'EDC15P/compatible V4.1 candidate','confidence':'structural and embedded identifiers; P/P+/P++ not distinguished',
             'name':'Standard V4.1 codeblocks','source':SOURCE,
             'evidence':{'signature_offsets':[hex(b+1) for b in bases],'identifiers':strings[:16]}}]


def _map(address,rows,cols,name,category,factor=1.0,offset=0.0,unit='raw'):
    return {'id':f'edc15-{address:x}','name':f'{name} @ {address:06X}', 'address':address,'rows':rows,'columns':cols,
            'type':'u16','endian':'little','factor':factor,'offset':offset,'unit':unit,'category':category,
            'verification':'candidate','source':SOURCE,'license':'GPL-3.0-only'}


def discover(data):
    from .catalog import match_profile
    known=match_profile(data)
    if known is not None:
        from .solutions import launch_control_maps
        by_address={m['address']:m for m in known['maps']}
        by_address.update({m['address']:m for m in launch_control_maps(data)})
        known['maps']=list(by_address.values())
        return known
    return discover_heuristic(data)


def discover_heuristic(data):
    bases=standard_bases(data)
    if not bases:
        raise ValueError('EDC15 discovery currently requires a 512 KiB standard V4.1 layout.')
    maps={}
    def axis(pos, end):
        if pos+4>end: return None
        ident,n=struct.unpack_from('<HH',data,pos)
        high=ident>>8
        if high not in AXIS_IDS or not 1<=n<=(32 if high&0xF0==0xE0 else 31) or pos+4+n*2>end:
            return None
        values=list(struct.unpack_from('<'+'H'*n,data,pos+4))
        # Deliberately stricter than upstream's bounds-only structural pass.
        if n>1 and (len(set(values))<2 or not all(x<=y for x,y in zip(values,values[1:]))): return None
        return ident,n,values,pos+4+n*2
    for base in bases:
        start,end=base-0x4000,base+0xC000
        for pos in range(start,end-8,2):
            ax=axis(pos,end)
            if not ax: continue
            xid,nx,xvals,ypos=ax
            ay=axis(ypos,end)
            if not ay: continue
            yid,ny,yvals,address=ay
            if nx*ny<4 or address+nx*ny*2>end: continue
            # Multi-temperature smoke tables have a third axis + index array.
            az=axis(address,end)
            if xid>>8==0xF9 and yid>>8==0xDA and nx==16 and ny==13 and az and az[0]>>8==0xC1 and az[1]<=10:
                _,count,temperatures,indices=az
                first=indices+count*2
                if first+count*416<=end:
                    for slot,temp in enumerate(temperatures):
                        a=first+slot*416
                        if sum(v!=0 for v in data[a:a+416])<21: continue
                        m=_map(a,16,13,f'Smoke limiter {temp*0.1-273.1:g} °C (selector candidate)','Smoke limitation',0.01,unit='mg/st')
                        m.update({'header_address':pos,'codeblock_base':base,'selector_address':address,'selector_slot':slot,
                                  'x_axis':{'address':ypos+4,'type':'u16','endian':'little','factor':.1,'offset':0,'values':[v*0.1 for v in yvals],'unit':'mg/st'},
                                  'y_axis':{'address':pos+4,'type':'u16','endian':'little','factor':1,'offset':0,'values':xvals,'unit':'rpm'},
                                  'evidence':f'F9/DA 16x13 axes and bounded C1 selector at 0x{address:X}; nonempty slot {slot}.',
                                  'confidence':0.7})
                        maps[a]=m
                continue
            # Reject a third axis header instead of mistaking it for map values.
            if az: continue
            matches=[]
            for p in PATTERNS:
                if not p['x_id'] or not p['y_id']: continue
                if (nx,ny,xid>>8,yid>>8)==(p['x_length'],p['y_length'],p['x_id'],p['y_id']): matches.append((p,False))
                elif (ny,nx,yid>>8,xid>>8)==(p['x_length'],p['y_length'],p['x_id'],p['y_id']): matches.append((p,True))
            semantics={p['name'] for p,_ in matches}
            if len(semantics)==1:
                p,swapped=matches[0]
                # Raw storage orientation retained. Scale axes by their matched identities.
                xf,xo,yf,yo=(p['y_factor'],p['y_offset'],p['x_factor'],p['x_offset']) if swapped else (p['x_factor'],p['x_offset'],p['y_factor'],p['y_offset'])
                m=_map(address,nx,ny,p['name']+' (pattern candidate)',p['category'],p['factor'],p['offset'],p['value_name'])
                m['unit']={'N75 duty cycle':'%','Boost target map':'mbar','Boost limit map':'mbar','Injector duration':'degrees crank angle','Start IQ':'mg/st','SOI limiter':'degrees BTDC'}.get(p['name'],'scaled '+p['value_name'])
                m['pattern_axis_swap']=swapped
                if p['name']=='Fuel volume correction': m['type']='i16'
            else:
                xf,yf=1,1; xo,yo=0,0
                m=_map(address,nx,ny,'Unclassified axis table','Unclassified')
            xi,yi=xid>>8,yid>>8
            raw=list(struct.unpack_from('<'+'H'*(nx*ny),data,address))
            # Source-backed corrections applied after broad pattern metadata.
            if xi==0xEC and yi==0xC0 and (nx,ny) in ((16,8),(8,16),(10,12),(12,10),(9,12),(12,9),(8,12),(12,8)) and sum(v<=10000 for v in raw)>len(raw)*0.75:
                m.update(name=f'Driver wish (candidate) @ {address:06X}',category='Engine fuel request',type='i16',factor=0.01,offset=0.0,unit='mg/st')
                xf,yf=1,0.01; xo,yo=0,0
            elif xi==0xC0 and yi==0xEC and nx==3 and ny in (20,21,25):
                m.update(name=f'Torque limiter (candidate) @ {address:06X}',category='Engine torque limiters',factor=0.01,offset=0.0,unit='mg/st')
                xf=yf=1; xo=yo=0
            elif xi==0xEC and yi==0xC5 and nx==10 and ny==8 and 100<=xvals[0] and xvals[-1]<=6000 and 1500<=yvals[0] and yvals[-1]<=4000 and all(100<=v<=700 for v in raw):
                m.update(name=f'BIP correction by SOI and rpm (candidate) @ {address:06X}',category='Injection system',factor=1/256,offset=0.0,unit='coefficient')
                xf,xo,yf,yo=1,0,-0.023437,78
            elif xi==0xEC and yi==0xDA and nx==16 and ny in (10,13):
                kind='MAP' if yvals[0]<2500 else 'MAF'
                m.update(name=f'IQ by {kind} limiter (candidate) @ {address:06X}',category='Smoke limitation',factor=0.01,offset=0.0,unit='mg/st')
                xf,yf=1,(1 if kind=='MAP' else 0.1); xo=yo=0
            elif xi==0xEC and yi==0xEA and nx*ny==208:
                m.update(name=f'N75 duty cycle (candidate) @ {address:06X}',category='Turbo boost pressure control',factor=-0.01,offset=100.0,unit='%')
                xf,yf=1,0.01; xo=yo=0
            elif xi==0xEC and yi in (0xC0,0xE9) and nx==16 and ny==13 and yvals[0]<=1000 and yvals[-1]<=10000:
                m.update(name=f'EGR (candidate) @ {address:06X}',category='EGR',factor=0.1,offset=0.0,unit='mg/st')
                xf,yf=1,0.01; xo=yo=0
            elif xi==0xEC and yi==0xC1 and nx==ny==10:
                m.update(name=f'Limit of overboost protection (candidate) @ {address:06X}',category='Turbo boost pressure',factor=1.0,offset=0.0,unit='raw')
                xf,yf=1,0.01; xo=yo=0
            elif xi==0xEC and yi==0xC0 and nx==ny==8:
                m.update(name=f'Expected fuel temperature (candidate) @ {address:06X}',category='Fuel',type='i16',factor=0.1,offset=-273.0,unit='°C')
                xf,yf=1,0.01; xo=yo=0
            elif xi==0xEC and yi==0xC1 and nx==ny==8 and all(1931<=v<=4731 for v in yvals) and any(raw):
                m.update(name=f'MAF correction by temperature (candidate) @ {address:06X}',category='Smoke limitation',type='i16',factor=0.01,offset=0.0,unit='raw')
                xf,yf=1,0.1; xo,yo=0,-273.1
            elif xi==0xC1 and yi==0xEC and nx==ny==3 and all(2731<=v<=4731 for v in xvals) and all(500<=v<=6500 for v in yvals) and 500<=max(raw)<=12000:
                m.update(name=f'IQ by air intake temp (candidate) @ {address:06X}',category='Smoke limitation',factor=0.01,offset=0.0,unit='mg/st')
                xf,yf=0.1,1; xo,yo=-273.0,0
            elif 'EGR' in m['name']:
                # Upstream filters out a same-shape pressure limiter. Avoid the known false name.
                iq=xvals if xi==0xC0 else yvals if yi==0xC0 else []
                if not iq or iq[0]>1000 or iq[-1]>10000:
                    m.update(name=f'Unclassified axis table @ {address:06X}',category='Unclassified',factor=1.0,offset=0.0,unit='raw')
                    xf=yf=1; xo=yo=0
            m.update({'header_address':pos,'codeblock_base':base,
                      'x_axis':{'address':ypos+4,'type':'u16','endian':'little','factor':yf,'offset':yo,'id':hex(yid),'values':[v*yf+yo for v in yvals]},
                      'y_axis':{'address':pos+4,'type':'u16','endian':'little','factor':xf,'offset':xo,'id':hex(xid),'values':[v*xf+xo for v in xvals]},
                      'confidence':0.65 if len(semantics)==1 else 0.35,
                      'evidence':f'Two bounded monotonic axes at 0x{pos:X}, IDs {xid:04X}/{yid:04X}; {nx}x{ny}; metadata naming is heuristic.'})
            maps.setdefault(address,m)
        # Independently visible scalar marker, adapted from upstream find_svrl_sequence.
        pos=start
        while True:
            pos=data.find(bytes.fromhex('27 07 00 0E'),pos,end)
            if pos<0: break
            address=pos+4
            if address+2<=end and 3000<=int.from_bytes(data[address:address+2],'little')<=8000:
                m=_map(address,1,1,'SVRL (marker candidate)','Maximum RPM limiter',unit='rpm')
                m.update({'minimum':3000,'maximum':8000,'evidence':f'27 07 00 0E marker at 0x{pos:X}; heuristic range only, not a validated safe engine range.'})
                maps[address]=m
            pos+=1
    from .source_sequences import source_maps
    maps.update(source_maps(data,bases))
    from .solutions import launch_control_maps
    maps.update({m['address']:m for m in launch_control_maps(data)})
    # Unclassified structures are diagnostics, not a usable mappack. Hide them
    # from the calibration tree rather than presenting a large false map count.
    unclassified=[m for m in maps.values() if m['category']=='Unclassified']
    result=sorted((m for m in maps.values() if m['category']!='Unclassified'),key=lambda m:m['address'])
    for i,m in enumerate(result):
        stop=m['address']+m['rows']*m['columns']*2
        m['overlaps']=[n['id'] for n in result[i+1:] if n['address']<stop]
    return {'schema':'opencal.definitions','version':1,'maps':result,'signatures':[], 'source':SOURCE,
            'detection':{'method':'heuristic','named_candidates':len(result),'unclassified_structures_hidden':len(unclassified),
                         'verification':'experimental candidates only'}}


def dtc_records(data):
    bases=standard_bases(data)
    if not bases: raise ValueError('Only standard V4.1 classic 8-byte DTC tables are supported.')
    records=[]
    for base in bases:
        start=base-0x4000
        for marker in range(start+0x2800,min(start+0x8100,len(data)-2)):
            if data[marker]!=0x23: continue
            code=int.from_bytes(data[marker+1:marker+3],'little')
            info=DTC_DATABASE.get(str(code))
            if not info or not 16471<=code<=20000: continue
            address=marker-5
            status,flags,kind=struct.unpack_from('<HHB',data,address)
            enabled=not(status==65535 and flags==0 and kind==0)
            records.append({'address':address,'code_address':marker+1,'vag_code':code, 'code':info['code'],
                            'description':info['description'],'system':info['system'],'enabled':enabled,
                            'codeblock_base':base,'raw':bytes(data[address:address+8]).hex(),'verification':'candidate'})
    if len({r['vag_code'] for r in records})<20:
        raise ValueError('Too few documented classic entries; table layout is unverified (may use fault-path records).')
    return records


def disable_dtc(data, code):
    records=[r for r in dtc_records(data) if r['vag_code']==code]
    if not records: raise ValueError('DTC is not present in supported tables.')
    result=bytearray(data)
    for record in records:
        a=record['address']; result[a:a+5]=bytes.fromhex('FF FF 00 00 00')
    return bytes(result),records


def restore_dtc(data, original, code):
    """Restore exact original record bytes, never invent universal enabled values."""
    stock={r['address']:r for r in dtc_records(original) if r['vag_code']==code}
    current=[r for r in dtc_records(data) if r['vag_code']==code]
    if not current or any(r['address'] not in stock for r in current):
        raise ValueError('No matching original DTC records; exact restoration unavailable.')
    result=bytearray(data)
    for r in current:
        a=r['address']; result[a:a+5]=original[a:a+5]
    return bytes(result)
