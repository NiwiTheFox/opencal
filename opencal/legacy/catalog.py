"""Versioned reference profiles learned from permitted, provenance-bearing mappacks.

Profiles contain map metadata and hashes, never firmware payloads. Match the code,
axes and identification bytes; mask only declared editable cells/checksum/DTC state.
This establishes layout equivalence, not correctness of source map semantics.
"""
import copy
import hashlib
import json
import struct
from pathlib import Path
from .core import validate_definitions
from .mappack import import_mappack

CATALOG=Path(__file__).parent/'data/reference-profiles.json'


def merged_ranges(ranges,size):
    result=[]
    for start,end in sorted(ranges):
        if type(start) is not int or type(end) is not int or not 0<=start<end<=size:
            raise ValueError('Invalid profile masking range.')
        if result and start<=result[-1][1]: result[-1][1]=max(end,result[-1][1])
        else: result.append([start,end])
    return result


def masked_hash(data,ranges):
    copy=bytearray(data)
    for start,end in merged_ranges(ranges,len(data)): copy[start:end]=bytes(end-start)
    return hashlib.sha256(copy).hexdigest()


def make_profile(data,pack,name,provenance):
    from .checksums import inspect
    from .edc15 import dtc_records
    definitions,skipped=import_mappack(pack,data,provenance)
    if skipped: raise ValueError(f'Cannot learn partial mappack: {skipped[:3]}')
    ranges=[]
    for m in definitions['maps']:
        width=struct.calcsize({'u8':'B','i8':'b','u16':'H','i16':'h','u32':'I','i32':'i','f32':'f'}[m['type']])
        ranges.append((m['address'],m['address']+m['rows']*m['columns']*width))
    checksum=inspect(data)
    for region in checksum.get('regions',[]): ranges.append((region['store'],region['store']+4))
    try:
        for record in dtc_records(data): ranges.append((record['address'],record['address']+5))
    except ValueError: pass
    ranges=merged_ranges(ranges,len(data))
    if sum(b-a for a,b in ranges)>len(data)//2:
        raise ValueError('Profile masks too much data to establish layout equivalence.')
    return {'schema':'opencal.reference-profile','version':1,'name':name,'size':len(data),
            'source_sha256':hashlib.sha256(data).hexdigest(),'masked_sha256':masked_hash(data,ranges),
            'mask_ranges':ranges,'mappack':pack,'provenance':provenance,
            'status':'reference-derived; semantics unverified'}


def match_profile(data,profiles=None):
    if profiles is None:
        if not CATALOG.exists(): return None
        profiles=json.loads(CATALOG.read_text(encoding='utf-8'))['profiles']
    for profile in profiles:
        if profile.get('schema')!='opencal.reference-profile' or profile.get('version')!=1 or profile['size']!=len(data): continue
        if masked_hash(data,profile['mask_ranges'])!=profile['masked_sha256']: continue
        definitions,skipped=import_mappack(profile['mappack'],data,profile['provenance'])
        if skipped: continue
        for m in definitions['maps']:
            m['evidence']='Code/axes/identification fingerprint matches learned reference; calibration cells, checksum fields and DTC state excluded.'
            m['reference_profile']=profile['name']
        definitions['detection']={'method':'reference-profile','name':profile['name'],'source':profile['provenance'],
                                 'reference_sha256':profile['source_sha256'],'map_count':len(definitions['maps']),
                                 'verification':'reference-derived candidates; not on-vehicle verified'}
        return validate_definitions(definitions,len(data))
    return None
