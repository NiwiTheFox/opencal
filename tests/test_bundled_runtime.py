import sys,unittest,tkinter as tk
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless((ROOT/'runtime/python.exe').exists(),'Portable runtime checks run in the Windows bundle')
class BundledRuntimeTests(unittest.TestCase):
    def test_interpreter_and_tcl_tk_are_inside_bundle(self):
        self.assertTrue(Path(sys.executable).resolve().is_relative_to(ROOT/'runtime'))
        self.assertEqual(sys.flags.isolated,1)
        root=tk.Tk();root.withdraw()
        try:
            for path in (root.tk.call('info','library'),root.tk.eval('set tk_library')):
                self.assertTrue(Path(path).resolve().is_relative_to(ROOT/'runtime'))
        finally:root.destroy()
