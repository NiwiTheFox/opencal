"""GPL-3.0-only. Original OpenCal bounded AS integration and memory mapping."""
import hashlib,json,re,struct,subprocess,tempfile
from pathlib import Path
from .core import digest
from .solutions import apply_preview

CPUS=('80c166','80c167','80c167cs')
ENGINE=Path(__file__).resolve().parents[1]/'tools/c166-as'
PINNED={'asw.exe':'95e7b654977971a479631db55720edeb75aa483dde441ffc30c24169809c124a',
        'p2bin.exe':'a874c5aabe1abd6b1d3530a49b6d7ad03a8bedca9a9356d94a0fc15743726256'}
MAX_PATCH=65536


def segments(value,size):
    if not isinstance(value,list) or not value or len(value)>64:raise ValueError('Define 1..64 file/CPU segments.')
    result=[]
    for item in value:
        if not isinstance(item,dict) or any(type(item.get(k)) is not int for k in ('file','cpu','size')):raise ValueError('Segment fields must be integers.')
        f,c,n=item['file'],item['cpu'],item['size']
        if min(f,c)<0 or n<=0 or f+n>size or c+n>0x1000000 or f%2 or c%2:raise ValueError('Segment outside BIN or 24-bit CPU space, or unaligned origin.')
        for old in result:
            if f<old['file']+old['size'] and old['file']<f+n or c<old['cpu']+old['size'] and old['cpu']<c+n:raise ValueError('Segments must not overlap in file or CPU space.')
        result.append(dict(item))
    return result


def to_cpu(mapping,offset,length=1):
    for s in mapping:
        if s['file']<=offset and offset+length<=s['file']+s['size']:return s['cpu']+offset-s['file']
    raise ValueError('Selected file range is not covered by one configured CPU segment.')


def to_file(mapping,address):
    for s in mapping:
        if s['cpu']<=address<s['cpu']+s['size']:return s['file']+address-s['cpu']
    raise ValueError('Target CPU address is not mapped into this BIN.')


def literal(text):
    text=text.strip().lower()
    if re.fullmatch(r'0x[0-9a-f]+',text):return int(text,16)
    if re.fullmatch(r'[0-9][0-9a-f]*h',text):return int(text[:-1],16)
    if re.fullmatch(r'[0-9]+',text):return int(text)
    raise ValueError('Use a literal decimal, 0x hexadecimal, or AS hexadecimal h value here.')


def check_source(source,cpu):
    if cpu not in CPUS or not isinstance(source,str) or not source.strip() or len(source)>131072 or len(source.splitlines())>5000:raise ValueError('Unsupported CPU or source fragment size.')
    from .c166 import C166Disassembler
    decoder=C166Disassembler();allowed={'jmp','call','db','dw','assume'}
    for expressions in decoder.cout.values():
        for expression in expressions:
            # Derive only literal mnemonic heads; expressions are never executed.
            import ast
            first=expression
            while isinstance(first,ast.BinOp):first=first.left
            if isinstance(first,ast.Constant) and isinstance(first.value,str):allowed.add(first.value.strip().split()[0].lower())
    allowed.update(('extp','extpr','movbs','movbz'))
    labels=set()
    for number,line in enumerate(source.splitlines(),1):
        line=line.split(';',1)[0].strip()
        if not line:continue
        if not re.fullmatch(r'[A-Za-z0-9_#,+.\[\]():$ *\-/]+',line):raise ValueError(f'Line {number}: unsupported source characters; file/macro directives are not allowed.')
        m=re.match(r'^([A-Za-z_][A-Za-z0-9_]*):\s*',line)
        if m:
            label=m[1].lower()
            if label in labels:raise ValueError(f'Line {number}: duplicate label.')
            labels.add(label);line=line[m.end():]
            if not line:continue
        parts=line.split(None,1);op=parts[0].lower();operand=parts[1] if len(parts)>1 else ''
        if op not in allowed:raise ValueError(f'Line {number}: unsupported instruction/directive {op}. CPU and origin are set by the workspace; includes, macros and file access are disabled.')
        if op in ('db','dw'):
            values=operand.split(',')
            upper=255 if op=='db' else 65535
            if not operand or len(values)>MAX_PATCH or any(not 0<=literal(value)<=upper for value in values):raise ValueError('DB/DW accept bounded literal byte/word values only.')
        if op=='assume':
            if not operand:raise ValueError('ASSUME needs explicit DPP literals.')
            for setting in operand.split(','):
                match=re.fullmatch(r'\s*dpp[0-3]\s*:\s*(\S+)\s*',setting,re.I)
                if not match or not 0<=literal(match[1])<=0x3ff:raise ValueError('Only DPP0..3 literal page assumptions 0..0x3FF are supported.')
        if op in ('extp','extpr','exts','extsr'):
            operands=[s.strip() for s in operand.split(',')]
            if len(operands)!=2 or not operands[1].startswith('#') or not 1<=literal(operands[1][1:])<=4:raise ValueError('Extension count must be a literal 1..4.')
            if operands[0].startswith('#'):
                upper=0x3ff if op.startswith('extp') else 0xff
                if not 0<=literal(operands[0][1:])<=upper:raise ValueError('Extension page/segment literal is outside the processor range.')
            elif not re.fullmatch(r'r(?:[0-9]|1[0-5])',operands[0],re.I):raise ValueError('Extension uses a literal immediate or R0..R15.')
    return source


def object_bytes(blob,origin,maximum):
    """Read AS .p records; require exact contiguous code coverage before conversion."""
    if blob[:2]!=b'\x89\x14':raise ValueError('Invalid AS object header.')
    pos=2;next_address=origin;output=bytearray();ended=False
    while pos<len(blob):
        kind=blob[pos];pos+=1
        if kind==0:
            ended=True;break
        if kind==0x81:
            if pos+3>len(blob):raise ValueError('Truncated AS record.')
            cpu,section,gran=blob[pos:pos+3];pos+=3
            if (cpu,section,gran)!=(0x4c,1,1):raise ValueError('Unexpected object CPU, section or granularity.')
        elif kind==0x4c:pass
        else:raise ValueError('Unexpected AS object record type.')
        if pos+6>len(blob):raise ValueError('Truncated AS code header.')
        address,count=struct.unpack_from('<IH',blob,pos);pos+=6
        if not count or address!=next_address or pos+count>len(blob) or len(output)+count>maximum:raise ValueError('AS output contains holes, overlaps, extra regions, truncation or exceeds the patch range.')
        output.extend(blob[pos:pos+count]);pos+=count;next_address+=count
    if not ended or not output:raise ValueError('AS object is empty or unterminated.')
    return bytes(output)


def assemble(source,origin,maximum,cpu='80c167'):
    check_source(source,cpu)
    if type(origin) is not int or origin<0 or origin%2 or type(maximum) is not int or not 1<=maximum<=MAX_PATCH or origin+maximum>(0x40000 if cpu=='80c166' else 0x1000000):raise ValueError('Invalid runtime origin or overwrite capacity.')
    for name,sha in PINNED.items():
        p=ENGINE/name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('Bundled AS tool is missing or its hash differs: '+name)
    with tempfile.TemporaryDirectory(prefix='opencal-c166-') as directory:
        path=Path(directory);src=path/'patch.asm';obj=path/'patch.p';out=path/'patch.bin'
        # AS treats column-one tokens as labels. The editor accepts unindented instructions.
        normalized='\n'.join(line if re.match(r'^\s*[A-Za-z_][A-Za-z0-9_]*:',line) else ' '+line for line in source.splitlines())
        src.write_text(f' cpu {cpu}\n org 0{origin:X}h\n'+normalized+'\n',encoding='utf-8')
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        def run(args):
            try:r=subprocess.run(args,cwd=path,shell=False,capture_output=True,text=True,timeout=15,creationflags=flags)
            except subprocess.TimeoutExpired as error:raise ValueError('Assembler timed out.') from error
            if r.returncode:raise ValueError(('Assembly failed:\n'+r.stdout+r.stderr)[-16000:])
            return r
        run([str(ENGINE/'asw.exe'),str(src),'-o',str(obj),'-q','-gnuerrors','-n'])
        if not obj.exists() or obj.stat().st_size>MAX_PATCH+4096:raise ValueError('Missing or oversized AS object.')
        raw=object_bytes(obj.read_bytes(),origin,maximum)
        run([str(ENGINE/'p2bin.exe'),str(obj),str(out),'-q'])
        if not out.exists() or out.stat().st_size!=len(raw) or out.read_bytes()!=raw:raise ValueError('Converted bytes differ from validated contiguous AS records.')
        return raw


def preview(document,source,offset,maximum,mapping,cpu='80c167'):
    mapping=segments(mapping,len(document.data))
    if type(offset) is not int or type(maximum) is not int or offset<0 or offset%2 or maximum<=0 or offset+maximum>len(document.data):raise ValueError('Patch is outside BIN or unaligned.')
    origin=to_cpu(mapping,offset,maximum)
    raw=assemble(source,origin,maximum,cpu)
    if len(raw)%2:raise ValueError('Code patch must contain complete aligned instruction words.')
    before=bytes(document.data[offset:offset+len(raw)]);result=bytearray(document.data);result[offset:offset+len(raw)]=raw
    return {'schema':'opencal.patch-preview','version':1,'name':f'C166 assembly at file 0x{offset:X} / CPU 0x{origin:X}',
            'input_sha256':digest(document.data),'result_sha256':digest(result),'source_sha256':digest(source.encode('utf-8')),
            'origin':origin,'cpu':cpu,'edits':[{'address':offset,'before':before.hex(),'after':raw.hex()}] if before!=raw else [],
            'output_hex':raw.hex(),'mapping':mapping,'verification':'Synthetic engine tests; ECU execution and address mapping require independent verification.'}


def branch_target(raw,text,ea):
    raw=bytes(raw)
    if not text or text.startswith('('):return None
    if raw[0] in (0xfa,0xda) and len(raw)==4:return (raw[1]<<16)|int.from_bytes(raw[2:4],'little')
    if text.split()[0].upper() in ('JMPR','JMPA','CALLR','CALLA','JB','JNB','JBC','JNBS'):
        values=re.findall(r'0x([0-9a-fA-F]+)',text)
        if values:return int(values[-1],16)
    return None


def validate_state(state,size):
    if not isinstance(state,dict):raise ValueError('Invalid code workspace metadata.')
    if not state:return {}
    if state.get('version')!=1 or state.get('cpu') not in CPUS:raise ValueError('Unsupported code workspace version/CPU.')
    segments(state.get('segments'),size)
    if not isinstance(state.get('source'),str) or len(state['source'])>131072:raise ValueError('Invalid saved assembly source.')
    for key in ('labels','comments'):
        notes=state.setdefault(key,{})
        if not isinstance(notes,dict) or len(notes)>8192:raise ValueError('Invalid code annotations.')
        for address,text in notes.items():
            if not isinstance(address,str) or not address.isdecimal() or not 0<=int(address)<size or not isinstance(text,str) or len(text)>4096:raise ValueError('Invalid code annotation address/text.')
    return state

