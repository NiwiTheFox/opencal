"""Original OpenCal batch editing. Previews validate every cell before mutation."""
import csv,io,json,math,struct
from .core import map_values,encode_map_value,TYPES,number,digest,axis_values,validate_definitions
from .solutions import apply_preview


def definitions_hash(defs):return digest(json.dumps(defs,sort_keys=True,allow_nan=False).encode())


def value_preview(data,m,values,indexes=None,name='Edit map values',definitions=None):
    validate_definitions({'schema':'opencal.definitions','version':1,'maps':[m]},len(data))
    indexes=list(range(m['rows']*m['columns'])) if indexes is None else list(indexes)
    if len(values)!=len(indexes) or len(set(indexes))!=len(indexes):raise ValueError('Value count or cell selection is invalid.')
    width=struct.calcsize(TYPES[m['type']]);result=bytearray(data);edits=[];cells=[]
    old=map_values(data,m)
    for index,value in zip(indexes,values):
        if type(index) is not int or not 0<=index<len(old):raise ValueError('Cell selection is outside this map.')
        encoded=encode_map_value(m,value);a=number(m['address'])+index*width;before=bytes(data[a:a+width])
        if len(before)!=width:raise ValueError('Map extends outside the BIN.')
        if before==encoded:continue
        result[a:a+width]=encoded
        stored=struct.unpack(('<' if m['endian']=='little' else '>')+TYPES[m['type']],encoded)[0]*m['factor']+m['offset']
        edits.append({'address':a,'before':before.hex(),'after':encoded.hex()})
        cells.append({'row':index//m['columns']+1,'column':index%m['columns']+1,'before':old[index],'after':stored})
    preview={'schema':'opencal.patch-preview','version':1,'name':name,'input_sha256':digest(data),'result_sha256':digest(result),
             'edits':edits,'cells':cells,'map_name':m['name'],'unit':m['unit']}
    if definitions is not None:preview['definitions_sha256']=definitions_hash(definitions)
    return preview


def operation_preview(data,m,operation,amount=0,indexes=None,original=None,definitions=None):
    indexes=list(range(m['rows']*m['columns'])) if indexes is None else list(indexes)
    old=map_values(data,m)
    if any(type(i) is not int or not 0<=i<len(old) for i in indexes):raise ValueError('Invalid cell selection.')
    if not isinstance(amount,(int,float)) or not math.isfinite(amount):raise ValueError('Enter a finite amount.')
    if operation=='Set':values=[amount for _ in indexes]
    elif operation=='Add':values=[old[i]+amount for i in indexes]
    elif operation=='Percent':values=[old[i]*(1+amount/100) for i in indexes]
    elif operation=='Restore original':
        if original is None or len(original)!=len(data):raise ValueError('Matching original is required.')
        orig=map_values(original,m);values=[orig[i] for i in indexes]
    else:raise ValueError('Unsupported table operation.')
    return value_preview(data,m,values,indexes,operation+' · '+m['name'],definitions)


def axis_preview(data,m,key,values,definitions):
    if key not in ('x_axis','y_axis') or key not in m:raise ValueError('This map has no ROM axis on that side.')
    axis_values(data,m,key,strict=True)
    axis=m[key]
    if 'address' not in axis or 'type' not in axis:raise ValueError('This axis has display labels only; ROM storage is not defined.')
    count=m['columns'] if key=='x_axis' else m['rows']
    view={k:v for k,v in m.items() if k not in ('x_axis','y_axis','minimum','maximum')}
    view.update({k:axis[k] for k in ('address','type','endian','factor','offset')})
    view.update(rows=1,columns=count,name=m['name']+' · '+key[0].upper()+' axis',unit=axis.get('unit',''))
    if len(values)!=count:raise ValueError(f'Expected {count} axis values.')
    preview=value_preview(data,view,values,name='Edit '+view['name'],definitions=definitions)
    start=number(axis['address']);end=start+count*struct.calcsize(TYPES[axis['type']])
    shared=[]
    for other in definitions['maps']:
        ranges=[(number(other['address']),other['rows']*other['columns']*struct.calcsize(TYPES[other['type']]))]
        for side,n in [('x_axis',other['columns']),('y_axis',other['rows'])]:
            a=other.get(side,{})
            if 'address' in a and 'type' in a:ranges.append((number(a['address']),n*struct.calcsize(TYPES[a['type']])))
        if any(a<end and a+length>start for a,length in ranges):shared.append(other['name'])
    preview['shared_maps']=shared
    return preview


def csv_preview(data,m,text,definitions=None):
    if len(text)>8*1024*1024:raise ValueError('CSV is too large.')
    rows=list(csv.reader(io.StringIO(text)))
    if len(rows)!=m['rows'] or any(len(row)!=m['columns'] for row in rows):raise ValueError(f'Expected exactly {m["rows"]} rows and {m["columns"]} numeric columns, without headers.')
    try:values=[float(value.strip()) for row in rows for value in row]
    except ValueError as exc:raise ValueError('CSV must contain numeric physical values only.') from exc
    return value_preview(data,m,values,name='Import CSV · '+m['name'],definitions=definitions)


def apply_table_preview(document,preview):
    if 'definitions_sha256' in preview and definitions_hash(document.definitions)!=preview['definitions_sha256']:
        raise ValueError('Definitions changed after preview. Review the operation again.')
    apply_preview(document,preview)


def interpolation_preview(data,m,rows=None,definitions=None):
    old=map_values(data,m);values=old.copy()
    def weights(key,count):
        v=axis_values(data,m,key,strict=True)
        monotonic=all(a<b for a,b in zip(v,v[1:])) or all(a>b for a,b in zip(v,v[1:]))
        return [(x-v[0])/(v[-1]-v[0]) for x in v] if count>1 and monotonic and v[-1]!=v[0] else [i/max(1,count-1) for i in range(count)]
    if m['columns']==1:
        if rows is not None:raise ValueError('Use whole-map interpolation for a single column.')
        for i,w in enumerate(weights('y_axis',m['rows'])):values[i]=old[0]+(old[-1]-old[0])*w
        indexes=list(range(len(old)))
    else:
        rows=list(range(m['rows'])) if rows is None else list(rows)
        if any(type(r) is not int or not 0<=r<m['rows'] for r in rows):raise ValueError('Invalid row selection.')
        indexes=[];ws=weights('x_axis',m['columns'])
        for r in rows:
            a=r*m['columns'];first,last=old[a],old[a+m['columns']-1]
            for c,w in enumerate(ws):values[a+c]=first+(last-first)*w;indexes.append(a+c)
    return value_preview(data,m,[values[i] for i in indexes],indexes,'Interpolate endpoints · '+m['name'],definitions)


def bank_copy_preview(data,m,definitions):
    from .checksums import standard_bases
    bases=standard_bases(data);base=next((b for b in bases if b-0x4000<=number(m['address'])<b+0xc000),None)
    size=m['rows']*m['columns']*struct.calcsize(TYPES[m['type']])
    if base is None or number(m['address'])+size>base+0xc000:raise ValueError('This map is outside supported calibration banks.')
    by_address={}
    for candidate in definitions['maps']:by_address.setdefault(number(candidate['address']),[]).append(candidate)
    previews=[];attrs=('rows','columns','type','endian','factor','offset','unit')
    for target in bases:
        if target==base:continue
        matches=by_address.get(number(m['address'])+target-base,[])
        if len(matches)!=1:raise ValueError(f'Matching map definition is missing or ambiguous in bank {target:05X}.')
        dest=matches[0]
        if any(dest[k]!=m[k] for k in attrs):raise ValueError(f'Matching map definition differs in bank {target:05X}.')
        for key,count in [('x_axis',m['columns']),('y_axis',m['rows'])]:
            a,b=m.get(key),dest.get(key)
            if bool(a)!=bool(b):raise ValueError('Destination axis definition differs.')
            if not a:continue
            axis_values(data,m,key,strict=True);axis_values(data,dest,key,strict=True)
            if 'type' not in a or 'type' not in b or 'address' not in a or 'address' not in b:raise ValueError('Bank copying requires explicit ROM axis storage.')
            if any(a.get(k)!=b.get(k) for k in ('type','endian','factor','offset','unit')):raise ValueError('Destination axis encoding or units differ.')
            width=struct.calcsize(TYPES[a['type']]);aa,bb=number(a['address']),number(b['address'])
            if bb-aa!=target-base:raise ValueError('Destination axis offset differs.')
            if not base-0x4000+4<=aa or aa+count*width>base+0xc000 or not target-0x4000+4<=bb or bb+count*width>target+0xc000:raise ValueError('Axis is outside its calibration bank.')
            if data[aa-4:aa+count*width]!=data[bb-4:bb+count*width]:raise ValueError('Bank axis headers or current values differ; copying refused.')
        previews.append(value_preview(data,dest,map_values(data,m),name='Copy matching bank'))
    if not previews:raise ValueError('No other supported calibration bank is present.')
    result=bytearray(data);edits=[]
    for preview in previews:
        for edit in preview['edits']:
            a=edit['address'];after=bytes.fromhex(edit['after']);result[a:a+len(after)]=after;edits.append(edit)
    return {'schema':'opencal.patch-preview','version':1,'name':'Copy map to matching banks · '+m['name'],
        'input_sha256':digest(data),'result_sha256':digest(result),'edits':edits,'cells':[],
        'definitions_sha256':definitions_hash(definitions),'destination_banks':len(previews)}
