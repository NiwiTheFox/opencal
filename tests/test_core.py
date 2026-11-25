import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from opencal.core import calcs, checksum, kline, logs, mappack, patterns, tuning
from opencal.core.ecufile import EcuFile, EcuFileError
from opencal.core.eeprom import Eeprom, EepromError
from opencal.core.project import Project

from . import synthetic

HERE = Path(__file__).parent


class ChecksumVectors(unittest.TestCase):
    """Arithmetic checked against independently compiled C# vectors."""

    @classmethod
    def setUpClass(cls):
        cls.v = json.loads((HERE / "checksum-csharp-vectors.json").read_text())
        cls.data = bytes.fromhex(cls.v["data_hex"])

    def test_tdi41(self):
        for c in self.v["tdi41"]:
            a, b = c["seeds"]
            self.assertEqual(checksum._tdi41_calc(self.data, c["start"], c["end"], a, b), c["expected"], c)

    def test_tdi41_2002(self):
        for c in self.v["tdi41_2002"]:
            got = checksum._c2002(self.data, c["start"], c["end"], *c["seeds"], c["first"])
            self.assertEqual(got, c["expected"], c)


class Synthetic(unittest.TestCase):
    def setUp(self):
        self.raw = bytes(synthetic.build())
        self.f = EcuFile(self.raw, "synthetic.bin")

    def test_identity_and_codeblocks(self):
        self.assertEqual(self.f.info.part_number, "038906019XX")
        self.assertEqual(self.f.info.software, "SG9999")
        cb = [c for c in self.f.codeblocks if c.populated]
        self.assertEqual([(c.base, c.id) for c in cb], [(0x70000, 3)])
        self.assertTrue(self.f.checksum().all_ok)

    def test_maps_identified(self):
        kinds = {m.kind for m in self.f.maps}
        for k in ("smoke", "driver_wish", "torque_limiter", "boost_target"):
            self.assertIn(k, kinds)
        sm = self.f.first("smoke")
        self.assertEqual((sm.rows, sm.cols), (16, 13))
        self.assertAlmostEqual(sm.values(self.f.buf)[0, 0], (3000 * 0.4 + 800) * 0.01)

    def test_edit_undo_redo_and_checksum(self):
        sm = self.f.first("smoke")
        v = sm.values(self.f.buf)
        self.f.write_map(sm, v + 1)
        self.assertFalse(self.f.checksum().all_ok)
        self.f.fix_checksums()
        self.assertTrue(self.f.checksum().all_ok)
        self.f.undo()
        self.f.undo()
        self.assertFalse(self.f.dirty)
        self.f.redo()
        self.assertTrue(self.f.dirty)

    def test_transaction_rolls_back_on_error(self):
        with self.assertRaises(RuntimeError):
            with self.f.begin() as tx:
                tx.write(0x70100, b"\x01\x02")
                raise RuntimeError
        self.assertFalse(self.f.dirty)

    def test_save_fixes_checksums(self):
        sm = self.f.first("smoke")
        self.f.write_map(sm, sm.values(self.f.buf) * 1.1)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "out.bin")
            self.f.save(p)
            self.assertTrue(checksum.detect(open(p, "rb").read()).all_ok)

    def test_multimap_and_stage1(self):
        filled = tuning.prepare_multimap(self.f, {0x50000: 4, 0x60000: 5})
        self.assertEqual(filled, [0x50000, 0x60000])
        self.assertEqual({c.base: c.id for c in self.f.codeblocks}, {0x50000: 4, 0x60000: 5, 0x70000: 3})
        self.f.fix_checksums()
        self.assertTrue(self.f.checksum().all_ok)
        self.assertEqual(self.f.checksum().n_total, 11)
        plan = tuning.plan_stage1(self.f, tuning.Stage1Params(bank=0x50000))
        self.assertTrue(plan.changes)
        tuning.apply_plan(self.f, plan)
        changed = {m.bank for m, _ in self.f.changed_maps(bytes(self.f.buf[:0x50000 - 0x4000]) + bytes(self.f.buf[0x50000 - 0x4000:]))}
        self.assertEqual(changed, set())
        # plan is refused once the file changed
        with self.assertRaises(EcuFileError):
            tuning.apply_plan(self.f, plan)

    def test_scalars(self):
        s = {x.kind: x for x in patterns.find_scalars(self.f.buf)}
        self.assertEqual(s["svbl"].value(self.f.buf), 2350)
        tuning.set_scalar(self.f, "svbl", 2500)
        self.assertEqual(s["svbl"].value(self.f.buf), 2500)

    def test_preflash_flags_broken_checksum(self):
        self.f.write(0x70200, b"\xAA")
        levels = [x.level for x in tuning.preflash_check(self.f)]
        self.assertIn("error", levels)

    def test_mappack_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            mappack.export_xdf(self.f, os.path.join(d, "m.xdf"))
            mappack.export_json(self.f, os.path.join(d, "m.json"))
            g = EcuFile(self.raw)
            for m in g.maps:
                m.name, m.identified = "", False
            added, skipped = mappack.import_xdf(g, os.path.join(d, "m.xdf"))
            self.assertGreaterEqual(added, 4)
            self.assertEqual(skipped, 0)
            sm = g.map(self.f.first("smoke").key)
            self.assertEqual(sm.name, "Smoke limiter")
            self.assertAlmostEqual(sm.factor, 0.01)

    def test_dyno(self):
        pts = calcs.virtual_dyno(self.f)
        self.assertTrue(pts)
        self.assertTrue(all(p.torque >= 0 for p in pts))

    def test_project_versions(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "a.bin")
            open(src, "wb").write(self.raw)
            p = Project.create(src, os.path.join(d, "proj"))
            i = p.add_version(self.raw[:10] + b"x" + self.raw[11:], "test")
            self.assertEqual(i, 1)
            self.assertEqual(len(Project.list(os.path.join(d, "proj"))[0].versions), 2)

    def test_rejects_wrong_size(self):
        with self.assertRaises(EcuFileError):
            EcuFile(b"\x00" * 1000)


class Calcs(unittest.TestCase):
    def test_air_and_lambda(self):
        e = calcs.EngineSpec()
        air = calcs.air_mg_per_stroke(2200, e)
        self.assertTrue(900 < air < 1100)
        self.assertAlmostEqual(calcs.lam(air, air / 14.5), 1.0)
        self.assertGreater(calcs.boost_for_iq(50, 1.25, e), 1800)


class Eeproms(unittest.TestCase):
    def test_immo_vin(self):
        ee = Eeprom.from_bytes(bytes(512))
        ee.set_immo(False)
        self.assertFalse(ee.immo_active)
        self.assertEqual(ee.data[0x1DE], 0x60)
        ee.set_vin("WVWZZZ1JZ3W000001")
        self.assertEqual(ee.vin, "WVWZZZ1JZ3W000001")
        with self.assertRaises(EepromError):
            ee.set_vin("short")


class KLine(unittest.TestCase):
    def test_frame_roundtrip(self):
        fr = kline.frame(bytes([0x1A, 0x9B]))
        self.assertEqual(kline.parse_frame(fr), (0x01, 0xF1, bytes([0x1A, 0x9B])))
        with self.assertRaises(kline.KLineError):
            kline.parse_frame(fr[:-1] + b"\x00")

    def test_simulated_session(self):
        s = kline.Session(kline.SimulatedEcu())
        s.connect()
        self.assertIn("038906019FJ", s.identify())
        self.assertEqual(len(s.read_dtcs()), 2)
        s.clear_dtcs()
        self.assertEqual(s.read_dtcs(), [])
        units = [v.unit for v in s.read_group(1)]
        self.assertEqual(units, ["rpm", "mg/st", "mbar", "°C"])

    def test_triplet_decoding(self):
        self.assertAlmostEqual(kline.decode_triplet(0x01, 250, 48).value, 2400)
        self.assertAlmostEqual(kline.decode_triplet(0x05, 10, 185).value, 85)


class Logs(unittest.TestCase):
    def test_vcds_csv(self):
        text = ("Marke,Group A:,'001,,\n,Engine speed,Injection quantity,Boost pressure\n"
                ",/min,mg/str,mbar\n1,900,5.2,1010\n2,2000,30.1,1900\n")
        lg = logs.parse_csv(text)
        self.assertEqual(set(lg.columns), {"rpm", "iq", "boost"})
        ov = logs.overlay(lg, [1000, 2000], [5, 30], "rpm", "iq", "boost")
        self.assertEqual(int(ov.counts.sum()), 2)
        self.assertEqual(float(ov.mean[1, 1]), 1900.0)


if __name__ == "__main__":
    unittest.main()
