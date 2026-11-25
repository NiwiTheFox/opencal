"""Headless GUI smoke test (Qt offscreen platform)."""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtWidgets
except ImportError:  # pragma: no cover
    QtWidgets = None

from . import synthetic


@unittest.skipIf(QtWidgets is None, "PySide6 not installed")
class Gui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    def test_open_edit_save(self):
        from opencal.gui import dialogs as dlg
        from opencal.gui.mainwindow import DtcDialog, MainWindow  # noqa: F401
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "syn.bin")
            with open(src, "wb") as fh:
                fh.write(synthetic.build())
            w = MainWindow()
            w.load(src)
            self.assertGreater(w.tree.topLevelItemCount(), 2)
            ed = w.open_map(w.f.first("smoke").key)
            before = ed.model.vals[0, 0]
            ed.table.selectAll()
            ed.op.setCurrentText("+ amount")
            ed.amount.setValue(1)
            ed.apply_op()
            self.assertAlmostEqual(ed.model.vals[0, 0], before + 1, places=2)
            w.undo()
            self.assertAlmostEqual(ed.model.vals[0, 0], before, places=2)
            for cls, args in ((dlg.Stage1Dialog, (w.f,)), (dlg.CodeblockDialog, (w.f,)), (dlg.CalcDialog, (w.f,)),
                              (dlg.DynoDialog, (w.f,)), (dlg.HexView, (w.f,)), (dlg.EcuDialog, ())):
                cls(*args).close()
            out = os.path.join(d, "out.bin")
            ed.apply_op()
            w._do_save(out)
            self.assertTrue(os.path.exists(out))
            w.f.history.clear()
            w.close()


if __name__ == "__main__":
    unittest.main()
