"""Read-only C166 banking evidence. Original implementation, GPL-3.0-only.

Uses documented MOV reg,#data16 and CALLS encodings, not proprietary EXE code.
Raw matches are not a control-flow disassembly or proof of functioning switching.
"""
from .checksums import standard_bases


def inspect_multimap(data):
    if len(data)!=0x80000:
        return {'status':'unverified','reason':'Only 512 KiB raw images are inspected.','groups':[]}
    triplets=[]
    for page in (0x34,0x38,0x3c):
        pattern=b''.join(bytes((0xe6,reg,page+reg,0)) for reg in range(3))
        pos=0
        while True:
            pos=data.find(pattern,pos)
            if pos<0: break
            if pos%2==0: triplets.append({'offset':pos,'pages':[page,page+1,page+2]})
            pos+=1
    triplets.sort(key=lambda x:x['offset'])
    groups=[]
    for triple in triplets:
        if not groups or triple['offset']-groups[-1]['triplets'][-1]['offset']>512:
            groups.append({'triplets':[]})
        groups[-1]['triplets'].append(triple)
    for group in groups:
        low=group['triplets'][0]['offset']; high=group['triplets'][-1]['offset']+12
        # ROM alias 0x80000 is an explicit hypothesis from this ECU research, not universal.
        refs=[]
        for pos in range(0,len(data)-3,2):
            if data[pos]!=0xda: continue
            target=(data[pos+1]<<16)|int.from_bytes(data[pos+2:pos+4],'little')
            offset=target-0x80000
            if max(0,low-512)<=offset<=high:
                refs.append({'call_offset':pos,'target_cpu_address':target,'target_file_offset_hypothesis':offset})
        group['far_call_candidates']=refs[:100]
        group['multiple_page_sets']=len({tuple(t['pages']) for t in group['triplets']})>1
    return {'status':'candidate evidence only','recognised_codeblock_bases':standard_bases(data),
            'groups':groups,'reason':'Raw aligned byte patterns; instruction boundaries, reachability, RAM usage, inputs and switching operation are unverified. Multiple calibration banks alone do not establish multimap.',
            'rom_alias_hypothesis':0x80000}
