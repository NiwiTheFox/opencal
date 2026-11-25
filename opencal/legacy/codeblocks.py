"""GPL-3.0-only. Standard V4.1 labels and bounded metadata ID reading.

ID convention adapted from ZedSuite (C) 2026 ZedPerf edc15p/layout.rs,
read_metadata_id, retained in third_party/zedsuite. Modified 2026-10-19.
"""
import re,struct
from .checksums import standard_bases
from .core import number


def metadata_id(data,base):
    from .layouts import detect
    layout=detect(data)
    if layout['generation']=='early' or base not in [b['base'] for b in layout['blocks']]:return None
    table_end,offset=struct.unpack_from('<HH',data,base+0x1000)
    if table_end==0xc3c3 or offset+2>0xc000:return None
    value=struct.unpack_from('<H',data,base+offset)[0]
    return value if 1<=value<=15 else None


def codeblock(data,m):
    address=number(m['address'])
    from .layouts import detect
    for block in detect(data)['blocks']:
        if block['start']<=address<block['end']:
            return dict(block,number=metadata_id(data,block['base']))
    return None


def map_name(data,m):
    block=codeblock(data,m)
    if block is None:return m['name']
    name=re.sub(r'\s*\[(?:codeblock\s+\d+|bank\s+[0-9a-f]+)\]\s*$','',m['name'],flags=re.I)
    name=re.sub(r'\s*@\s*[0-9a-f]{6}\s*$','',name,flags=re.I)
    label=str(block['number']) if block['number'] is not None else 'ID unknown'
    return f'{name} [codeblock {label}]'
