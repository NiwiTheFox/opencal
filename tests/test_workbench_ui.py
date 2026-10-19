"""Widget-level regressions for scalar identity, edits and workspace layout."""
import copy,struct,tkinter as tk,unittest
from unittest.mock import patch
from opencal.workbench import App
from opencal.core import Document
from tests.test_core import definitions
from tests.private_fixtures import STOCK


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.root.withdraw(); self.app=App(self.root)
        data=bytearray(128); struct.pack_into('<HH',data,16,5300,2375)
        base=definitions()['maps'][0]
        maps=[]
        for i,(name,unit) in enumerate([('SVRL - RPM limiter','rpm'),('SVBL boost limiter','mbar')]):
            m=copy.deepcopy(base); m.update(id=str(i),name=name,address=16+i*2,rows=1,columns=1,factor=1,offset=0,unit=unit)
            m.pop('minimum');m.pop('maximum'); maps.append(m)
        self.app.doc=Document(data);self.app.doc.definitions={'schema':'opencal.definitions','version':1,'maps':maps}
        self.app.refresh();self.root.update()

    def tearDown(self): self.root.destroy()

    def test_svl_shortcuts_select_different_units_and_values(self):
        self.app.jump_to_map('SVRL');self.root.update()
        self.assertEqual(self.app.editor_scalar_value.get(),'5300 rpm')
        self.assertIsNone(self.app.editor_canvas)
        self.app.jump_to_map('SVBL');self.root.update()
        self.assertEqual(self.app.editor_scalar_value.get(),'2375 mbar')
        self.assertEqual(self.app.editor_graph_mode.get(),'Single value')

    def test_scalar_apply_undo_and_invalid_value_preserve_other_bytes(self):
        self.app.jump_to_map('SVRL'); before=bytes(self.app.doc.data)
        self.app.editor_scalar_draft.set('5400');self.app.editor_scalar_apply.invoke()
        self.assertEqual(struct.unpack_from('<H',self.app.doc.data,16)[0],5400)
        self.assertEqual(self.app.doc.data[:16],before[:16]);self.assertEqual(self.app.doc.data[18:],before[18:])
        self.app.undo(); self.assertEqual(self.app.doc.data,before)
        self.app.editor_scalar_draft.set('nan')
        with patch('opencal.gui.mb.showerror') as error:self.app.editor_scalar_apply.invoke()
        error.assert_called_once();self.assertEqual(self.app.doc.data,before)

    def test_sidebar_initial_width_and_user_resize_are_preserved(self):
        self.root.deiconify();self.root.update()
        self.assertLessEqual(self.app.panes.sashpos(0),340)
        self.app.panes.sashpos(0,410);self.root.geometry('1300x850');self.root.update()
        self.assertGreaterEqual(self.app.panes.sashpos(0),400)

    def test_scalar_raw_mode_survives_refresh(self):
        self.app.doc.definitions['maps'][0].update(factor=.5,offset=10)
        self.app.jump_to_map('SVRL');self.app.editor_value_mode.set('Raw')
        self.app.editor_scalar_draft.set('5400');self.app.editor_scalar_apply.invoke()
        self.assertEqual(self.app.editor_value_mode.get(),'Raw')
        self.assertEqual(self.app.editor_scalar_value.get(),'5400 raw')

    @unittest.skipUnless(STOCK.exists(),'Private copied stock unavailable')
    def test_stock_rpm_and_boost_are_not_confused(self):
        from opencal.edc15 import discover
        self.app.doc=Document(STOCK.read_bytes(),STOCK);self.app.doc.definitions=discover(self.app.doc.data)
        self.app.active_map=None;self.app.refresh()
        self.app.jump_to_map('SVRL');self.assertEqual(self.app.editor_scalar_value.get(),'5300 rpm')
        self.app.jump_to_map('SVBL');self.assertEqual(self.app.editor_scalar_value.get(),'2375 mbar')
