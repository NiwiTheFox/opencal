# Dev note: SVRL rev limiter (for the next release)

Reported by the user: the virtual dyno ignores the SVRL rev limiter, so fuel
(and pop/bang/overrun) keeps going past the rev limit instead of being cut.

## What SVRL is
SVRL = single-value **rev** limiter (engine speed, rpm). Distinct from SVBL
(single-value **boost** limiter, mbar, already detected at the `D2 00 FC 03…`
pattern in `patterns.py`).

## Where it is (confirmed, SG1376)
- File offset **0x740F6**, stored as **plain rpm** (no scaling).
- SG1376 stock value = **5300** rpm.
- Confirmed with the user's own files:
  - `POPCORN - EDITED 3 4400 SVRL.bin` sets 0x740F6 = **4400** (matches the
    "4400 SVRL" in the filename exactly).
  - `POPCORN - EDIT.bin` = 4250 at the same offset.
- 0x740F6 is bank-relative 0x40F6 (page 0x70000 bank). For multi-bank files the
  limiter likely exists per bank at base+0x40F6 — verify.

## Still to do
1. Detect SVRL as a scalar. 0x740F6 is software-specific, so locate it by a byte
   pattern around it (dump 0x740E0-0x74120 of a known file for the signature) or
   by bank+0x40F6, not a hard address. Add to `patterns.find_scalars` with
   kind `"svrl"`, unit `"rpm"`, factor 1.0.
2. Related pop/overrun fuel that the popcorn files zero: 0x76FE4 / 0x76FFE /
   0x77018 (7500 -> 0 in the popcorn edit). Worth surfacing too.
3. Dyno (`sim.py`): cut fuel to 0 (or the overrun value) when rpm >= SVRL, and
   end the pull there, instead of the fixed `p.end_rpm`. Default end_rpm should
   follow SVRL when found. Add an event "rev limiter (SVRL) at N rpm".
4. Test against the popcorn/hardcut SG1376 files in bin-tests.

This did NOT make it into 2.1.1 (which was dyno torque model + codeblock
labelling only). Target 2.1.2.
