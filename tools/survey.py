"""Run every file in a folder through OpenCal's engine and print a table.

    python tools/survey.py <folder> [--json out.json]

Checks per file: identity, checksum layout, banks, key maps found per bank,
DTC table, multimap code patch, Stage 1 plan + checksum fix round trip.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opencal.core import dtc, multimap, tuning  # noqa: E402
from opencal.core.ecufile import EcuFile  # noqa: E402

KEY = ("driver_wish", "smoke", "torque_limiter", "boost_target", "boost_limit", "n75", "soi", "duration", "egr")


def survey(path: Path) -> dict:
    r = {"file": path.name}
    try:
        f = EcuFile.load(str(path))
    except Exception as e:
        return {**r, "error": str(e)}
    r["id"] = f"{f.info.part_number} {f.info.software}"
    rep = f.checksum()
    r["checksum"] = rep.summary() if rep else "unknown"
    r["checksum_ok"] = bool(rep and rep.all_ok)
    r["banks"] = [(hex(c.base), c.id) for c in f.populated_banks]
    r["maps"] = len(f.maps)
    r["missing"] = {hex(c.base): [k for k in KEY if not f.find(k, c.base)] for c in f.populated_banks}
    try:
        r["dtc"] = len(dtc.groups(f))
    except Exception as e:
        r["dtc"] = f"n/a ({str(e)[:50]})"
    try:
        r["multimap"] = multimap.describe(f)
    except Exception as e:
        r["multimap"] = f"error {e}"
    try:
        plan = tuning.plan_stage1(f)
        tuning.apply_plan(f, plan)
        after = f.fix_checksums()
        r["stage1"] = f"{len(plan.changes)} changes, " + (after.summary() if after else "no checksum")
        r["stage1_ok"] = bool(after and after.all_ok)
    except Exception as e:
        r["stage1"] = f"error {e}"
        r["stage1_ok"] = False
        r["trace"] = traceback.format_exc(limit=3)
    return r


def main():
    folder = Path(sys.argv[1])
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".bin", ".ori") and p.stat().st_size == 0x80000)
    rows = [survey(p) for p in files]
    for r in rows:
        if "error" in r:
            print(f"ERR  {r['file'][:60]:60} {r['error']}")
            continue
        miss = {k: v for k, v in r["missing"].items() if v}
        print(f"{'ok ' if r['checksum_ok'] and r.get('stage1_ok') else 'BAD'}  {r['id']:22} {r['checksum']:28} "
              f"banks={[b[1] for b in r['banks']]} maps={r['maps']} dtc={r['dtc']} mm={r['multimap']} "
              f"{'missing=' + str(miss) if miss else ''}  | {r['file'][:50]}")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(rows, indent=1))
    ok = sum(1 for r in rows if r.get("checksum_ok") and r.get("stage1_ok"))
    print(f"\n{ok}/{len(rows)} files: checksum OK and Stage 1 round trip OK")


if __name__ == "__main__":
    main()
