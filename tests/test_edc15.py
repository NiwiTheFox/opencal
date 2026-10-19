import json
import struct
import unittest
from pathlib import Path
from opencal.checksums import SIGNATURE, inspect, correct
from opencal.core import digest,differences,Document,validate_definitions
from opencal.edc15 import discover,dtc_records,disable_dtc,restore_dtc,identity
from opencal.multimap import inspect_multimap


def golden_binary():
    vector=json.loads((Path(__file__).parent/'checksum_vectors.json').read_text())
    data=bytearray((i*17+3)&255 for i in range(0x80000))
    data[0x70001:0x7000c]=SIGNATURE
    assert digest(data)==vector['original_sha256']
    for store,value in vector['stores']: struct.pack_into('<I',data,store,value)
    assert digest(data)==vector['corrected_sha256']
    return data


def dtc_fixture():
    data=bytearray(0x80000); data[0x70001:0x7000c]=SIGNATURE
    from opencal.edc15 import DTC_DATABASE
    codes=[int(c) for c in DTC_DATABASE if 16471<=int(c)<=20000][:25]
    for i,code in enumerate(codes):
        a=0x6e800+i*10
        struct.pack_into('<HHBBH',data,a,0x30,0x30,0x11,0x23,code)
    return data,codes


class ChecksumTests(unittest.TestCase):
    def test_golden_independent_typescript_vector(self):
        data=golden_binary(); before=bytes(data); r=inspect(data)
        self.assertEqual(r['status'],'matched'); self.assertEqual(r['matched'],5)
        self.assertEqual(data,before)

    def test_correction_and_unrelated_bytes(self):
        original=golden_binary(); data=bytearray(original); data[0x6c900]^=1
        self.assertEqual(inspect(data)['status'],'mismatch')
        fixed=correct(data,original); self.assertEqual(inspect(fixed)['status'],'matched')
        checksum_bytes={a for r in inspect(data)['regions'] for a in range(r['store'],r['store']+4)}
        changed={a for start,end in differences(data,fixed) for a in range(start,end)}
        self.assertTrue(changed); self.assertTrue(changed<=checksum_bytes)
        self.assertEqual(fixed[0x6c900],data[0x6c900])
        self.assertEqual(correct(fixed,original),fixed)

    def test_unknown_is_never_success(self):
        for data in [bytes(8),bytes(0x80000),bytes(0x100000)]:
            self.assertEqual(inspect(data)['status'],'unverified')
            with self.assertRaises(ValueError): correct(data,data)

    def test_bad_baseline_and_changed_layout(self):
        orig=golden_binary(); bad=bytearray(orig); bad[0x8001]^=1
        with self.assertRaises(ValueError): correct(bad,bad)
        bad=bytearray(orig); bad[0x70001]=0
        with self.assertRaises(ValueError): correct(bad,orig)


class DetectionTests(unittest.TestCase):
    def test_structure_signed_driver_and_cell_preservation(self):
        data=bytearray(0x80000); data[0x70001:0x7000c]=SIGNATURE
        pos=0x6c200
        first=struct.pack('<HH12H',0xec2c,12,*range(0,6000,500))
        second=struct.pack('<HH8H',0xc0b4,8,*range(0,10001,1428))
        data[pos:pos+len(first)+len(second)]=first+second
        address=pos+len(first)+len(second)
        struct.pack_into('<96h',data,address,*([1000]*95+[-90]))
        defs=validate_definitions(discover(data),len(data))
        m=next(m for m in defs['maps'] if m['address']==address)
        self.assertIn('Driver wish',m['name']); self.assertEqual(m['type'],'i16')
        self.assertEqual((m['rows'],m['columns']),(12,8)); self.assertEqual(m['verification'],'candidate')
        doc=Document(data); doc.set_map_cell(m,95,-1.2)
        self.assertEqual(struct.unpack_from('<h',doc.data,address+190)[0],-120)
        self.assertEqual(doc.data[:address+190],data[:address+190]); self.assertEqual(doc.data[address+192:],data[address+192:])

    def test_unsupported_and_truncated_structures(self):
        with self.assertRaises(ValueError): discover(bytes(256))
        data=bytearray(0x80000); data[0x70001:0x7000c]=SIGNATURE
        struct.pack_into('<HH',data,0x7bff8,0xec2c,32)
        self.assertEqual(discover(data)['maps'],[])
        self.assertEqual(identity(bytes(0x80000)),[])

    def test_dtc_disable_restore_and_undo(self):
        original,codes=dtc_fixture(); records=dtc_records(original)
        self.assertEqual(len(records),25)
        result,selected=disable_dtc(original,codes[0])
        a=selected[0]['address']
        self.assertEqual(result[a:a+5],bytes.fromhex('ff ff 00 00 00'))
        self.assertEqual(result[a+5:],original[a+5:]); self.assertEqual(result[:a],original[:a])
        self.assertFalse(next(r for r in dtc_records(result) if r['vag_code']==codes[0])['enabled'])
        self.assertEqual(restore_dtc(result,original,codes[0]),original)
        doc=Document(original); doc.edit(0,result,'DTC'); doc.undo(); self.assertEqual(doc.data,original)
        with self.assertRaises(ValueError): dtc_records(bytes(0x80000))

    def test_multimap_evidence_and_false_claim_prevention(self):
        data=bytearray(0x80000)
        self.assertEqual(inspect_multimap(data)['groups'],[])
        for i,page in enumerate((0x34,0x38,0x3c)):
            data[0x1a000+i*16:0x1a00c+i*16]=b''.join(bytes((0xe6,r,page+r,0)) for r in range(3))
        data[0x14784:0x14788]=bytes.fromhex('da 09 00 a0')
        result=inspect_multimap(data)
        self.assertEqual(result['status'],'candidate evidence only')
        self.assertTrue(result['groups'][0]['multiple_page_sets'])
        self.assertEqual(result['groups'][0]['far_call_candidates'][0]['call_offset'],0x14784)


if __name__=='__main__': unittest.main()
