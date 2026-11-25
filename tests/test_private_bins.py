"""Checks on real ECU files. Skipped unless OPENCAL_PRIVATE_BINS points to a
folder holding them; vehicle firmware is never committed."""
import os
import unittest
from pathlib import Path

from opencal.core import dtc, sim, tuning
from opencal.core.ecufile import EcuFile

ROOT = os.environ.get("OPENCAL_PRIVATE_BINS")
KEY = ("smoke", "driver_wish", "torque_limiter", "boost_target", "soi")
# Older "compact" EDC15P software with a different table structure: identification is partial.
KNOWN_LIMITED = {"SG1086"}


def bins():
    if not ROOT:
        return []
    return sorted(p for p in Path(ROOT).iterdir()
                  if p.suffix.lower() in (".bin", ".ori") and p.stat().st_size == 0x80000)


@unittest.skipUnless(bins(), "set OPENCAL_PRIVATE_BINS to a folder of 512 KB EDC15P files")
class RealFiles(unittest.TestCase):
    def test_each_file(self):
        checked = 0
        for p in bins():
            with self.subTest(file=p.name):
                f = EcuFile.load(str(p))
                if not f.populated_banks or f.checksum_layout is None:
                    # unknown layout or arrived with bad checksums: must refuse to guess
                    if f.checksum_layout is None and f.populated_banks:
                        with self.assertRaises(Exception):
                            f.fix_checksums()
                    continue
                checked += 1
                self.assertTrue(f.checksum().all_ok)
                found = sum(1 for k in KEY if f.find(k, f.active_bank))
                if f.info.software not in KNOWN_LIMITED:
                    self.assertGreaterEqual(found, 4, f"key maps found: {found}/5")
                gs = dtc.groups(f)
                self.assertGreater(len(gs), 20)
                code = next(g for g in gs if g.state == "Enabled").vag_code
                dtc.set_enabled(f, [code], False)
                dtc.set_enabled(f, [code], True)
                self.assertFalse(f.dirty, "DTC enable must restore exact bytes")
                tuning.apply_plan(f, tuning.plan_stage1(f))
                f.fix_checksums()
                self.assertTrue(f.checksum().all_ok)
                self.assertTrue(sim.simulate(f).started)
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
