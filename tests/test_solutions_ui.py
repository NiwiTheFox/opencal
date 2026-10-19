import tkinter as tk,unittest
from opencal.workbench import App
from opencal.core import Document
from opencal.edc15 import discover
from opencal.solutions import preview_launch_control,apply_preview
from tests.test_solutions import fixture


class SolutionsWidgetTests(unittest.TestCase):
    def test_apply_undo_redo_restore_updates_definition_and_status(self):
        root=tk.Tk();root.withdraw()
        try:
            app=App(root);data,_=fixture();app.doc=Document(data);app.doc.definitions=discover(data);app.refresh();root.update()
            self.assertIn('Available',app.solution_status.get())
            apply_preview(app.doc,preview_launch_control(app.doc.data));app.refresh();root.update()
            self.assertIn('Active',app.solution_status.get())
            index=next(i for i,m in enumerate(app.doc.definitions['maps']) if m['id'].startswith('launch-control-'))
            app.active_map=index;app.render_map(index);root.update()
            self.assertEqual(len(app.editor_table.get_children()),14)
            app.undo();root.update()
            self.assertFalse(any(m['id'].startswith('launch-control-') for m in app.doc.definitions['maps']))
            self.assertIsNone(app.active_map)
            self.assertEqual(app.doc.data,data)
            app.redo();root.update();self.assertIn('Active',app.solution_status.get())
            apply_preview(app.doc,preview_launch_control(app.doc.data,app.doc.original));app.refresh()
            self.assertEqual(app.doc.data,data)
            self.assertIn('Available',app.solution_status.get())
        finally:root.destroy()
