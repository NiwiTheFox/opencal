import unittest

from opencal.core import checksum, multimap, sim, units
from opencal.core.ecufile import ChecksumLayoutUnknown, EcuFile

from . import synthetic


class Units(unittest.TestCase):
    def tearDown(self):
        for fam, spec in units.FAMILIES.items():
            units.set_choice(fam, spec["native"])

    def test_roundtrip(self):
        units.set_choice("pressure", "bar")
        c = units.conv("mbar")
        self.assertEqual(c.shown, "bar")
        self.assertAlmostEqual(c.to_shown(2350), 2.35)
        self.assertAlmostEqual(c.to_native(2.1), 2100)
        units.set_choice("power", "kW")
        self.assertAlmostEqual(units.conv("hp").to_shown(100), 73.549875, places=4)
        units.set_choice("temperature", "°F")
        self.assertAlmostEqual(units.conv("°C").to_shown(100), 212, places=6)
        self.assertTrue(units.conv("rpm").identity)


class ChecksumLock(unittest.TestCase):
    def test_layout_locked_at_load(self):
        f = EcuFile(bytes(synthetic.build()))
        self.assertEqual(f.checksum_layout, "tdi41_2002")
        self.assertFalse(f.checksum_uncertain)

    def test_uncertain_file_refuses_to_guess(self):
        b = synthetic.build()
        b[0x70100] ^= 0xFF               # break a checksum before "loading"
        f = EcuFile(bytes(b))
        self.assertIsNone(f.checksum_layout)
        self.assertTrue(f.checksum_uncertain)
        with self.assertRaises(ChecksumLayoutUnknown):
            f.fix_checksums()
        f.set_checksum_layout("tdi41_2002")
        self.assertTrue(f.fix_checksums().all_ok)

    def test_candidates_sorted(self):
        reps = checksum.candidates(synthetic.build())
        self.assertEqual(reps[0].layout, "tdi41_2002")


class Multimap(unittest.TestCase):
    def test_code_patch_detected(self):
        stock = bytes(synthetic.build())
        mod = bytearray(stock)
        mod[0x1A000:0x1A010] = bytes(range(16))     # routine in "free" flash (not C3 in fixture, still a range)
        mod[0x10EEE] ^= 0x01                        # a hook
        f = EcuFile(bytes(mod))
        p = multimap.code_patch(f, stock)
        self.assertTrue(p.present)
        self.assertGreaterEqual(len(p.ranges), 2)
        self.assertIn("code patch", multimap.describe(f, stock))
        self.assertIn("identical", multimap.describe(EcuFile(stock), stock))


class Simulation(unittest.TestCase):
    def test_start_and_pull(self):
        f = EcuFile(bytes(synthetic.build()))
        r = sim.simulate(f)
        self.assertTrue(r.started)
        self.assertIsNotNone(r.peak_power)
        pull = [s for s in r.samples if s.phase == "pull"]
        self.assertGreater(pull[-1].rpm, pull[0].rpm)
        self.assertTrue(all(s.boost >= 900 for s in pull))
        levels = {e.level for e in r.events}
        self.assertIn("ok", levels)


if __name__ == "__main__":
    unittest.main()


class CodeblockLabelling(unittest.TestCase):
    def test_base_first_and_labels(self):
        import tempfile, os
        from opencal.core.ecufile import EcuFile
        # build a 3-bank multimap from the synthetic single-map file
        base = synthetic.build()
        f = EcuFile(bytes(base))
        from opencal.core import tuning
        tuning.prepare_multimap(f, {0x50000: 4, 0x60000: 5})
        banks = f.populated_banks
        # base map (0x70000, the single-map bank) must come first
        self.assertTrue(banks[0].is_base)
        self.assertEqual(banks[0].base, 0x70000)
        self.assertIn("base map", banks[0].label())
        # every bank labelled by its codeblock id, never by position
        ids = {cb.base: cb.id for cb in banks}
        self.assertEqual(ids, {0x70000: 3, 0x50000: 4, 0x60000: 5})
        for cb in banks:
            self.assertIn(f"Codeblock {cb.id}", cb.label())
        # exactly one base
        self.assertEqual(sum(cb.is_base for cb in banks), 1)


class DynoPhysics(unittest.TestCase):
    def test_power_peaks_then_falls(self):
        from opencal.core import sim
        f = _mk()
        r = sim.simulate(f)
        pull = [s for s in r.samples if s.phase == "pull"]
        self.assertTrue(pull)
        pk = max(range(len(pull)), key=lambda i: pull[i].power)
        # peak power is not at the very last sample: the curve falls toward redline
        self.assertLess(pk, len(pull) - 1)
        # brake torque falls off at high rpm for the same fuel (friction + combustion)
        import numpy as np
        air = 9000.0
        e = sim.calcs.EngineSpec()
        self.assertGreater(sim.brake_torque(45, 2000, air, e), sim.brake_torque(45, 4500, air, e))
        # air-limited: no torque beyond what the air can burn
        self.assertAlmostEqual(sim.brake_torque(80, 2000, 1000, e),
                               sim.brake_torque(100, 2000, 1000, e), places=3)

    def test_limiter_edits_change_output(self):
        from opencal.core import sim
        f = _mk()
        p0 = max(s.power for s in sim.simulate(f).samples if s.phase == "pull")
        dw = f.first("driver_wish")
        f.write_map(dw, dw.values(f.buf) * 0.5)
        p1 = max(s.power for s in sim.simulate(f).samples if s.phase == "pull")
        self.assertLess(p1, p0 * 0.9)


def _mk():
    from opencal.core.ecufile import EcuFile
    return EcuFile(bytes(synthetic.build()))
