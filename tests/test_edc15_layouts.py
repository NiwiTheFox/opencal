import struct,unittest
from opencal.checksums import SIGNATURE,inspect as sums,correct,calculate_tdi41
from opencal.layouts import detect
from opencal.edc15 import discover_heuristic,dtc_records,DTC_DATABASE
from opencal.core import Document,validate_definitions
from opencal.dtc import apply,DISABLED
from opencal.codeblocks import codeblock


def compact_fixture():
    data=bytearray(b'\xc3'*0x80000)
    for base in (0x58000,0x70000):
        data[base+1:base+12]=SIGNATURE
        p=base+0x200
        axes=struct.pack('<HH16H',0xec00,16,*range(0,6400,400))+struct.pack('<HH13H',0xc000,13,*range(0,6500,500))
        data[p:p+len(axes)+416]=axes+struct.pack('<208H',*([3500]*208))
        codes=[int(c) for c in DTC_DATABASE if 16471<=int(c)<=20000][:25]
        for i,c in enumerate(codes):
            a=base+0x2000+i*42
            raw=b'\xc3'+struct.pack('<8H',c,*([0]*7))+struct.pack('<5H',*([0xf000]*5))+bytes.fromhex('300030001100ffff00000000')+b'\x00'*3
            data[a:a+42]=raw
    return data,codes


class LayoutTests(unittest.TestCase):
    def test_compact_map_bounds_and_codeblock_grouping(self):
        data,_=compact_fixture();self.assertEqual(detect(data)['generation'],'compact')
        defs=validate_definitions(discover_heuristic(data),len(data));self.assertTrue(defs['maps'])
        for m in defs['maps']:
            b=codeblock(data,m);self.assertIsNotNone(b);self.assertGreaterEqual(m['address'],b['start']);self.assertLessEqual(m['address']+2*m['rows']*m['columns'],b['end'])
    def test_compact_checksum_correction_is_bounded_and_idempotent(self):
        original,_=compact_fixture()
        # Seed synthetic stored sums, then make this the valid original.
        for r in sums(original)['regions']:struct.pack_into('<I',original,r['store'],r['computed'])
        self.assertEqual(sums(original)['status'],'matched')
        modified=bytearray(original);modified[0x58300]^=1
        fixed=correct(modified,original);self.assertEqual(sums(fixed)['status'],'matched')
        allowed={a for r in sums(original)['regions'] for a in range(r['store'],r['store']+4)}
        self.assertLessEqual({i for i,(a,b) in enumerate(zip(modified,fixed)) if a!=b},allowed)
        self.assertEqual(correct(fixed,original),fixed)
    def test_fault_path_disable_shared_bytes_and_exact_enable(self):
        data,codes=compact_fixture();records=dtc_records(data);self.assertEqual(len(records),50)
        doc=Document(data);op=apply(doc,codes[0],False);self.assertEqual(len(op['edits']),2)
        for r in dtc_records(doc.data):
            if r['vag_code']==codes[0]:self.assertFalse(r['enabled'])
        apply(doc,codes[0],True);self.assertEqual(doc.data,data)
        doc.undo();doc.undo();self.assertEqual(doc.data,data)
    def test_early_layout_does_not_invent_checksum_or_dtcs(self):
        data=bytearray(0x80000)
        for end in (0x8000,0x10000):data[end-8:end-4]=bytes.fromhex('3c3c41e4')
        self.assertEqual(detect(data)['generation'],'early');self.assertEqual(sums(data)['status'],'unverified')
        with self.assertRaises(ValueError):dtc_records(data)
    def test_tdi41_bounds(self):
        for start,end in ((0,0),(1,8),(0,6),(0,12)):
            with self.assertRaises(ValueError):calculate_tdi41(bytes(8),start,end)

    def test_shared_fault_path_affects_all_its_codes_and_restores_exactly(self):
        data,codes=compact_fixture()
        for base in (0x58000,0x70000):struct.pack_into('<H',data,base+0x2000+3,codes[1])
        doc=Document(data);operation=apply(doc,codes[0],False)
        self.assertIn(codes[1],operation['shared_path_codes'])
        for r in dtc_records(doc.data):
            if r.get('path_address') in (0x5a000,0x72000):self.assertFalse(r['enabled'])
        apply(doc,codes[0],True);self.assertEqual(doc.data,data)

    def test_fault_path_padding_and_single_code_candidate_cannot_enable_support(self):
        data,codes=compact_fixture()
        # Corrupt the pad of every triplet. Markers alone cannot establish a table.
        for base in (0x58000,0x70000):
            for i in range(25):data[base+0x2000+i*42+32]=1
        with self.assertRaises(ValueError):dtc_records(data)

    def test_early_axis_identity_classifies_driver_and_boost_candidates(self):
        data=bytearray(0x80000)
        for end in (0x8000,0x80000):data[end-8:end-4]=bytes.fromhex('3c3c41e4')
        for i in range(3):
            pos=0x78100+i*600
            first=struct.pack('<HH16H',0xe082,16,*range(0,6400,400))
            second=struct.pack('<HH8H',0xe800,8,*range(0,10001,1428))
            data[pos:pos+len(first)+len(second)+256]=first+second+struct.pack('<128H',*([3000]*128))
        maps=discover_heuristic(data)['maps']
        self.assertEqual(sum('Driver wish' in m['name'] for m in maps),3)
        for m in maps:self.assertEqual(m['x_axis']['factor'],.01)
