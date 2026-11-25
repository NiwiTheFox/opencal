"""Bounded EDC15P EGR request-map and diagnostic solution.

GPL-3.0-only. Target-map strategy adapted from the GPL VAGEDCSuite fork's
EDC15PTuner.DisableEGRMap; final LE word order checked in Tools.savedatatobinary.
OpenCal adds explicit software/layout guards, DTC selection, previews and undo.
Structural/byte-level support is not a vehicle-execution validation.
"""
import struct
from .core import digest
from .checksums import standard_bases
from .transfer import identifiers
from .codeblocks import metadata_id
from .edc15 import dtc_records
from .dtc import DISABLED

PROFILE={'ecu':['038906019FJ'],'hardware':['0281010789'],'software':['1376']}
CODES=frozenset(('P3131','P3130','P1402','P1441'))
MAP_OFFSET=0x5624
RAW_TARGET=8500
TARGET=struct.pack('<H',RAW_TARGET)*208
SOURCE='GPL VAGEDCSuite EDC15PTuner.cs DisableEGRMap; OpenCal checked FJ/1376 layout'


def inspect(data):
    bases=standard_bases(data)
    failure={'status':'unsupported','maps':[],'records':[],
             'reason':'EGR automation currently supports only the checked 038906019FJ / 0281010789 / SG 1376 standard V4.1 layout.'}
    if not bases or identifiers(data)!=PROFILE:return inspect_structural(data)
    maps=[]
    for base in bases:
        if identifiers(data[base-0x4000:base+0xc000])!=PROFILE:
            return dict(failure,reason=f'Embedded identifiers differ or are missing in bank 0x{base:05X}.')
        address=base+MAP_OFFSET;header=address-66
        y_id,rows=struct.unpack_from('<HH',data,header)
        x_id,columns=struct.unpack_from('<HH',data,header+36)
        if y_id>>8!=0xEC or x_id>>8 not in (0xC0,0xE9) or (rows,columns)!=(16,13):
            return dict(failure,reason=f'EGR axis headers do not match the checked layout in bank 0x{base:05X}.')
        rpm=struct.unpack_from('<16H',data,header+4);iq=struct.unpack_from('<13H',data,header+40)
        if not (rpm[0]<=1000 and 3500<=rpm[-1]<=6500 and iq[0]<=1000 and 3000<=iq[-1]<=10000 and
                len(set(rpm))>=8 and len(set(iq))>=4 and all(a<=b for a,b in zip(rpm,rpm[1:])) and all(a<=b for a,b in zip(iq,iq[1:]))):
            return dict(failure,reason=f'EGR axis ranges/order differ from the checked layout in bank 0x{base:05X}.')
        raw=struct.unpack_from('<208H',data,address)
        if max(raw)>16000:return dict(failure,reason=f'EGR request values are outside the supported range in bank 0x{base:05X}.')
        maps.append({'bank':base,'codeblock':metadata_id(data,base),'address':address,'rows':rows,'columns':columns,
                     'name':'EGR fresh-air request','minimum':min(raw)*.1,'maximum':max(raw)*.1,
                     'at_target':bytes(data[address:address+416])==TARGET})
    try:all_records=dtc_records(data)
    except ValueError as error:return dict(failure,reason=str(error))
    records=[r for r in all_records if r['system']=='EGR']
    for base in bases:
        selected=[r for r in records if r['codeblock_base']==base]
        if len(selected)!=4 or {r['code'] for r in selected}!=CODES:
            return dict(failure,reason=f'EGR diagnostic layout is incomplete or differs in bank 0x{base:05X}.')
    enabled=sum(r['enabled'] for r in records);ready=all(m['at_target'] for m in maps) and enabled==0
    return {'status':'target present' if ready else 'supported','maps':maps,'records':records,
            'maps_at_target':sum(m['at_target'] for m in maps),'enabled_records':enabled,'source':SOURCE,
            'verification':'Source-backed request target; vehicle behaviour unverified'}


def preview(document,restore=False):
    state=inspect(document.data)
    if state['status']=='unsupported':raise ValueError(state['reason'])
    if restore:
        original=inspect(document.original)
        if original['status']=='unsupported' or [m['address'] for m in original['maps']]!=[m['address'] for m in state['maps']]:
            raise ValueError('The loaded original does not have the same supported EGR layout.')
        originals={r['address']:r for r in original['records']}
        if any(r['address'] not in originals or originals[r['address']]['vag_code']!=r['vag_code'] for r in state['records']):
            raise ValueError('Original EGR diagnostic records differ; exact restoration unavailable.')
    edits=[];result=bytearray(document.data);cells=0
    for m in state['maps']:
        address=m['address'];size=m['rows']*m['columns']*2;before=bytes(result[address:address+size]);after=bytes(document.original[address:address+size]) if restore else struct.pack('<H',RAW_TARGET)*(size//2)
        if before!=after:
            cells+=sum(before[i:i+2]!=after[i:i+2] for i in range(0,size,2))
            edits.append({'address':address,'before':before.hex(),'after':after.hex(),'bank':m['bank'],'kind':'map','name':m['name']})
            result[address:address+size]=after
    for record in state['records']:
        address=record['address'];before=bytes(result[address:address+5]);after=bytes(document.original[address:address+5]) if restore else DISABLED
        if before!=after:
            edits.append({'address':address,'before':before.hex(),'after':after.hex(),'bank':record['codeblock_base'],'kind':'dtc','name':record['code']+' · '+record['description']})
            result[address:address+5]=after
    return {'schema':'opencal.patch-preview','version':1,'name':'Restore loaded-original EGR settings' if restore else 'Disable EGR · request target and related diagnostics',
            'input_sha256':digest(document.data),'result_sha256':digest(result),'edits':edits,'map_cells_changed':cells,
            'maps':state['maps'],'records':state['records'],'restore':restore,'source':SOURCE,
            'verification':'850 mg/st fresh-air request strategy from GPL source; ECU execution unverified'}


def inspect_structural(data):
    """Source pattern support across identified standard EDC15 calibrations.

    Require exact bounded axis structures and the same relative topology in all
    banks. No switch-off is inferred for temperature maps or arbitrary labels.
    """
    from .edc15 import discover_heuristic
    from .layouts import detect
    failure={'status':'unsupported','maps':[],'records':[],
             'reason':'No complete supported EGR request-map and diagnostic layout found for this EDC15 software.'}
    layout=detect(data);ids=identifiers(data)
    if layout['generation']!='standard' or any(not v for v in ids.values()):return failure
    try:definitions=discover_heuristic(data);all_records=dtc_records(data)
    except ValueError as error:return dict(failure,reason=str(error))
    maps=[];topology=None;codes=None;records=[]
    for block in layout['blocks']:
        base=block['base']
        if identifiers(data[block['start']:block['end']])!=ids:return dict(failure,reason='Inconsistent bank identifiers.')
        selected=[]
        for m in definitions['maps']:
            if not m['name'].startswith('EGR ') or m['category']!='EGR' or m.get('codeblock_base')!=base:continue
            if (m['rows'],m['columns']) not in ((16,13),(16,12),(16,11)):continue
            h=m.get('header_address')
            if h is None:continue
            yi,n=struct.unpack_from('<HH',data,h);xpos=h+4+2*n;xi,k=struct.unpack_from('<HH',data,xpos)
            if yi>>8!=0xec or xi>>8 not in (0xc0,0xe9) or (n,k)!=(m['rows'],m['columns']):continue
            rpm=struct.unpack_from('<'+'H'*n,data,h+4);iq=struct.unpack_from('<'+'H'*k,data,xpos+4)
            if not (rpm[0]<=1000 and 3500<=rpm[-1]<=6500 and iq[0]<=1000 and 3000<=iq[-1]<=10000):continue
            raw=struct.unpack_from('<'+'H'*(n*k),data,m['address'])
            if max(raw)>16000:continue
            selected.append({'bank':base,'codeblock':metadata_id(data,base),'address':m['address'],'rows':n,'columns':k,
                             'name':'EGR fresh-air request (structural candidate)','minimum':min(raw)*.1,'maximum':max(raw)*.1,
                             'at_target':all(v==RAW_TARGET for v in raw)})
        if not selected:return dict(failure,reason=f'No bounded EGR request table in bank 0x{base:X}.')
        shape=[(m['address']-base,m['rows'],m['columns']) for m in selected]
        if topology is not None and shape!=topology:return dict(failure,reason='EGR map topology differs between banks.')
        topology=shape;maps.extend(selected)
        diagnostics=[r for r in all_records if r['codeblock_base']==base and r['system']=='EGR']
        current={(r['address']-base,r['vag_code']) for r in diagnostics}
        if not current or codes is not None and current!=codes:return dict(failure,reason='EGR diagnostics absent or inconsistent between banks.')
        codes=current;records.extend(diagnostics)
    enabled=sum(r['enabled'] for r in records);ready=all(m['at_target'] for m in maps) and not enabled
    return {'status':'target present' if ready else 'supported','maps':maps,'records':records,
            'maps_at_target':sum(m['at_target'] for m in maps),'enabled_records':enabled,
            'source':'GPL ZedSuite axis patterns and VAGEDCSuite EGR target; OpenCal structural guards',
            'verification':'Structural candidate; vehicle operation unverified'}
