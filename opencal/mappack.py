"""GPL-3.0-only. ZedSuite/WinOLS JSON format adapter, modified 2026-10-18.

Field conventions informed by ZedSuite mappack_import.rs and mappack-export.ts,
Copyright (C) 2026 ZedPerf and contributors. Retained in third_party/zedsuite.
No proprietary WinOLS code or database is used. Raw contiguous storage only.
"""
import math
import struct
from .core import validate_definitions


def decode_json(raw):
    """Upstream serializeWinolsMappack deliberately emits Latin-1 JSON."""
    try:
        text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text=raw.decode('latin-1')
    import json
    return json.loads(text)


def field(obj,key,default=None):
    if key in obj: return obj[key]
    cur=obj
    for part in key.split('.'):
        if not isinstance(cur,dict) or part not in cur: return default
        cur=cur[part]
    return cur


def address(value):
    if type(value) is int and value>=0: return value
    if isinstance(value,str):
        s=value.strip()
        if s.startswith('$'): return int(s[1:].removeprefix('0x'),16)
        if s.lower().startswith('0x'): return int(s,16)
        return int(s,10)  # Never guess that an ambiguous string is hexadecimal.
    raise ValueError('Invalid integer address.')


def numeric(value):
    n=float(str(value).replace(',','.'))
    if not math.isfinite(n): raise ValueError('Nonfinite numeric field.')
    return n


def data_org(value,signed=False):
    org=str(value).lower().removeprefix('e')
    options={'byte':('u8','B','little'),'lohi':('u16','H','little'),'hilo':('u16','H','big'),
             'lohilohi':('u32','I','little'),'hilohilo':('u32','I','big'),
             'float':('f32','f','little'),'floatlohi':('f32','f','little'),'floathilo':('f32','f','big')}
    if org not in options: raise ValueError('Unsupported DataOrg.')
    dtype,fmt,endian=options[org]
    if signed and dtype!='f32': dtype='i'+dtype[1:]; fmt=fmt.lower()
    return dtype,('<' if endian=='little' else '>')+fmt,endian


def truth(value):
    return str(value).lower() in ('true','1')


def import_mappack(obj,data,source='User-supplied ZedSuite/WinOLS JSON'):
    entries=obj if isinstance(obj,list) else obj.get('maps',obj.get('Maps')) if isinstance(obj,dict) else None
    if not isinstance(entries,list): raise ValueError('No supported map list in JSON.')
    maps=[]; skipped=[]
    for index,entry in enumerate(entries):
        try:
            if not isinstance(entry,dict): raise ValueError('Map must be an object.')
            get=lambda k,d=None:field(entry,k,d)
            name=get('Name',get('name'))
            if not isinstance(name,str) or not name.strip(): raise ValueError('Missing map name.')
            a=address(get('Fieldvalues.StartAddr.Cpu',get('address')))
            rows,cols=numeric(get('Rows',1)),numeric(get('Columns',1))
            if rows!=int(rows) or cols!=int(cols): raise ValueError('Noninteger grid dimension.')
            for key in ('SkipBytes','LineSkipBytes','bReciprocal','bDelta','bPercent'):
                if numeric(get(key,0))!=0: raise ValueError(f'Unsupported {key}.')
            dtype,fmt,endian=data_org(get('DataOrg','eLoHi'),truth(get('bSigned',False)))
            m={'id':f'imported-{index}-{a:x}','name':name,'address':a,'rows':int(rows),'columns':int(cols),'type':dtype,'endian':endian,
               'factor':numeric(get('Fieldvalues.Factor',1)),'offset':numeric(get('Fieldvalues.Offset',0)),
               'unit':str(get('Fieldvalues.Unit','')),'category':str(get('FolderName','Imported')),
               'verification':'candidate','source':source,'license':str(get('license','Redistribution rights not established by importer')),
               'description':str(get('Comment','')),'import_format':'ZedSuite/WinOLS dotted JSON',
               'original_fields':entry}
            # Validate table before allocating axis values.
            validate_definitions({'schema':'opencal.definitions','version':1,'maps':[m]},len(data))
            for letter,key,count in [('X','x_axis',m['columns']),('Y','y_axis',m['rows'])]:
                raw=get(f'Axis{letter}.DataAddr.Cpu')
                if raw is None or count<=1: continue
                axis_address=address(raw)
                if axis_address==0: continue
                if get(f'Axis{letter}.DataSrc','eRom')!='eRom': raise ValueError('Only ROM axes are supported.')
                _,axis_fmt,_=data_org(get(f'Axis{letter}.DataOrg','eLoHi'),truth(get(f'Axis{letter}.bSigned',False)))
                width=struct.calcsize(axis_fmt)
                if axis_address<0 or axis_address+count*width>len(data): raise ValueError('Axis outside binary.')
                factor=numeric(get(f'Axis{letter}.Factor',1)); offset=numeric(get(f'Axis{letter}.Offset',0))
                values=[struct.unpack_from(axis_fmt,data,axis_address+i*width)[0]*factor+offset for i in range(count)]
                m[key]={'address':axis_address,'values':values,'name':str(get(f'Axis{letter}.Name','')),
                        'unit':str(get(f'Axis{letter}.Unit','')),'display_backwards':truth(get(f'Axis{letter}.bBackwards',False))}
            validate_definitions({'schema':'opencal.definitions','version':1,'maps':[m]},len(data))
            maps.append(m)
        except (ValueError,TypeError,KeyError,OverflowError,struct.error) as exc:
            skipped.append({'index':index,'reason':str(exc)})
    if not maps: raise ValueError('No supported maps: '+str(skipped[:5]))
    return {'schema':'opencal.definitions','version':1,'maps':maps,'signatures':[]},skipped
