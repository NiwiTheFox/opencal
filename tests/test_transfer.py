import copy,json,struct,unittest
from opencal.transfer import transfer_ori,identifiers
from opencal.catalog import make_profile,match_profile
from opencal.mappack import decode_json,import_mappack
from opencal.edc15 import discover,discover_heuristic
from tests.private_fixtures import STOCK,V9


@unittest.skipUnless(STOCK.exists() and V9.exists(),'Private working copies unavailable')
class TransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ori=STOCK.read_bytes(); cls.tuned=V9.read_bytes()
        cls.pack=decode_json((STOCK.parent/'codex stock ZedSuite mappack.json').read_bytes())

    def test_all_ori_definitions_retained_in_three_banks(self):
        pack=transfer_ori(self.ori,self.tuned,self.pack)
        self.assertEqual(len(pack['maps']),213)
        defs,skipped=import_mappack(pack,self.tuned)
        self.assertFalse(skipped)
        selectors=[m for m in defs['maps'] if 'Selector for injector duration' in m['name']]
        self.assertEqual(len(selectors),3)
        for m in defs['maps']: self.assertTrue(0x4c000<=m['address']<0x7c000)
        self.assertEqual(V9.read_bytes(),self.tuned)

    def test_mismatched_software_or_axis_header_refused(self):
        changed=bytearray(self.tuned)
        a=changed.find(b'SG  1376'); self.assertGreater(a,0); changed[a+4:a+8]=b'9999'
        with self.assertRaises(ValueError): transfer_ori(self.ori,changed,self.pack)
        changed=bytearray(self.tuned)
        defs,_=import_mappack(self.pack,self.ori)
        a=next(m['x_axis']['address'] for m in defs['maps'] if 'x_axis' in m)-0x20000-4
        changed[a]^=1
        with self.assertRaises(ValueError): transfer_ori(self.ori,changed,self.pack)

    def test_malformed_pack_refused(self):
        pack=copy.deepcopy(self.pack); pack['maps'][0]['Fieldvalues.StartAddr.Cpu']='$100'
        with self.assertRaises(ValueError): transfer_ori(self.ori,self.tuned,pack)

    def test_profile_matches_calibration_edit_but_refuses_code_edit(self):
        profile=make_profile(self.ori,self.pack,'test','test source')
        defs,_=import_mappack(self.pack,self.ori)
        changed=bytearray(self.ori); changed[defs['maps'][0]['address']]^=1
        self.assertIsNotNone(match_profile(changed,[profile]))
        changed[0x100]^=1
        self.assertIsNone(match_profile(changed,[profile]))

    def test_auto_detect_uses_correct_reference(self):
        self.assertEqual(len(discover(self.ori)['maps']),71)
        self.assertEqual(len(discover(self.tuned)['maps']),213)

    def test_source_port_matches_fresh_stock_export_without_profile(self):
        expected,_=import_mappack(self.pack,self.ori)
        actual=discover_heuristic(self.ori)['maps']
        oracle={m['address']:m for m in expected['maps']}
        self.assertEqual({m['address'] for m in actual},set(oracle))
        for m in actual:
            reference=oracle[m['address']]
            self.assertEqual(m['type'],reference['type'],m['name'])
            self.assertEqual(m['endian'],reference['endian'])
            self.assertEqual(m['rows']*m['columns'],reference['rows']*reference['columns'])
            self.assertAlmostEqual(m['factor'],reference['factor'],delta=.00000051)
            self.assertAlmostEqual(m['offset'],reference['offset'],delta=.00000051)
            if min(m['rows'],m['columns'])>1:
                self.assertEqual((m['rows'],m['columns']),(reference['rows'],reference['columns']))


class SourcePassTests(unittest.TestCase):
    def test_project_save_cannot_replace_an_unloaded_bin(self):
        import tempfile
        from pathlib import Path
        from opencal.core import Document
        with tempfile.TemporaryDirectory() as temp:
            binary=Path(temp)/'codex original.bin'; binary.write_bytes(b'untouched input')
            with self.assertRaises(ValueError): Document(b'other input').save_project(binary)
            self.assertEqual(binary.read_bytes(),b'untouched input')

    def test_second_software_matches_fresh_reference_export(self):
        from pathlib import Path
        folder=STOCK.parent.parent/'byznis-038906019LA-SG-5405-157a8c7a'
        export=folder/'codex LA ZedSuite mappack.json'
        if not export.exists(): self.skipTest('Private second-software oracle unavailable')
        data=(folder/'codex 038906019LA-SG  5405.Bin').read_bytes()
        expected,skipped=import_mappack(decode_json(export.read_bytes()),data)
        self.assertFalse(skipped)
        self.assertEqual(len(expected['maps']),142)
        actual=discover_heuristic(data)['maps']
        self.assertEqual({m['address'] for m in actual},{m['address'] for m in expected['maps']})

    def test_n75_curve_does_not_consume_a_two_axis_table_header(self):
        from opencal.checksums import SIGNATURE
        from opencal.source_sequences import source_maps
        data=bytearray(0x80000); data[0x70001:0x7000c]=SIGNATURE
        p=0x6c200
        struct.pack_into('<HH16H',data,p,0xec00,16,*range(0,4000,250))
        a=p+36
        struct.pack_into('<HH8H',data,a,0xc000,8,*range(0,8000,1000))
        self.assertNotIn(a,source_maps(data,[0x70000]))
        data[a:a+32]=struct.pack('<16H',*([8000]*16))
        self.assertIn('Boost actuator upper limit',source_maps(data,[0x70000])[a]['name'])

    def test_selector_allows_nonmonotonic_axis_and_rejects_missing_pattern(self):
        from opencal.checksums import SIGNATURE
        data=bytearray(0x80000); data[0x70001:0x7000c]=SIGNATURE
        a=0x7545c
        struct.pack_into('<HH6H6H',data,a-16,0xec00,6,2688,2901,3754,3328,4000,4500,0,256,512,768,1024,1280)
        maps=discover_heuristic(data)['maps']
        selector=next(m for m in maps if m['address']==a)
        self.assertIn('Selector for injector duration',selector['name'])
        data[a+2]=17
        self.assertFalse(any('Selector for injector duration' in m['name'] for m in discover_heuristic(data)['maps']))

    def test_edc16_size_is_not_accepted_as_edc15(self):
        with self.assertRaises(ValueError): discover_heuristic(bytes(0x100000))
