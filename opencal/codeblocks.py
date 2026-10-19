"""GPL-3.0-only. Standard V4.1 labels and bounded metadata ID reading.

ID convention adapted from ZedSuite (C) 2026 ZedPerf edc15p/layout.rs,
read_metadata_id, retained in third_party/zedsuite. Modified 2026-10-19.
"""
import re,struct
from .checksums import standard_bases
from .core import number


def metadata_id(data,base):
    if base not in standard_bases(data):return None
    table_end,offset=struct.unpack_from('<HH',data,base+0x1000)
    if table_end==0xc3c3 or offset+2>0xc000:return None
    value=struct.unpack_from('<H',data,base+offset)[0]
    return value if 1<=value<=15 else None


def codeblock(data,m):
    address=number(m['address'])
    for base in standard_bases(data):
        if base-0x4000<=address<base+0xc000:
            return {'number':metadata_id(data,base),'base':base,'start':base-0x4000,'end':base+0xc000}
    return None


def map_name(data,m):
    block=codeblock(data,m)
    if block is None:return m['name']
    name=re.sub(r'\s*\[(?:codeblock\s+\d+|bank\s+[0-9a-f]+)\]\s*$','',m['name'],flags=re.I)
    name=re.sub(r'\s*@\s*[0-9a-f]{6}\s*$','',name,flags=re.I)
    label=str(block['number']) if block['number'] is not None else 'ID unknown'
    return f'{name} [codeblock {label}]'
