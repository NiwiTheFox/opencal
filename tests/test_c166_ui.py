import tempfile,tkinter as tk,unittest,json
from pathlib import Path
from unittest.mock import patch
from opencal.workbench import App
from opencal.core import Document


class CodeWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.app=App(self.root);self.app.doc=Document(bytes(512));self.app.refresh()
        self.workspace=self.app.open_code_workspace();self.root.update();self.workspace.state['segments']=[{'file':0,'cpu':0x80000,'size':512}]
    def tearDown(self):
        if not self.workspace.closed:self.workspace.close()
        self.root.destroy()
    def source(self,value):
        self.workspace.source.delete('1.0','end');self.workspace.source.insert('1.0',value);self.workspace.source_changed();self.root.update()
    def test_preview_apply_main_undo_redo_and_source_project_roundtrip(self):
        w=self.workspace;self.source('start: mov r3,#01234h\n jmpr uc,start')
        op=w.assemble();self.root.update();self.assertEqual(self.app.doc.data,bytes(512))
        self.assertTrue(w.apply_button.winfo_ismapped());self.assertGreater(w.apply_button.winfo_width(),100)
        w.apply_button.invoke();self.root.update();self.assertEqual(self.app.doc.data[:6],bytes.fromhex('e6f334120dfd'))
        self.assertIn('MOV',w.rows['0']['text']);self.assertIn('E6 F3 34 12',self.app.hex.get('1.0','end'))
        self.app.undo();self.assertEqual(self.app.doc.data,bytes(512));self.app.redo();self.assertEqual(self.app.doc.data[:4],bytes.fromhex('e6f33412'))
        self.app.doc.code_workspace['labels']['0']='entry';self.app.doc.code_workspace['comments']['0']='synthetic'
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'codex code.ocproj';self.app.doc.save_project(p);loaded=Document.load_project(p)
            self.assertEqual(loaded.code_workspace['source'],w.source.get('1.0','end-1c'));self.assertEqual(loaded.code_workspace['labels']['0'],'entry');self.assertEqual(loaded.data,self.app.doc.data)
    def test_stale_source_project_and_mapping_refused_without_edits(self):
        w=self.workspace;self.source('nop');w.assemble();self.source('ret')
        with patch('opencal.gui.mb.showerror') as error:w.apply_button.invoke();error.assert_called_once()
        self.assertEqual(self.app.doc.data,bytes(512));w.preview_window.destroy()
        w.assemble();w.state['segments']=[{'file':0,'cpu':0x90000,'size':512}]
        with patch('opencal.gui.mb.showerror') as error:w.apply_button.invoke();error.assert_called_once()
        w.preview_window.destroy();w.assemble();old=self.app.doc;self.app.doc=Document(bytes(512))
        with patch('opencal.gui.mb.showerror') as error:w.apply_button.invoke();error.assert_called_once()
        self.assertEqual(old.data,bytes(512));self.assertEqual(self.app.doc.data,bytes(512));self.app.refresh();self.assertTrue(w.closed)
    def test_navigation_search_and_listener_cleanup(self):
        w=self.workspace;self.source('start: nop\n jmpr uc,start');w.assemble();w.apply_button.invoke();self.root.update()
        w.tree.selection_set('2');w.follow();self.assertEqual(w.address.get(),'0x0')
        w.query.set('JMPR');w.find();self.assertEqual(w.tree.selection(),('2',))
        count=len(self.app.doc._listeners);w.close();self.assertEqual(len(self.app.doc._listeners),count-1)
    def test_source_notes_and_mapping_mark_project_dirty(self):
        self.app.saved_state=self.app.state();self.source('nop\n ret')
        self.assertNotEqual(self.app.state(),self.app.saved_state)
        self.app.saved_state=self.app.state();self.workspace.state['comments']['0']='changed'
        self.assertNotEqual(self.app.state(),self.app.saved_state)

    def test_minimum_workspace_controls_remain_visible(self):
        from tkinter import ttk
        w=self.workspace;w.window.geometry('1020x650+30+30');self.root.update()
        buttons=[]
        def visit(parent):
            for child in parent.winfo_children():
                if isinstance(child,ttk.Button):buttons.append(child)
                visit(child)
        visit(w.window)
        self.assertTrue(buttons)
        left=w.window.winfo_rootx();right=left+w.window.winfo_width();top=w.window.winfo_rooty();bottom=top+w.window.winfo_height()
        for button in buttons:
            self.assertTrue(button.winfo_ismapped(),button.cget('text'))
            self.assertGreaterEqual(button.winfo_rootx(),left,button.cget('text'));self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),right,button.cget('text'))
            self.assertGreaterEqual(button.winfo_rooty(),top);self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),bottom,button.cget('text'))
