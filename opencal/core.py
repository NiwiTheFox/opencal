"""Independent binary model. No reference executable code or definitions."""
import base64
import hashlib
import json
import math
import os
import struct
from pathlib import Path

MAX_FILE = 32 * 1024 * 1024
TYPES = {'u8': 'B', 'i8': 'b', 'u16': 'H', 'i16': 'h', 'u32': 'I', 'i32': 'i', 'f32': 'f'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_binary(path):
    p = Path(path)
    if not 0 < p.stat().st_size <= MAX_FILE:
        raise ValueError('Expected a nonempty file of at most 32 MiB.')
    data = p.read_bytes()
    if not 0 < len(data) <= MAX_FILE:
        raise ValueError('File size changed while reading.')
    return data


def number(value):
    if isinstance(value, str):
        return int(value, 0)
    if type(value) is not int:
        raise ValueError('Address must be an integer or 0x hexadecimal string.')
    return value


def differences(left, right):
    """Half-open contiguous byte ranges, including length differences."""
    start = None
    for i in range(max(len(left), len(right))):
        changed = i >= min(len(left), len(right)) or left[i] != right[i]
        if changed and start is None:
            start = i
        if not changed and start is not None:
            yield start, i
            start = None
    if start is not None:
        yield start, max(len(left), len(right))


def validate_definitions(doc, size):
    if not isinstance(doc, dict) or doc.get('schema') != 'opencal.definitions' or doc.get('version') != 1:
        raise ValueError('Unsupported definition schema/version.')
    if not isinstance(doc.get('maps'), list) or not isinstance(doc.get('signatures', []), list):
        raise ValueError('maps and signatures must be arrays.')
    ids = set()
    for m in doc['maps']:
        for key in ('id', 'name', 'address', 'rows', 'columns', 'type', 'endian', 'factor', 'offset', 'unit', 'category', 'verification', 'source', 'license'):
            if key not in m:
                raise ValueError(f'Map missing {key}')
        if not isinstance(m['id'], str) or not m['id'] or m['id'] in ids:
            raise ValueError('Map IDs must be unique nonempty strings.')
        ids.add(m['id'])
        if m['type'] not in TYPES or m['endian'] not in ('little', 'big'):
            raise ValueError('Unsupported type or byte order.')
        if m['verification'] not in ('synthetic', 'candidate', 'verified'):
            raise ValueError('Invalid verification status.')
        for key in ('factor', 'offset'):
            if not isinstance(m[key], (int, float)) or not math.isfinite(m[key]):
                raise ValueError('Scaling must be finite.')
        if m['factor'] == 0:
            raise ValueError('Scaling factor cannot be zero.')
        for key in ('rows', 'columns'):
            if type(m[key]) is not int or not 1 <= m[key] <= 1024:
                raise ValueError('Dimensions must be integers from 1 to 1024.')
        address = number(m['address'])
        length = m['rows'] * m['columns'] * struct.calcsize(TYPES[m['type']])
        if address < 0 or address + length > size:
            raise ValueError(f'Map {m["id"]} is outside this binary.')
        if not m['source'] or not m['license']:
            raise ValueError('Source and license are required.')
        for key in ('minimum', 'maximum'):
            if key in m and not math.isfinite(m[key]):
                raise ValueError('Map limits must be finite.')
        if m.get('minimum', -math.inf) > m.get('maximum', math.inf):
            raise ValueError('Reversed map limits.')
        for key, count in (('x_axis', m['columns']), ('y_axis', m['rows'])):
            if key in m:
                axis = m[key]
                if not isinstance(axis, dict) or len(axis.get('values', [])) != count:
                    raise ValueError('Axis values must match map dimensions.')
                if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in axis['values']):
                    raise ValueError('Axis values must be finite numbers.')
                if 'type' in axis:
                    if axis['type'] not in TYPES or axis.get('endian') not in ('little','big'):
                        raise ValueError('Unsupported axis storage type or byte order.')
                    for field in ('factor','offset'):
                        if not isinstance(axis.get(field),(int,float)) or not math.isfinite(axis[field]):
                            raise ValueError('Axis scaling must be finite.')
                    if axis['factor']==0: raise ValueError('Axis factor cannot be zero.')
                    a=number(axis.get('address',-1)); width=struct.calcsize(TYPES[axis['type']])
                    if a<0 or a+count*width>size: raise ValueError('Axis is outside the binary.')
    for s in doc.get('signatures', []):
        if not all(k in s for k in ('family', 'name', 'address', 'hex', 'source', 'license')):
            raise ValueError('Incomplete identification signature.')
        pattern = bytes.fromhex(s['hex'])
        if not pattern or number(s['address']) < 0:
            raise ValueError('Invalid signature.')
    return doc


def map_values(data, m):
    fmt = ('<' if m['endian'] == 'little' else '>') + TYPES[m['type']]
    width = struct.calcsize(fmt)
    return [struct.unpack_from(fmt, data, number(m['address']) + i * width)[0] * m['factor'] + m['offset']
            for i in range(m['rows'] * m['columns'])]


def encode_map_value(m,physical):
    if not isinstance(physical,(int,float)) or not math.isfinite(physical):
        raise ValueError('Map values must be finite numbers.')
    if not m.get('minimum',-math.inf)<=physical<=m.get('maximum',math.inf):
        raise ValueError('Value outside definition limits.')
    raw=(physical-m['offset'])/m['factor']
    if not math.isfinite(raw): raise ValueError('Value cannot be represented with this scaling.')
    if m['type']!='f32': raw=round(raw)
    fmt=('<' if m['endian']=='little' else '>')+TYPES[m['type']]
    try:
        encoded=struct.pack(fmt,raw)
        stored=struct.unpack(fmt,encoded)[0]*m['factor']+m['offset']
        if not math.isfinite(stored): raise ValueError('Stored value must remain finite.')
        if not m.get('minimum',-math.inf)<=stored<=m.get('maximum',math.inf):
            raise ValueError('Rounded stored value is outside definition limits.')
        return encoded
    except (struct.error,OverflowError) as exc:
        raise ValueError(f'Value cannot be stored as {m["type"]}.') from exc


def axis_values(data,m,key,strict=False):
    """Decode live ROM axes when storage is known; retain legacy display labels."""
    axis=m.get(key)
    count=m['columns'] if key=='x_axis' else m['rows']
    if not axis: return list(range(1,count+1))
    if 'type' not in axis:
        if strict and 'address' in axis:
            raise ValueError('Reimport this mappack or detect maps again to obtain editable axis storage.')
        return list(axis['values'])
    view=dict(axis,rows=1,columns=count)
    return map_values(data,view)


def refresh_axes(data,definitions):
    for m in definitions['maps']:
        for key in ('x_axis','y_axis'):
            if 'type' in m.get(key,{}): m[key]['values']=axis_values(data,m,key)


def identify(data, definitions):
    found = []
    for s in definitions.get('signatures', []):
        address = number(s['address']); pattern = bytes.fromhex(s['hex'])
        if data[address:address + len(pattern)] == pattern:
            found.append({'family': s['family'], 'name': s['name'], 'confidence': 'signature match; coverage depends on definition provenance',
                          'evidence': f'{len(pattern)} exact bytes at 0x{address:X}', 'source': s['source']})
    from .edc15 import identity
    return found + identity(data)


def scan_axes(data, start=0, end=None, minimum=8, maximum=32, limit=200):
    """Experimental aligned monotonic u16 LE curves; no ECU or map semantics."""
    end = len(data) if end is None else end
    if start < 0 or end > len(data) or start >= end:
        raise ValueError('Invalid scan range.')
    candidates = []
    pos = start + start % 2
    while pos + minimum * 2 <= end and len(candidates) < limit:
        vals = []
        for off in range(pos, min(end - 1, pos + maximum * 2), 2):
            v = int.from_bytes(data[off:off + 2], 'little')
            if vals and (v <= vals[-1] or v - vals[-1] > 10000):
                break
            vals.append(v)
        if len(vals) >= minimum:
            candidates.append({'address': pos, 'length': len(vals), 'status': 'candidate',
                               'reason': 'Strictly rising aligned u16 LE sequence; axis-like only, not a confirmed ECU map.'})
            pos += len(vals) * 2
        else:
            pos += 2
    return candidates


class Document:
    def __init__(self, original, source=None):
        if not 0 < len(original) <= MAX_FILE:
            raise ValueError('Invalid binary size.')
        self.original = bytes(original)
        self.data = bytearray(original)
        self.source = str(Path(source).resolve()) if source else None
        self.protected_paths = {self.source} if self.source else set()
        self.undo_stack = []
        self.redo_stack = []
        self.history = []
        self.definitions = {'schema': 'opencal.definitions', 'version': 1, 'maps': [], 'signatures': []}
        self.profiles = {}

    def edit(self, address, new, label='Hex edit'):
        new = bytes(new)
        if address < 0 or not new or address + len(new) > len(self.data):
            raise ValueError('Edit is outside the binary or empty.')
        before = bytes(self.data[address:address + len(new)])
        if before == new:
            return
        action = (address, before, new, str(label))
        self.data[address:address + len(new)] = new
        self.undo_stack.append(action); self.redo_stack.clear()
        self.history.append({'action': 'edit', 'address': address, 'before': before.hex(), 'after': new.hex(), 'label': str(label)})

    def undo(self):
        if self.undo_stack:
            a, before, after, label = self.undo_stack.pop()
            self.data[a:a + len(before)] = before
            self.redo_stack.append((a, before, after, label))
            self.history.append({'action': 'undo', 'label': label})

    def redo(self):
        if self.redo_stack:
            a, before, after, label = self.redo_stack.pop()
            self.data[a:a + len(after)] = after
            self.undo_stack.append((a, before, after, label))
            self.history.append({'action': 'redo', 'label': label})

    def find(self, pattern, start=0):
        if not pattern:
            raise ValueError('Empty search pattern.')
        return self.data.find(pattern, start)

    def set_map_cell(self, m, index, physical):
        if type(index) is not int or not 0 <= index < m['rows'] * m['columns']:
            raise ValueError('Invalid cell or value.')
        encoded=encode_map_value(m,physical)
        self.edit(number(m['address']) + index * len(encoded), encoded, m['name'])

    def report(self):
        from .checksums import inspect
        return {'schema': 'opencal.audit', 'version': 1, 'original_sha256': digest(self.original),
                'modified_sha256': digest(self.data), 'size': len(self.data),
                'changed_ranges': list(differences(self.original, self.data)),
                'identification': identify(self.original, self.definitions),
                'checksum': inspect(self.data),
                'history': self.history}

    def protect(self, path):
        p = Path(path).resolve()
        for old in self.protected_paths:
            q = Path(old)
            if p == q or (p.exists() and q.exists() and p.samefile(q)):
                raise ValueError('This path is an original input and cannot be overwritten.')
        return p

    def save_project(self, path):
        p = self.protect(path)
        if p.suffix.lower()!='.ocproj':
            raise ValueError('Projects must use .ocproj; a BIN or other input cannot be replaced by a project.')
        payload = {'schema': 'opencal.project', 'version': 1, 'source': self.source,
                   'original': base64.b64encode(self.original).decode(), 'modified': base64.b64encode(self.data).decode(),
                   'original_sha256': digest(self.original), 'modified_sha256': digest(self.data),
                   'definitions': self.definitions, 'history': self.history,
                   'undo': [[a, b.hex(), c.hex(), d] for a, b, c, d in self.undo_stack],
                   'redo': [[a, b.hex(), c.hex(), d] for a, b, c, d in self.redo_stack],
                   'profiles': {k: base64.b64encode(v).decode() for k, v in self.profiles.items()}}
        atomic_json(p, payload)

    @classmethod
    def load_project(cls, path):
        p = Path(path)
        if p.stat().st_size > MAX_FILE * 6:
            raise ValueError('Project exceeds size limit.')
        obj = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(obj,dict) or obj.get('schema') != 'opencal.project' or obj.get('version') != 1:
            raise ValueError('Unsupported project schema/version.')
        original = base64.b64decode(obj['original'], validate=True)
        modified = base64.b64decode(obj['modified'], validate=True)
        if digest(original) != obj['original_sha256'] or digest(modified) != obj['modified_sha256'] or len(original) != len(modified):
            raise ValueError('Project binary integrity check failed.')
        doc = cls(original, obj.get('source'))
        doc.data[:] = modified
        doc.definitions = validate_definitions(obj['definitions'], len(original))
        from .mappack import upgrade_legacy_axes
        upgrade_legacy_axes(doc.definitions,doc.data)
        validate_definitions(doc.definitions,len(original))
        doc.history = obj['history']
        if not isinstance(doc.history,list) or any(not isinstance(e,dict) for e in doc.history):
            raise ValueError('Invalid project history.')
        for key in ('undo', 'redo'):
            stack = []
            for a, b, c, d in obj.get(key, []):
                b, c = bytes.fromhex(b), bytes.fromhex(c)
                if type(a) is not int or a < 0 or not b or len(b) != len(c) or a + len(b) > len(original):
                    raise ValueError('Invalid project edit history.')
                stack.append((a, b, c, d))
            setattr(doc, key + '_stack', stack)
        # Hashes cover payloads, but an independently damaged undo record must
        # not be allowed to introduce unrelated bytes on the next Undo/Redo.
        replay=bytearray(original)
        for a,before,after,label in doc.undo_stack:
            if bytes(replay[a:a+len(before)])!=before:
                raise ValueError('Project undo history is inconsistent with original bytes.')
            replay[a:a+len(after)]=after
        if replay!=modified: raise ValueError('Project edit history does not reproduce the modified BIN.')
        for a,before,after,label in reversed(doc.redo_stack):
            if bytes(replay[a:a+len(before)])!=before:
                raise ValueError('Project redo history is inconsistent with current bytes.')
            replay[a:a+len(after)]=after
        if not isinstance(obj.get('profiles',{}),dict):raise ValueError('Invalid project snapshots.')
        for k, v in obj.get('profiles', {}).items():
            data = base64.b64decode(v, validate=True)
            if len(data) != len(original):
                raise ValueError('Profile has wrong binary size.')
            doc.profiles[k] = data
        doc.protected_paths.add(str(p.resolve()))
        refresh_axes(doc.data,doc.definitions)
        return doc

    def export(self, path):
        p = self.protect(path)
        # Exclusive creation prevents overwriting any file, symlink or original.
        report = self.report()
        sidecar = Path(str(p) + '.audit.json')
        with sidecar.open('x', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        created = False
        try:
            with p.open('xb') as f:
                created = True
                f.write(self.data); f.flush(); os.fsync(f.fileno())
        except Exception:
            if created:
                p.unlink(missing_ok=True)
            sidecar.unlink()
            raise
        return report


def atomic_json(path, payload):
    import tempfile
    p = Path(path)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=p.parent, delete=False) as f:
            temp = Path(f.name)
            json.dump(payload, f, indent=2, allow_nan=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(temp, p)
    finally:
        if temp and temp.exists():
            temp.unlink()
