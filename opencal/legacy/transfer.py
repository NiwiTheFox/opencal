"""Original OpenCal code: transfer permitted ORI metadata, never firmware bytes."""
import copy
import re
import struct
from .checksums import standard_bases
from .mappack import import_mappack,field,address


def identifiers(data):
    patterns={'ecu':rb'[0-9]{3}906[0-9]{3}[A-Z]{1,3}',
              'hardware':rb'0281[0-9]{6}','software':rb'SG\s+(\d{4})'}
    return {key:sorted(set(x.decode('ascii') for x in re.findall(pattern,data)))
            for key,pattern in patterns.items()}


def _set(entry,key,value):
    if key in entry: entry[key]=value; return
    parts=key.split('.'); obj=entry
    for part in parts[:-1]: obj=obj.setdefault(part,{})
    obj[parts[-1]]=value


def transfer_ori(original,tuned,pack):
    """Require matching bank identities and axis headers before relocation.

    Identity alone cannot prove shared layout. All explicit ROM axes must retain
    their four-byte identifier/length headers at the translated positions.
    Values may differ; instructions are never copied or modified.
    """
    source_bases=standard_bases(original); target_bases=standard_bases(tuned)
    if not source_bases or not target_bases:
        raise ValueError('ORI transfer requires supported standard EDC15 V4.1 banks.')
    expected=identifiers(original)
    if any(not values for values in expected.values()) or expected!=identifiers(tuned):
        raise ValueError('Embedded ECU, hardware and software identifiers must all match.')
    definitions,skipped=import_mappack(pack,original)
    if skipped or not definitions['maps']: raise ValueError('ORI mappack must import completely.')
    # Select one complete source bank. Never combine banks silently.
    candidates=[b for b in source_bases if all(b-0x4000<=m['address'] and
        m['address']+m['rows']*m['columns']*struct.calcsize({'u8':'B','i8':'b','u16':'H','i16':'h','u32':'I','i32':'i','f32':'f'}[m['type']])<=b+0xc000
        for m in definitions['maps'])]
    if len(candidates)!=1: raise ValueError('ORI mappack must describe one complete calibration bank.')
    base=candidates[0]; entries=[]; checked=0
    for target in target_bases:
        from .codeblocks import metadata_id
        block_id=metadata_id(tuned,target)
        block_label=str(block_id) if block_id is not None else 'ID unknown'
        if identifiers(original[base-0x4000:base+0xc000])!=identifiers(tuned[target-0x4000:target+0xc000]):
            raise ValueError('Individual bank identification differs from ORI.')
        delta=target-base
        for m in definitions['maps']:
            entry=copy.deepcopy(m['original_fields'])
            _set(entry,'Fieldvalues.StartAddr.Cpu',f'${m["address"]+delta:X}')
            for letter,key in [('X','x_axis'),('Y','y_axis')]:
                if key not in m: continue
                a=m[key]['address']; dest=a+delta
                count=m['columns'] if letter=='X' else m['rows']
                if not base-0x4000+4<=a or a+count*2>base+0xc000:
                    raise ValueError('ORI axis is outside its calibration bank.')
                if original[a-4:a]!=tuned[dest-4:dest]:
                    raise ValueError(f'Axis layout differs at 0x{dest:X}; transfer refused.')
                _set(entry,f'Axis{letter}.DataAddr.Cpu',f'${dest:X}'); checked+=1
            for key in ('Name','IdName','Fieldvalues.Name'):
                name=field(entry,key)
                if name is not None:
                    name=re.sub(r'\s*\[(?:codeblock \d+|bank [0-9a-f]+)\]','',str(name),flags=re.I)
                    _set(entry,key,f'{name} [codeblock {block_label}]')
            entry['Comment']=f'Inherited from matching ORI bank {base:05X}; destination bank {target:05X}. '+str(field(entry,'Comment',''))
            entries.append(entry)
    result={'maps':entries,'opencal_transfer':{'identifiers':expected,'source_bank':base,
            'target_banks':target_bases,'axis_headers_checked':checked,
            'verification':'identifiers and axis headers match; map semantics and execution unverified'}}
    imported,skipped=import_mappack(result,tuned,'Matching ORI mappack with bank/axis-header checks')
    if skipped or len(imported['maps'])!=len(entries): raise ValueError('Translated mappack is invalid.')
    return result
