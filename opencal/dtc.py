"""Grouped DTC editing with exact restoration and checked stock references.

Original OpenCal integration. Record decoding/data are attributed GPL ZedSuite
ports in edc15.py. No universal enabled monitoring bytes are assumed.
"""
from collections import defaultdict
from .core import digest
from .edc15 import dtc_records
from .checksums import standard_bases
from .transfer import identifiers
from .codeblocks import metadata_id

DISABLED=bytes.fromhex('ff ff 00 00 00')


def grouped(records):
    codes={}
    for record in records:
        code=record['vag_code']
        if code not in codes:
            codes[code]={k:record[k] for k in ('vag_code','code','description','system')}
            codes[code]['records']=[]
        codes[code]['records'].append(record)
    for group in codes.values():
        enabled=sum(r['enabled'] for r in group['records'])
        group.update(enabled=enabled,total=len(group['records']),
                     state='Enabled' if enabled==len(group['records']) else 'Disabled' if not enabled else 'Mixed')
    return sorted(codes.values(),key=lambda g:(g['system'],g['code'],g['vag_code']))


def _banks(data,records):
    result=defaultdict(dict)
    for record in records:
        result[record['codeblock_base']][record['address']-record['codeblock_base']]=record
    return result


def reference_records(current,reference):
    """Map stock entries only when IDs and whole per-bank record topology match.

    A single stock bank may match multiple cloned banks. Multiple source banks
    with different monitoring values are ambiguous unless metadata IDs select
    exactly one. A partially similar DTC table is never a restoration source.
    """
    expected=identifiers(current)
    if len(reference)!=len(current) or any(not v for v in expected.values()) or expected!=identifiers(reference):
        raise ValueError('Stock reference must match embedded ECU, hardware and software identifiers and file size.')
    target=_banks(current,dtc_records(current)); source=_banks(reference,dtc_records(reference)); mapping={}
    if set(target)!=set(standard_bases(current)) or set(source)!=set(standard_bases(reference)):
        raise ValueError('A complete supported DTC table is required in every calibration bank.')
    for bank,records in target.items():
        topology={offset:r['vag_code'] for offset,r in records.items()}
        candidates=[]
        for original_bank,original in source.items():
            if topology!={offset:r['vag_code'] for offset,r in original.items()}:continue
            if identifiers(current[bank-0x4000:bank+0xc000])!=identifiers(reference[original_bank-0x4000:original_bank+0xc000]):continue
            candidates.append(original_bank)
        if not candidates:raise ValueError(f'Stock DTC record layout differs from bank 0x{bank:05X}.')
        if len(candidates)>1:
            block=metadata_id(current,bank)
            selected=[b for b in candidates if block is not None and metadata_id(reference,b)==block]
            if len(selected)==1:candidates=selected
        for offset,record in records.items():
            values={bytes.fromhex(source[b][offset]['raw'])[:5] for b in candidates}
            if len(values)!=1:raise ValueError('Stock banks have ambiguous monitoring bytes; use an exact matching stock reference.')
            mapping[record['address']]=next(iter(values))
    return mapping


def enabled_bytes(document,records=None):
    original={r['address']:r for r in dtc_records(document.original)}
    reference=getattr(document,'dtc_reference',None)
    external=reference_records(document.data,reference) if reference is not None else {}
    result={}
    for record in dtc_records(document.data) if records is None else records:
        address=record['address']; old=original.get(address)
        if old and old['vag_code']==record['vag_code'] and old['enabled']:
            result[address]=bytes.fromhex(old['raw'])[:5]
        elif address in external and external[address]!=DISABLED:
            result[address]=external[address]
    return result


def preview(document,code,enable,addresses=None):
    if type(enable) is not bool:raise ValueError('DTC target state must be enabled or disabled.')
    records=[r for r in dtc_records(document.data) if r['vag_code']==code]
    if addresses is not None:
        chosen=set(addresses)
        if not chosen or chosen-{r['address'] for r in records}:raise ValueError('Selected DTC records changed. Read the table again.')
        records=[r for r in records if r['address'] in chosen]
    if not records:raise ValueError('DTC is not present in supported tables.')
    restore=enabled_bytes(document,records) if enable else {}
    edits=[]; result=bytearray(document.data)
    for record in records:
        address=record['address'];before=bytes(result[address:address+5])
        if enable:
            if record['enabled']:continue
            if address not in restore:
                raise ValueError(f'Cannot enable {record["code"]} at 0x{address:06X}: the loaded original was already disabled. Load a matching stock DTC reference with known enabled bytes.')
            after=restore[address]
        else:after=DISABLED
        if before!=after:
            edits.append({'address':address,'before':before.hex(),'after':after.hex(),'bank':record['codeblock_base']})
            result[address:address+5]=after
    return {'schema':'opencal.patch-preview','version':1,'name':f'{"Enable" if enable else "Disable"} {records[0]["code"]} / VAG {code}',
            'input_sha256':digest(document.data),'result_sha256':digest(result),'edits':edits,
            'verification':'Exact supported DTC monitoring records; source file preserved'}


def apply(document,code,enable,addresses=None):
    from .solutions import apply_preview
    operation=preview(document,code,enable,addresses)
    apply_preview(document,operation)
    return operation
