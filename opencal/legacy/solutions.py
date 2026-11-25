"""GPL-3.0-only. Adapted from ZedSuite (C) 2026 ZedPerf, solutions/index.ts
and detector/ecu/bosch/launch_control.rs. Modified 2026-10-18 for OpenCal.

Only bounded standard V4.1 EDC15 layouts are enabled. Byte-level reproduction
does not verify vehicle execution. No instruction patch or switching code.
"""
import re,struct
from .checksums import standard_bases
from .core import digest,validate_definitions

SPEED_STEPS=tuple(range(0,261,20))
AXIS=struct.pack('<15H',14,*SPEED_STEPS)
SOURCE='ZedSuite GPL-3.0-only solutions/index.ts and launch_control.rs; bounded OpenCal port'


def launch_control_state(data,reference=None):
    bases=standard_bases(data)
    if not bases: return {'status':'unsupported','sites':[],'reason':'Requires a supported standard V4.1 layout.'}
    sites=[]
    for base in bases:
        start,end=base-0x4000,base+0xc000
        candidates={}
        for match in re.finditer(rb'[\s\S]{2}\x02\x00\x80\x00\x00\x0a[\s\S]{2}\x02\x00\x00\x00\x70\x17',data[start:end]):
            candidates[start+match.start()]='available'
        for header in (AXIS,b'\x00\x0e'+AXIS[2:]):
            for match in re.finditer(re.escape(header),data[start:end]): candidates[start+match.start()-2]='active'
        anchored=set()
        if reference is not None and len(reference)==len(data) and standard_bases(reference)==bases:
            for site in launch_control_state(reference)['sites']:
                sig=site['signature']
                if site['bank']==base and data[sig+2:sig+4] in (b'\x0e\x00',b'\x00\x0e'):
                    anchored.add(sig)
                    candidates.setdefault(sig,'custom')
        for sig,status in sorted(candidates.items()):
            if sig<start or sig+786>end: continue
            rpm=struct.unpack_from('<25H',data,sig+36)
            if sig not in anchored and (not all(a<=b for a,b in zip(rpm,rpm[1:])) or not 2500<=max(rpm)<=7000 or rpm[0]>2000): continue
            sites.append({'signature':sig,'axis_address':sig+2,'map_address':sig+86,'bank':base,'status':status})
    statuses={s['status'] for s in sites}
    state='mixed' if len(statuses)>1 else next(iter(statuses),'not found')
    return {'status':state,'sites':sites,'source':SOURCE,'verification':'Source-backed byte pattern; ECU execution unverified'}


def launch_control_maps(data,reference=None):
    maps=[]
    for site in launch_control_state(data,reference)['sites']:
        if site['status'] not in ('active','custom'): continue
        sig=site['signature']; a=site['map_address']
        maps.append({'id':f'launch-control-{a:x}','name':f'Launch control map [bank {site["bank"]:05X}]',
            'address':a,'rows':14,'columns':25,'type':'u16','endian':'little','factor':.01,'offset':0,
            'unit':'mg/st','category':'Launch control','verification':'candidate','source':SOURCE,'license':'GPL-3.0-only',
            'x_axis':{'address':sig+36,'type':'u16','endian':'little','factor':1,'offset':0,'values':list(struct.unpack_from('<25H',data,sig+36)),'name':'Engine speed','unit':'rpm'},
            'y_axis':{'address':sig+4,'type':'u16','endian':'little','factor':.15625,'offset':0,'values':[v*.15625 for v in struct.unpack_from('<14H',data,sig+4)],'name':'Vehicle speed','unit':'km/h','display_backwards':True},
            'evidence':'Exact 14-step speed axis and bounded map/RPM structure; no on-vehicle verification.'})
    return maps


def preview_launch_control(data,restore_from=None,reference=None):
    state=launch_control_state(data,restore_from if restore_from is not None else reference)
    if not state['sites']: raise ValueError('No supported launch-control structure was found.')
    edits=[]
    if restore_from is not None:
        if len(restore_from)!=len(data) or standard_bases(restore_from)!=standard_bases(data): raise ValueError('Original layout differs.')
        original={s['signature']:s for s in launch_control_state(restore_from)['sites']}
    for site in state['sites']:
        a=site['axis_address']
        if restore_from is None:
            if site['status']!='available': continue
            after=AXIS
        else:
            if site['signature'] not in original: raise ValueError('Original launch-control structure does not match.')
            after=bytes(restore_from[a:a+30])
        before=bytes(data[a:a+30])
        if before!=after: edits.append({'address':a,'before':before.hex(),'after':after.hex(),'bank':site['bank']})
    result=bytearray(data)
    for edit in edits:
        a=edit['address']; result[a:a+30]=bytes.fromhex(edit['after'])
    validate_definitions({'schema':'opencal.definitions','version':1,'maps':launch_control_maps(result)},len(data))
    return {'schema':'opencal.patch-preview','version':1,'name':'Restore original launch-control axis' if restore_from is not None else 'Enable launch-control speed axis',
            'input_sha256':digest(data),'result_sha256':digest(result),'edits':edits,
            'verification':'Byte-level source port only; not on-vehicle validated'}


def apply_preview(document,preview):
    if digest(document.data)!=preview['input_sha256']: raise ValueError('BIN changed after preview. Inspect the solution again.')
    result=bytearray(document.data)
    for edit in preview['edits']:
        a=edit['address']; before=bytes.fromhex(edit['before']); after=bytes.fromhex(edit['after'])
        if len(before)!=len(after) or a<0 or a+len(before)>len(result) or bytes(result[a:a+len(before)])!=before: raise ValueError('Patch precondition failed.')
        result[a:a+len(after)]=after
    if digest(result)!=preview['result_sha256']: raise ValueError('Patch result integrity failed.')
    if preview['edits']:
        # A single history operation makes all banks one reversible change.
        first=min(e['address'] for e in preview['edits']); last=max(e['address']+len(bytes.fromhex(e['after'])) for e in preview['edits'])
        document.edit(first,result[first:last],preview['name'])
