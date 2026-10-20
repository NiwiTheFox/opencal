"""Read-only comparison model with explicit compatible-bank map matching."""
import copy,struct
from .core import TYPES,number
from .checksums import standard_bases
from .transfer import identifiers
from .codeblocks import codeblock,metadata_id


def _signature_match(data,definitions):
    signatures=definitions.get('signatures',[])
    if not signatures:return False
    for sig in signatures:
        try:
            expected=bytes.fromhex(sig['hex']);offset=number(sig['address'])
        except (KeyError,TypeError,ValueError):return False
        if not expected or offset<0 or bytes(data[offset:offset+len(expected)])!=expected:return False
    return True


def reference_map(current,reference,m,definitions):
    """Return a relocated metadata copy, never copy table bytes or edit inputs."""
    width=struct.calcsize(TYPES[m['type']]);size=width*m['rows']*m['columns'];address=number(m['address'])
    bases=standard_bases(reference);block=codeblock(current,m)
    if block and bases:
        expected=identifiers(current)
        if any(not v for v in expected.values()) or expected!=identifiers(reference):return None,'ECU/hardware/software identifiers differ or are missing'
        base=block['base'];candidates=[]
        for other in bases:
            delta=other-base;dest=address+delta
            if not other-0x4000<=dest or dest+size>other+0xc000:continue
            if identifiers(current[base-0x4000:base+0xc000])!=identifiers(reference[other-0x4000:other+0xc000]):continue
            axes=True
            for key,count in (('x_axis',m['columns']),('y_axis',m['rows'])):
                axis=m.get(key,{})
                if 'address' not in axis:continue
                a=number(axis['address']);w=struct.calcsize(TYPES[axis.get('type','u16')])
                if a-4<base-0x4000 or a+count*w>base+0xc000 or bytes(current[a-4:a])!=bytes(reference[a+delta-4:a+delta]):axes=False;break
            if axes:candidates.append(other)
        if not candidates:return None,'No compatible reference bank/axis headers'
        exact=[b for b in candidates if block['number'] is not None and metadata_id(reference,b)==block['number']]
        if len(exact)==1:candidates=exact
        elif base in candidates:candidates=[base]
        if len(candidates)!=1:return None,'Multiple compatible reference banks; match is ambiguous'
        delta=candidates[0]-base;reason=f'Matching IDs and axis headers · reference bank 0x{candidates[0]:05X}'
    elif m.get('verification')=='synthetic' and _signature_match(current,definitions) and _signature_match(reference,definitions):
        delta=0;reason='Synthetic fixture with matching explicit signatures'
    else:return None,'No verified compatible map layout; raw hex comparison is available'
    if address+delta<0 or address+delta+size>len(reference):return None,'Map extends beyond reference file'
    result=copy.deepcopy(m);result['address']=address+delta
    for key in ('x_axis','y_axis'):
        if 'address' in result.get(key,{}):
            axis=result[key];axis['address']=number(axis['address'])+delta
            count=m['columns'] if key=='x_axis' else m['rows']
            if axis['address']<0 or axis['address']+count*struct.calcsize(TYPES[axis.get('type','u16')])>len(reference):return None,'Axis extends beyond reference file'
    if 'codeblock_base' in result:result['codeblock_base']+=delta
    return result,reason


def map_difference(current,reference,m,other):
    width=struct.calcsize(TYPES[m['type']]);a=number(m['address']);b=number(other['address'])
    cells=[i for i in range(m['rows']*m['columns']) if bytes(current[a+i*width:a+(i+1)*width])!=bytes(reference[b+i*width:b+(i+1)*width])]
    axes={}
    for key,count in (('x_axis',m['columns']),('y_axis',m['rows'])):
        axis=m.get(key,{})
        if 'address' not in axis:continue
        w=struct.calcsize(TYPES[axis.get('type','u16')]);a=number(axis['address']);b=number(other[key]['address'])
        changed=[i for i in range(count) if bytes(current[a+i*w:a+(i+1)*w])!=bytes(reference[b+i*w:b+(i+1)*w])]
        if changed:axes[key]=changed
    return cells,axes


def changed_maps(current,reference,definitions):
    changed=[];unmatched=[];matched=0
    for index,m in enumerate(definitions['maps']):
        other,reason=reference_map(current,reference,m,definitions)
        if other is None:unmatched.append({'index':index,'reason':reason});continue
        matched+=1;cells,axes=map_difference(current,reference,m,other)
        if cells or axes:changed.append({'index':index,'id':m['id'],'map':m,'reference_map':other,'cells':cells,'axes':axes,'reason':reason})
    return {'changed':changed,'unmatched':unmatched,'matched':matched}
