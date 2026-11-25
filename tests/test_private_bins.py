"""Checks on real ECU files. Skipped unless OPENCAL_PRIVATE_BINS points to a
folder holding them; vehicle firmware is never committed."""
import os
import unittest
from pathlib import Path

from opencal.core import dtc, tuning
from opencal.core.ecufile import EcuFile

ROOT = os.environ.get("OPENCAL_PRIVATE_BINS")


def bins():
    if not ROOT:
        return []
    return sorted(p for p in Path(ROOT).glob("*.bin") if p.stat().st_size == 0x80000)


@unittest.skipUnless(bins(), "set OPENCAL_PRIVATE_BINS to a folder of 512 KB EDC15P files")
class RealFiles(unittest.TestCase):
    def test_each_file(self):
        for p in bins():
            with self.subTest(file=p.name):
                f = EcuFile.load(str(p))
                rep = f.checksum()
                self.assertIsNotNone(rep)
                self.assertTrue(rep.all_ok, rep.summary())
                for kind in ("smoke", "driver_wish", "torque_limiter", "boost_target", "soi"):
                    self.assertTrue(f.find(kind, f.active_bank), f"{kind} missing in {p.name}")
                gs = dtc.groups(f)
                self.assertGreater(len(gs), 20)
                code = next(g for g in gs if g.state == "Enabled").vag_code
                dtc.set_enabled(f, [code], False)
                dtc.set_enabled(f, [code], True)
                self.assertFalse(f.dirty, "DTC enable must restore exact bytes")
                plan = tuning.plan_stage1(f)
                tuning.apply_plan(f, plan)
                f.fix_checksums()
                self.assertTrue(f.checksum().all_ok)


if __name__ == "__main__":
    unittest.main()
