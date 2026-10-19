import tkinter as tk,unittest,struct
from unittest.mock import patch
from opencal.workbench import App
from opencal.core import axis_values
from opencal.table_tools_ui import edit_axis,review
from opencal.table_tools import operation_preview
from tests.test_table_tools import document


class TableWidgetTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.app=App(self.root);self.d,self.m=document();self.app.doc=self.d
        self.app.refresh();self.app.active_map=0;self.app.render_map(0);self.root.update()
    def tearDown(self):self.root.destroy()

    def test_inline_edit_and_undo(self):
        self.app.editor_edit_cell(1);entry=self.app.editor_cell_entry;entry.delete(0,'end');entry.insert(0,'55')
        self.app.editor_cell_commit();self.assertEqual(struct.unpack_from('<H',self.d.data,18)[0],55)
        self.app.undo();self.assertEqual(self.d.data,self.d.original)

    def test_axis_button_preview_apply_undo_and_header_refresh(self):
        self.app.editor_axis_buttons['x_axis'].invoke();self.root.update()
        self.app.axis_drafts[1].set('8');self.app.axis_review_button.invoke();self.root.update()
        self.assertEqual(self.d.data,self.d.original);self.app.table_preview_apply.invoke();self.root.update()
        self.assertEqual(self.app.editor_table.heading('1')['text'],'8')
        self.app.undo();self.assertEqual(self.app.editor_table.heading('1')['text'],'3')
        self.app.redo();self.assertEqual(axis_values(self.d.data,self.m,'x_axis'),[-2,8,13,18])
        self.app.editor_axis_buttons['y_axis'].invoke();self.app.axis_drafts[1].set('2100');self.app.axis_review_button.invoke();self.app.table_preview_apply.invoke()
        self.assertEqual(self.app.editor_table.item('1')['text'],'2100')

    def test_invalid_axis_and_stale_preview_leave_bytes_unchanged(self):
        edit_axis(self.app,self.m,'x_axis');self.app.axis_drafts[3].set('nan')
        with patch('opencal.gui.mb.showerror') as error:self.app.axis_review_button.invoke()
        error.assert_called_once();self.assertEqual(self.d.data,self.d.original)
        self.app.axis_window.destroy();p=operation_preview(self.d.data,self.m,'Set',40,definitions=self.d.definitions);review(self.app,p)
        self.d.edit(0,b'X');before=bytes(self.d.data)
        with patch('opencal.gui.mb.showerror') as error:self.app.table_preview_apply.invoke()
        error.assert_called_once();self.assertEqual(self.d.data,before)

    def test_reversed_display_keeps_storage_cell_mapping(self):
        self.m['x_axis']['display_backwards']=True;self.app.render_map(0);self.root.update()
        self.assertEqual(self.app.editor_table['displaycolumns'],('3','2','1','0'))
        self.app.editor_edit_cell(3);entry=self.app.editor_cell_entry;entry.delete(0,'end');entry.insert(0,'77');self.app.editor_cell_commit()
        self.assertEqual(struct.unpack_from('<4H',self.d.data,16),(10,90,30,77))

    def test_table_graph_and_actions_fit_small_window(self):
        self.root.geometry('1080x700');self.root.update()
        canvas=self.app.editor_canvas
        self.assertGreater(canvas.winfo_height(),65)
        self.assertLessEqual(canvas.winfo_rooty()+canvas.winfo_height(),self.app.editor.winfo_rooty()+self.app.editor.winfo_height())
        self.assertGreater(self.app.editor_table.winfo_height(),60)

    def test_keyboard_row_selection_moves_inline_edit_target(self):
        table=self.app.editor_table;table.selection_set('1');table.focus('1');self.root.update()
        self.app.editor_edit_cell();entry=self.app.editor_cell_entry;entry.delete(0,'end');entry.insert(0,'44');self.app.editor_cell_commit()
        self.assertEqual(struct.unpack_from('<H',self.d.data,24)[0],44)
        self.assertEqual(struct.unpack_from('<H',self.d.data,16)[0],10)
