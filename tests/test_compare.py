import copy,struct,unittest
from unittest.mock import patch
from opencal.core import Document,digest
from opencal.compare import changed_maps,reference_map
from tests.test_core import definitions


def fixture():
    document=Document(b'OCAL'+bytes(508));document.definitions=definitions()
    m=document.definitions['maps'][0]
    m['x_axis']={'address':48,'type':'u16','endian':'little','factor':1,'offset':0,'values':[0]*4,'unit':'rpm'}
    m['y_axis']={'address':56,'type':'u16','endian':'little','factor':1,'offset':0,'values':[0]*2,'unit':'mg/st'}
    return document


class CompareTests(unittest.TestCase):
    def test_shared_document_notifications_and_unsubscribe(self):
        doc=Document(b'abc');events=[];unsubscribe=doc.subscribe(lambda:events.append((doc.revision,bytes(doc.data))))
        doc.edit(0,b'Z');doc.undo();doc.redo();doc.edit(0,b'Z')
        self.assertEqual(events,[(1,b'Zbc'),(2,b'abc'),(3,b'Zbc')])
        unsubscribe();doc.undo();self.assertEqual(len(events),3)

    def test_cells_axes_unequal_files_and_wrong_signatures(self):
        doc=fixture();ref=bytes(doc.original);self.assertFalse(changed_maps(doc.data,ref,doc.definitions)['changed'])
        doc.edit(16,b'\x02\0');doc.edit(48,b'\x03\0')
        report=changed_maps(doc.data,ref,doc.definitions);self.assertEqual(len(report['changed']),1)
        self.assertEqual(report['changed'][0]['cells'],[0]);self.assertEqual(report['changed'][0]['axes'],{'x_axis':[0]})
        self.assertEqual(len(changed_maps(doc.data,b'WRNG'+ref[4:],doc.definitions)['unmatched']),1)
        self.assertEqual(len(changed_maps(doc.data,ref[:40],doc.definitions)['unmatched']),1)
        doc.undo();doc.undo();self.assertFalse(changed_maps(doc.data,ref,doc.definitions)['changed'])

    def test_real_stock_and_v9_map_alignment(self):
        from tests.private_fixtures import STOCK,V9
        if not STOCK.exists() or not V9.exists():self.skipTest('Private copies unavailable')
        from opencal.edc15 import discover
        stock=STOCK.read_bytes();v9=V9.read_bytes();defs=discover(v9);before=(digest(stock),digest(v9))
        report=changed_maps(v9,stock,defs)
        self.assertGreater(report['matched'],200);self.assertTrue(report['changed'])
        for item in report['changed']:
            self.assertTrue(0x6c000<=item['reference_map']['address']<0x7c000)
        import re
        bad=bytearray(stock)
        for match in re.finditer(rb'SG\s+1376',bad):bad[match.end()-1]=ord('7')
        self.assertEqual(changed_maps(v9,bad,defs)['matched'],0)
        self.assertEqual(before,(digest(STOCK.read_bytes()),digest(V9.read_bytes())))


class CompareWidgetTests(unittest.TestCase):
    def test_side_by_side_table_headers_align(self):
        import tkinter as tk
        from opencal.workbench import App
        root=tk.Tk();root.withdraw();errors=[]
        root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        try:
            app=App(root);app.doc=fixture();app.doc.edit(16,b'\x02');app.refresh()
            session=app.open_comparison(app.doc.original,'codex reference.bin');root.update()
            delta=abs(session.map_host.editor_table.winfo_rooty()-session.reference_view.table.winfo_rooty())
            self.assertLessEqual(delta,1,f'Side-by-side table headers differ by {delta}px')
            session.map_window.geometry('1050x650');root.update()
            self.assertLessEqual(abs(session.map_host.editor_table.winfo_rooty()-session.reference_view.table.winfo_rooty()),1)
            editor=session.map_host.editor
            def buttons(parent):
                for child in parent.winfo_children():
                    if child.winfo_class() in ('TButton','TMenubutton'):yield child
                    yield from buttons(child)
            for button in buttons(editor):
                self.assertTrue(button.winfo_ismapped(),button.cget('text'))
                self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),editor.winfo_rootx()+editor.winfo_width()+1,button.cget('text'))
            self.assertEqual(errors,[])
            session.close()
        finally:root.destroy()

    def test_live_hex_map_main_undo_and_reference_protection(self):
        import tkinter as tk
        from opencal.workbench import App
        root=tk.Tk();root.withdraw()
        try:
            app=App(root);app.doc=fixture();app.refresh();ref=bytes(app.doc.original)
            app.doc.edit(16,b'\x02\0');app.refresh()
            app.page=16;app.render_hex()
            session=app.open_comparison(ref,'codex comparison.bin');root.update()
            self.assertEqual(len(session.report['changed']),1);self.assertEqual(session.map_host.editor_map['id'],'curve')
            session.address.set('0x10');session.edit_bytes('04 00');root.update()
            self.assertEqual(app.doc.data[16],4);self.assertIn('04 00',app.hex.get('1.0','end'))
            self.assertEqual(session.reference,ref)
            self.assertEqual(session.reference_view.body.cget('bg'),'#2a2e37')
            self.assertEqual(session.reference_view.table.bind('<Double-1>'),'')
            self.assertTrue(session.map_tree.parent('curve').startswith('category:'))
            self.assertLess(session.map_host.editor.winfo_rootx(),session.reference_view.body.winfo_rootx())
            session.value_tree.selection_set('cell:1')
            with patch('opencal.compare_ui.sd.askfloat',return_value=-9):session.value_edit_button.invoke()
            root.update();self.assertEqual(app.doc.data[18],2)
            app.undo();root.update();self.assertEqual(app.doc.data[18],0)
            session.open_in_main();root.update();self.assertEqual(app.editor_map['id'],'curve')
            app.doc.set_map_cell(app.doc.definitions['maps'][0],0,-7);root.update()
            self.assertEqual(app.doc.data[16],6);self.assertEqual(session.value_tree.item('cell:0','values')[1],'-7')
            app.undo();root.update();self.assertEqual(session.value_tree.item('cell:0','values')[1],'-8')
            app.undo();app.undo();root.update();self.assertEqual(session.map_tree.get_children(),())
            self.assertEqual(session.map_host.editor_map['id'],'curve')
            self.assertIn('now matches',session.detail_label.get())
            self.assertEqual(app.doc.data,ref)
            self.assertTrue(app.doc._listeners)
            with patch.object(app,'can_leave',return_value=True):app.close_project()
            root.update();self.assertTrue(session.closed);self.assertFalse(session.document._listeners)
        finally:root.destroy()

    def test_scroll_click_missing_bytes_and_independent_window_close(self):
        import tkinter as tk
        from opencal.workbench import App
        root=tk.Tk();root.withdraw()
        try:
            app=App(root);app.doc=fixture();app.refresh();session=app.open_comparison(app.doc.original+bytes(8192),'codex longer.bin');root.update()
            session.scroll('moveto',1);self.assertTrue(session.first>0)
            session.address.set('0x200');session.goto()
            with self.assertRaises(ValueError):session.edit_bytes('FF')
            self.assertEqual(len(app.doc.data),512)
            session.close_window(session.hex_window);root.update();self.assertFalse(session.closed)
            app.doc.edit(16,b'\x08');root.update();self.assertEqual(len(session.report['changed']),1)
            session.close_window(session.map_window);root.update();self.assertTrue(session.closed)
            self.assertFalse(app.doc._listeners)
        finally:root.destroy()
