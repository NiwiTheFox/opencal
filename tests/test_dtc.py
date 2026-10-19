import json,struct,tempfile,unittest
from pathlib import Path
from opencal.core import Document,differences
from opencal.edc15 import DTC_DATABASE,dtc_records
from opencal.dtc import grouped,preview,apply,reference_records,DISABLED
from tests.test_edc15 import dtc_fixture


def identified_fixture():
    data,codes=dtc_fixture()
    data[0x7b100:0x7b100+len(b'038906019FJ 0281010789 SG 1376')]=b'038906019FJ 0281010789 SG 1376'
    return data,codes


class DTCTests(unittest.TestCase):
    def test_english_and_categories(self):
        self.assertEqual(len(DTC_DATABASE),1776)
        self.assertEqual(next(v for v in DTC_DATABASE.values() if v['code']=='P0605')['description'],'Engine control unit - ROM error')
        for entry in DTC_DATABASE.values():
            self.assertTrue(entry['description']);self.assertTrue(entry['system_key'])
            self.assertNotIn('Calculateur',entry['description']);self.assertNotIn('Echappement',entry['system'])

    def test_group_and_individual_exact_edits(self):
        original,codes=dtc_fixture();code=codes[0]
        original[0x6f100:0x6f108]=original[0x6e800:0x6e808]
        document=Document(original);records=[r for r in dtc_records(original) if r['vag_code']==code]
        operation=apply(document,code,False,[records[0]['address']])
        self.assertEqual(len(operation['edits']),1)
        group=next(g for g in grouped(dtc_records(document.data)) if g['vag_code']==code)
        self.assertEqual(group['state'],'Mixed');self.assertEqual(group['enabled'],1)
        apply(document,code,True);self.assertEqual(document.data,original)
        apply(document,code,False);self.assertEqual(len(document.undo_stack),3)
        changes={a for start,end in differences(original,document.data) for a in range(start,end)}
        allowed={a for r in records for a in range(r['address'],r['address']+5)}
        self.assertLessEqual(changes,allowed)
        document.undo();self.assertEqual(document.data,original)
        document.redo();self.assertEqual(next(g for g in grouped(dtc_records(document.data)) if g['vag_code']==code)['state'],'Disabled')

    def test_no_invented_enable_bytes_and_atomic_failure(self):
        original,codes=dtc_fixture();original[0x6e800:0x6e805]=DISABLED
        doc=Document(original)
        with self.assertRaisesRegex(ValueError,'already disabled'):apply(doc,codes[0],True)
        self.assertEqual(doc.data,original);self.assertEqual(doc.undo_stack,[])
        with self.assertRaises(ValueError):preview(doc,codes[1],False,[0x6e800])

    def test_reference_and_multibank_relocation(self):
        stock,codes=identified_fixture();tuned=bytearray(stock)
        tuned[0x4c000:0x5c000]=stock[0x6c000:0x7c000]
        tuned[0x5c000:0x6c000]=stock[0x6c000:0x7c000]
        target=Document(tuned)
        for r in dtc_records(tuned):
            if r['vag_code']==codes[0]:target.data[r['address']:r['address']+5]=DISABLED
        # Already disabled input is deliberately the project's immutable baseline.
        target=Document(target.data);target.dtc_reference=bytes(stock)
        operation=apply(target,codes[0],True)
        self.assertEqual(len(operation['edits']),3)
        self.assertEqual(target.data,tuned)
        target.undo();self.assertEqual(target.data,target.original)
        bad=bytearray(stock);bad[0x7b100]^=1
        with self.assertRaises(ValueError):reference_records(tuned,bad)
        bad=bytearray(stock);bad[0x6e806:0x6e808]=struct.pack('<H',codes[1])
        with self.assertRaises(ValueError):reference_records(tuned,bad)

    def test_project_reference_persistence_integrity_and_dirty_state(self):
        stock,codes=identified_fixture();doc=Document(stock);doc.dtc_reference=bytes(stock)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'codex test.ocproj';doc.save_project(path)
            restored=Document.load_project(path);self.assertEqual(restored.dtc_reference,stock)
            obj=json.loads(path.read_text());obj['dtc_reference']['sha256']='0'*64;path.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError,'reference integrity'):Document.load_project(path)

    def test_real_copied_stock_v9_reference(self):
        from tests.private_fixtures import STOCK,V9
        if not STOCK.exists() or not V9.exists():self.skipTest('Private copied fixtures unavailable')
        stock=STOCK.read_bytes();v9=V9.read_bytes();doc=Document(v9)
        mapping=reference_records(v9,stock);self.assertEqual(len(mapping),504)
        doc.dtc_reference=stock
        disabled=[r for r in dtc_records(v9) if not r['enabled'] and mapping[r['address']]!=DISABLED]
        self.assertTrue(disabled)
        code=disabled[0]['vag_code'];before=bytes(doc.data);apply(doc,code,True)
        for r in dtc_records(doc.data):
            if r['vag_code']==code:self.assertTrue(r['enabled'])
        doc.undo();self.assertEqual(doc.data,before)
        self.assertEqual(STOCK.read_bytes(),stock);self.assertEqual(V9.read_bytes(),v9)


class DTCWidgetTests(unittest.TestCase):
    def test_buttons_colours_persistence_and_close(self):
        import tkinter as tk
        from opencal.workbench import App
        from unittest.mock import patch
        root=tk.Tk();root.withdraw()
        try:
            app=App(root);original,codes=dtc_fixture();app.doc=Document(original);app.refresh();app.read_dtcs();root.update()
            panel=app.dtc_panel;key=(codes[0],None);label=panel.row_labels[key]
            self.assertEqual(label.cget('fg'),'#63dba0');self.assertEqual(panel.buttons[key].cget('fg'),'white')
            panel.buttons[key].invoke();root.update()
            self.assertEqual(panel.row_labels[key].cget('fg'),'#ff777e');self.assertEqual(panel.buttons[key].cget('fg'),'white')
            app.undo();root.update();self.assertEqual(panel.row_labels[key].cget('fg'),'#63dba0')
            panel.expand(codes[0]);self.assertIn((codes[0],0x6e800),panel.buttons)
            app.doc.edit(2,b'X');app.refresh();root.update();self.assertEqual(len(panel.records),25)
            panel.query.set('does not exist');self.assertEqual(panel.buttons,{})
            panel.query.set('');self.assertIn(key,panel.buttons)
            with patch.object(app,'can_leave',return_value=True):app.close_project()
            self.assertFalse(panel.loaded);self.assertEqual(panel.records,[])
        finally:root.destroy()
