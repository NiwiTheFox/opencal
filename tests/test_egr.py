import struct,unittest
from unittest.mock import patch
from opencal.core import Document,differences,digest
from opencal.edc15 import DTC_DATABASE,dtc_records
from opencal.egr import inspect,preview,TARGET,CODES,MAP_OFFSET
from opencal.solutions import apply_preview
from opencal.dtc import DISABLED
from tests.test_dtc import identified_fixture


def fixture():
    data,_=identified_fixture();base=0x70000;address=base+MAP_OFFSET;header=address-66
    struct.pack_into('<HH16H',data,header,0xec1a,16,*range(0,6001,400))
    struct.pack_into('<HH13H',data,header+36,0xc0b4,13,*range(0,6001,500))
    struct.pack_into('<208H',data,address,*[3500+i*7 for i in range(208)])
    for i,code in enumerate(sorted(CODES)):
        vag=next(int(key) for key,value in DTC_DATABASE.items() if value['code']==code)
        struct.pack_into('<HHBBH',data,0x6ea00+i*10,0x30,0x30,0x11,0x23,vag)
    return data


class EGRTests(unittest.TestCase):
    def test_only_named_maps_and_egr_records_change_one_undo(self):
        original=fixture();document=Document(original);state=inspect(original)
        self.assertEqual(state['status'],'supported');self.assertEqual(len(state['records']),4)
        operation=preview(document);self.assertEqual(operation['map_cells_changed'],208)
        self.assertEqual(sum(e['kind']=='dtc' for e in operation['edits']),4)
        apply_preview(document,operation)
        address=0x70000+MAP_OFFSET;self.assertEqual(document.data[address:address+416],TARGET)
        allowed=set(range(address,address+416))|{a for r in state['records'] for a in range(r['address'],r['address']+5)}
        changed={a for start,end in differences(original,document.data) for a in range(start,end)}
        self.assertTrue(changed);self.assertLessEqual(changed,allowed)
        self.assertEqual(inspect(document.data)['status'],'target present');self.assertEqual(len(document.undo_stack),1)
        self.assertEqual(preview(document)['edits'],[])
        before=len(document.undo_stack);apply_preview(document,preview(document));self.assertEqual(len(document.undo_stack),before)
        document.undo();self.assertEqual(document.data,original)
        document.redo();apply_preview(document,preview(document,restore=True));self.assertEqual(document.data,original)

    def test_all_banks_and_complete_failure_on_one_bad_bank(self):
        original=fixture()
        original[0x4c000:0x5c000]=original[0x6c000:0x7c000]
        original[0x5c000:0x6c000]=original[0x6c000:0x7c000]
        document=Document(original);operation=preview(document)
        self.assertEqual(operation['map_cells_changed'],624);self.assertEqual(len(operation['records']),12)
        apply_preview(document,operation);self.assertEqual(inspect(document.data)['maps_at_target'],3)
        document.undo();self.assertEqual(document.data,original)
        bad=bytearray(original);bad[0x50000+MAP_OFFSET-65]=0
        self.assertEqual(inspect(bad)['status'],'unsupported')
        with self.assertRaises(ValueError):preview(Document(bad))
        bad=bytearray(original);bad[0x5b100]=ord('X')
        self.assertEqual(inspect(bad)['status'],'unsupported')
        with self.assertRaises(ValueError):preview(Document(bad))

    def test_identity_axis_values_and_diagnostic_layout_guards(self):
        original=fixture()
        for address,value in [(0x7b100,b'X'),(0x70000+MAP_OFFSET-66,b'\0\0'),(0x70000+MAP_OFFSET,b'\xff\xff'),(0x6ea05,b'\0')]:
            bad=bytearray(original);bad[address:address+len(value)]=value
            self.assertEqual(inspect(bad)['status'],'unsupported')
            document=Document(bad)
            with self.assertRaises(ValueError):preview(document)
            self.assertEqual(document.data,bad);self.assertFalse(document.undo_stack)

    def test_stale_preview_and_original_disabled_restore(self):
        document=Document(fixture());operation=preview(document);document.edit(12,b'\x01')
        before=bytes(document.data)
        with self.assertRaises(ValueError):apply_preview(document,operation)
        self.assertEqual(document.data,before)
        disabled=bytearray(fixture());address=0x70000+MAP_OFFSET;disabled[address:address+416]=TARGET
        for record in inspect(disabled)['records']:disabled[record['address']:record['address']+5]=DISABLED
        document=Document(disabled);document.edit(address,b'\0\0');apply_preview(document,preview(document,restore=True))
        self.assertEqual(document.data,disabled);self.assertFalse(inspect(document.data)['enabled_records'])

    def test_private_copies_checksum_undo_and_existing_v9_target(self):
        from tests.private_fixtures import STOCK,V9
        if not STOCK.exists() or not V9.exists():self.skipTest('Private copied firmware unavailable')
        stock=STOCK.read_bytes();v9=V9.read_bytes();document=Document(stock)
        self.assertEqual(inspect(stock)['maps_at_target'],1)
        operation=preview(document);self.assertEqual(operation['map_cells_changed'],0);self.assertEqual(len(operation['edits']),4)
        apply_preview(document,operation)
        from opencal.checksums import correct,inspect as sums
        corrected=correct(document.data,document.original);self.assertEqual(sums(corrected)['status'],'matched')
        document.undo();self.assertEqual(document.data,stock)
        self.assertEqual(inspect(v9)['status'],'target present');self.assertEqual(preview(Document(v9))['edits'],[])
        self.assertEqual(STOCK.read_bytes(),stock);self.assertEqual(V9.read_bytes(),v9)


class EGRWidgetTests(unittest.TestCase):
    def test_preview_apply_undo_refresh_and_stale_project_guard(self):
        import tkinter as tk
        from opencal.workbench import App
        from opencal.egr_ui import show_preview
        root=tk.Tk();root.withdraw();errors=[];root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        try:
            app=App(root);app.doc=Document(fixture());app.refresh();before=bytes(app.doc.data)
            root.deiconify();root.geometry('1080x700+80+60');root.update()
            show_preview(app);root.update()
            self.assertGreaterEqual(app.egr_preview_window.winfo_rootx(),root.winfo_rootx())
            self.assertGreaterEqual(app.egr_preview_window.winfo_rooty(),root.winfo_rooty())
            app.egr_apply_button.invoke();root.update()
            self.assertEqual(inspect(app.doc.data)['status'],'target present');self.assertIn('0/4',app.egr_status.get())
            app.undo();self.assertEqual(app.doc.data,before)
            show_preview(app);old=app.doc;app.doc=Document(fixture())
            with patch('opencal.gui.mb.showerror') as error:app.egr_apply_button.invoke();error.assert_called_once()
            self.assertEqual(old.data,before);self.assertEqual(app.doc.data,before)
            app.egr_preview_window.destroy();self.assertEqual(errors,[])
        finally:root.destroy()
