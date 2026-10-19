import copy,tkinter as tk,unittest,struct
from opencal.checksums import SIGNATURE
from opencal.codeblocks import codeblock,map_name,metadata_id
from opencal.core import Document
from opencal.workbench import App
from tests.test_core import definitions


class CodeblockTests(unittest.TestCase):
    def test_sparse_and_multiple_blocks_keep_ecu_numbering(self):
        data=bytearray(0x80000);data[0x70001:0x7000c]=SIGNATURE
        struct.pack_into('<HH',data,0x71000,0x1b2e,0x1b62);struct.pack_into('<H',data,0x71b62,3)
        m=definitions()['maps'][0];m.update(address=0x70100,name='Torque limiter [bank 70000]')
        self.assertEqual(codeblock(data,m)['number'],3)
        self.assertEqual(map_name(data,m),'Torque limiter [codeblock 3]')
        self.assertIsNone(codeblock(bytes(0x100000),m))
        struct.pack_into('<H',data,0x71b62,58882);self.assertIsNone(metadata_id(data,0x70000))
        self.assertIn('ID unknown',map_name(data,m))

    def test_tree_groups_tuned_file_and_searches_codeblocks(self):
        data=bytearray(0x80000);maps=[]
        for i,base in enumerate((0x50000,0x60000,0x70000),1):
            data[base+1:base+12]=SIGNATURE
            struct.pack_into('<HH',data,base+0x1000,0x1b2e,0x1b62);struct.pack_into('<H',data,base+0x1b62,i)
            m=copy.deepcopy(definitions()['maps'][0]);m.update(id=str(i),address=base+0x100,name=f'Driver wish [bank {base:05X}]');maps.append(m)
        root=tk.Tk();root.withdraw()
        try:
            app=App(root);app.doc=Document(data);app.doc.definitions={'schema':'opencal.definitions','version':1,'maps':maps};app.refresh()
            self.assertEqual(len(app.maps.get_children()),3);self.assertEqual(len(app.map_leaf_ids()),3)
            for i,item in enumerate(app.map_leaf_ids(),1):self.assertIn(f'[codeblock {i}]',app.maps.item(item)['text'])
            app.search.set('codeblock 2');self.assertEqual(app.map_leaf_ids(),['1'])
            app.search.set('');app.maps.selection_set('2');app.view_map();self.assertEqual(app.active_map,2)
        finally:root.destroy()

    def test_private_stock_and_tuned_metadata_ids(self):
        from tests.private_fixtures import STOCK,V9
        if not STOCK.exists() or not V9.exists():self.skipTest('Private copies unavailable')
        self.assertEqual(metadata_id(STOCK.read_bytes(),0x70000),3)
        self.assertEqual([metadata_id(V9.read_bytes(),base) for base in (0x50000,0x60000,0x70000)],[4,5,3])
