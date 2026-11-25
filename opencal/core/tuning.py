"""Tuning operations on an EcuFile. Each one is a single undo step."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import maps as M
from . import patterns
from .ecufile import EcuFile, EcuFileError

STOICH = 14.5               # diesel stoichiometric AFR
MAP_SENSOR_CEILING = 2450   # mbar, practical top of the stock 2.5 bar sensor


# ------------------------------------------------------------ codeblocks --

def copy_codeblock(f: EcuFile, src: int, dst: int, new_id: int | None = None) -> None:
    """Copy the whole calibration of bank ``src`` into bank ``dst``."""
    if src == dst:
        raise EcuFileError("Source and target are the same bank.")
    s0, d0 = src - 0x4000, dst - 0x4000
    data = bytes(f.buf[s0:s0 + 0x10000])
    with f.begin() as tx:
        tx.write(d0, data, f"codeblock {src >> 16:X} copied to {dst >> 16:X}")
        if new_id is not None:
            _write_id(f, tx, dst, new_id)
    f.rescan()


def _write_id(f, tx, base, new_id):
    ptr = M.u16(f.buf, base + 0x1002) + base
    if not base <= ptr < base + 0xFFFF:
        raise EcuFileError("This bank has no codeblock id pointer.")
    tx.write(ptr, bytes([new_id & 0xFF, (new_id >> 8) & 0xFF]), f"codeblock id set to {new_id}")


def set_codeblock_id(f: EcuFile, base: int, new_id: int) -> None:
    with f.begin() as tx:
        _write_id(f, tx, base, new_id)
    f.rescan()


def clear_codeblock(f: EcuFile, base: int) -> None:
    with f.begin() as tx:
        tx.write(base - 0x4000, b"\xC3" * 0x10000, f"codeblock {base >> 16:X} emptied")
    f.rescan()


def prepare_multimap(f: EcuFile, ids: dict[int, int] | None = None) -> list[int]:
    """Fill every empty bank with a copy of the active calibration.

    ``ids`` maps bank base -> codeblock id. Returns the banks that were filled.
    The ECU picks the codeblock whose id matches its coding; with distinct
    ids per bank, changing the coding (VCDS, 01 > 07) selects the map.
    """
    src = f.active_bank
    filled = []
    for cb in f.codeblocks:
        if cb.populated or cb.base == src:
            continue
        nid = (ids or {}).get(cb.base)
        copy_codeblock(f, src, cb.base, nid)
        filled.append(cb.base)
    return filled


def repair_bank(f: EcuFile, base: int) -> list[M.Map]:
    """Copy maps that are all-zero/empty in ``base`` from the active bank."""
    src = f.active_bank
    fixed = []
    with f.begin() as tx:
        for m in f.maps:
            if m.bank != base or not m.identified:
                continue
            d = m.raw(f.buf)
            if np.all(d == 0) or np.all(d == 0xC3C3):
                twin = f.map(f"{m.address - base + src:05X}")
                if twin is not None and twin.same_shape(m):
                    tx.write(m.address, bytes(f.buf[twin.address:twin.end]), f"{m.name} repaired from bank {src >> 16:X}")
                    fixed.append(m)
    return fixed


# ----------------------------------------------------------- one-offs ----

def egr_off(f: EcuFile, bank: int | None = None, mg: float = 850.0) -> list[M.Map]:
    """Raise every EGR airflow target so the valve stays shut.

    For off-road / competition use. Raising the target above the airflow the
    engine can reach closes the EGR valve without fault codes.
    """
    bank = f.active_bank if bank is None else bank
    egr = f.find("egr", bank)
    with f.begin() as tx:
        for m in egr:
            v = np.full((m.rows, m.cols), mg)
            raw = m.to_raw(v)
            tx.write(m.address, (raw & 0xFFFF).astype("<u2").tobytes(), "EGR off (race use)")
    return egr


def duplicate_smoke(f: EcuFile, bank: int | None = None) -> list[M.Map]:
    """Copy the smoke limiter onto its sister tables in the same bank."""
    bank = f.active_bank if bank is None else bank
    src = f.first("smoke", bank)
    if src is None:
        raise EcuFileError("No smoke limiter in this bank.")
    sisters = [m for m in f.maps if m is not src and m.bank == bank and m.same_shape(src)
               and m.x.id == src.x.id and m.y and m.y.id == src.y.id and 0 < m.address - src.address < 0x800]
    data = bytes(f.buf[src.address:src.end])
    with f.begin() as tx:
        for m in sisters:
            tx.write(m.address, data, "smoke limiter duplicated")
    return sisters


def set_scalar(f: EcuFile, kind: str, raw: int) -> patterns.Scalar:
    s = next((s for s in patterns.find_scalars(f.buf) if s.kind == kind), None)
    if s is None:
        raise EcuFileError(f"No {kind} found in this file.")
    f.write(s.address, bytes([raw & 0xFF, (raw >> 8) & 0xFF]), f"{s.name} = {raw}")
    return s


def map_sensor_linearization(f: EcuFile, v_lo: float, p_lo: float, v_hi: float, p_hi: float,
                             vref: float = 5.0, adc_max: int = 1023) -> list[float]:
    """Rewrite the MAP linearization for a sensor with a linear transfer.

    The curve's axis holds ADC counts; the values the pressure at each.
    The sensor is given by two points (volts, mbar) from its datasheet.
    """
    m = f.first("map_lin")
    if m is None:
        raise EcuFileError("No MAP linearization found.")
    adc = m.col_axis.raw(f.buf)
    volts = adc * vref / adc_max
    slope = (p_hi - p_lo) / (v_hi - v_lo)
    p = p_lo + (volts - v_lo) * slope
    f.write_map(m, np.round(p).reshape(m.rows, m.cols), "MAP sensor linearization")
    return [float(x) for x in p]


def activate_launch_control(f: EcuFile) -> int:
    """Give the dormant launch-control table a real vehicle-speed axis.

    Experimental: verify with logs before relying on it.
    """
    sites = patterns.launch_sites(f.buf)
    if not sites:
        raise EcuFileError("Launch control is already active or this software has none.")
    axis = [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200, 220, 240, 260]
    payload = bytes([0x0E, 0x00]) + b"".join(v.to_bytes(2, "little") for v in axis)
    with f.begin() as tx:
        for a in sites:
            tx.write(a + 2, payload, "launch control activated")
    f.rescan()
    return len(sites)


# ---------------------------------------------------------- auto stage 1 --

@dataclass
class Stage1Params:
    fuel_gain: float = 0.15          # +15 % fuel at full load
    max_iq: float = 52.0             # mg/st ceiling
    boost_add: float = 150.0         # mbar on top of stock plateau
    boost_cap: float = MAP_SENSOR_CEILING
    min_lambda: float = 1.20         # smoke limit at full load
    bank: int | None = None


@dataclass
class PlannedChange:
    map: M.Map
    new_raw: np.ndarray
    summary: str


@dataclass
class Plan:
    changes: list[PlannedChange] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    signature: bytes = b""


def _scale_full_load(vals: np.ndarray, gain: float, cap: float, frac_from: float = 0.6) -> np.ndarray:
    """Raise the upper part of a fuel table, more at the top, capped."""
    peak = float(vals.max()) or 1.0
    w = np.clip((vals / peak - frac_from) / (1 - frac_from), 0, 1)
    out = vals * (1 + gain * w)
    return np.minimum(out, np.maximum(vals, cap))


def plan_stage1(f: EcuFile, p: Stage1Params = Stage1Params()) -> Plan:
    bank = f.active_bank if p.bank is None else p.bank
    plan = Plan(signature=bytes(f.buf))

    def add(m, new_vals, text):
        raw = m.to_raw(new_vals)
        if not np.array_equal(raw, m.raw(f.buf)):
            plan.changes.append(PlannedChange(m, raw, text))

    dw = f.first("driver_wish", bank)
    if dw is not None:
        v = dw.values(f.buf)
        add(dw, _scale_full_load(v, p.fuel_gain, p.max_iq), f"Driver wish: full pedal +{p.fuel_gain:.0%}, max {p.max_iq:g} mg")

    tl = f.first("torque_limiter", bank)
    if tl is not None:
        v = tl.values(f.buf)
        add(tl, np.minimum(v * (1 + p.fuel_gain), np.maximum(v, p.max_iq)), f"Torque limiter +{p.fuel_gain:.0%}")

    sm = f.first("smoke", bank)
    if sm is not None:
        v = sm.values(f.buf)
        air = sm.y.values(f.buf)[None, :]
        lam_cap = air / (STOICH * p.min_lambda)
        new = np.minimum(np.maximum(v, np.minimum(v * (1 + p.fuel_gain), lam_cap)), np.maximum(v, p.max_iq))
        add(sm, new, f"Smoke limiter +{p.fuel_gain:.0%} where lambda stays ≥ {p.min_lambda:g}")

    iqm = f.first("iq_by_map", bank)
    if iqm is not None:
        v = iqm.values(f.buf)
        add(iqm, np.maximum(v, np.minimum(v * (1 + p.fuel_gain), np.maximum(v, p.max_iq))), "IQ by MAP limiter raised")

    bt = f.first("boost_target", bank)
    if bt is not None:
        v = bt.values(f.buf)
        peak = float(v.max())
        w = np.clip((v - 1000) / max(peak - 1000, 1), 0, 1)
        new = np.minimum(v + p.boost_add * w, p.boost_cap)
        add(bt, np.maximum(new, np.minimum(v, p.boost_cap)), f"Boost target +{p.boost_add:g} mbar at the plateau, cap {p.boost_cap:g}")
        target_peak = float(np.max(new))
        bl = f.first("boost_limit", bank)
        if bl is not None:
            lv = bl.values(f.buf)
            add(bl, np.maximum(lv, np.minimum(lv + p.boost_add + 100, p.boost_cap + 100)), "Boost limit raised above the new target")
        sv = next((s for s in patterns.find_scalars(f.buf) if s.kind == "svbl"), None)
        if sv is not None and sv.value(f.buf) < target_peak + 150:
            plan.notes.append(f"SVBL will be set to {int(min(target_peak + 150, 2550))} mbar.")
            plan.svbl = int(min(target_peak + 150, 2550))  # type: ignore[attr-defined]
    plan.notes.append("A base map built from this file's own calibration. Verify it with logs or a dyno.")
    return plan


def apply_plan(f: EcuFile, plan: Plan) -> None:
    if bytes(f.buf) != plan.signature:
        raise EcuFileError("The file changed since this plan was made. Make the plan again.")
    with f.begin() as tx:
        for c in plan.changes:
            tx.write(c.map.address, (c.new_raw & 0xFFFF).astype("<u2").tobytes(), "Auto Stage 1")
        svbl = getattr(plan, "svbl", None)
        if svbl:
            s = next(s for s in patterns.find_scalars(f.buf) if s.kind == "svbl")
            tx.write(s.address, bytes([svbl & 0xFF, svbl >> 8]), "Auto Stage 1")


# ------------------------------------------------------- pre-flash check --

@dataclass
class Finding:
    level: str      # "error" | "warning" | "ok"
    text: str


def preflash_check(f: EcuFile) -> list[Finding]:
    out: list[Finding] = []
    rep = f.checksum()
    if rep is None:
        out.append(Finding("error", "Checksums: no known layout for this ECU. Do not flash."))
    elif not rep.all_ok:
        out.append(Finding("error", f"Checksums bad. {rep.n_ok} of {rep.n_total} correct. Run Fix checksums."))
    else:
        out.append(Finding("ok", f"Checksums OK ({rep.layout}, {rep.n_total} blocks)."))

    sv = next((s for s in patterns.find_scalars(f.buf) if s.kind == "svbl"), None)
    for cb in f.populated_banks:
        tag = f"codeblock {cb.id if cb.id is not None else '?'} ({cb.base >> 16:X}xxxx)"
        empty = [m.name for m in f.maps if m.bank == cb.base and m.identified and m.kind in
                 ("driver_wish", "smoke", "torque_limiter", "boost_target", "soi", "duration")
                 and np.all(m.raw(f.buf) == 0)]
        if empty:
            out.append(Finding("error", f"{tag}: empty maps ({', '.join(sorted(set(empty))[:4])}). "
                                        "Selecting that map stops the engine. Use Repair bank."))
        bt = f.first("boost_target", cb.base)
        bl = f.first("boost_limit", cb.base)
        if bt is not None:
            peak = float(bt.values(f.buf).max())
            if peak > MAP_SENSOR_CEILING:
                out.append(Finding("warning", f"{tag}: boost target {peak:.0f} mbar exceeds the ~{MAP_SENSOR_CEILING} mbar MAP-sensor ceiling."))
            if bl is not None and float(bl.values(f.buf).max()) < peak:
                out.append(Finding("warning", f"{tag}: boost limit map is below the boost target; overboost limp mode likely."))
            if sv is not None and sv.value(f.buf) < peak:
                out.append(Finding("warning", f"SVBL {sv.value(f.buf):.0f} mbar is below the {tag} boost target {peak:.0f} mbar."))
        dw = f.first("driver_wish", cb.base)
        sm = f.first("smoke", cb.base)
        if dw is not None and sm is not None:
            dmax, smax = float(dw.values(f.buf).max()), float(sm.values(f.buf).max())
            if smax >= 65:
                out.append(Finding("warning", f"{tag}: smoke limiter allows {smax:.0f} mg, effectively off. Expect smoke."))
        for e in eoi_table(f, cb.base) or []:
            if e[2] < -15:
                out.append(Finding("warning", f"{tag}: end of injection {abs(e[2]):.0f}° ATDC at {e[0]:.0f} rpm, {e[1]:.0f} mg (hot)."))
                break
    if not any(x.level != "ok" for x in out):
        out.append(Finding("ok", "No problems found by the heuristic checks."))
    return out


# --------------------------------------------------------------- EOI ------

def eoi_table(f: EcuFile, bank: int | None = None, soi_index: int = 6, dur_index: int = 1):
    """End of injection (deg BTDC, negative = after TDC) over the full-load line.

    Uses one SOI map (by temperature index) and one duration map. Returns a
    list of (rpm, iq, eoi) for the highest IQ column per rpm row.
    """
    bank = f.active_bank if bank is None else bank
    soi = f.find("soi", bank)
    dur = f.find("duration", bank)
    if not soi or not dur:
        return None
    s = soi[min(soi_index, len(soi) - 1)]
    d = dur[min(dur_index, len(dur) - 1)]
    srpm, siq, sval = s.x.values(f.buf), s.y.values(f.buf), s.values(f.buf)
    diq, drpm, dval = d.x.values(f.buf), d.y.values(f.buf), d.values(f.buf)
    out = []
    for i, rpm in enumerate(srpm):
        iq = float(siq[-1])
        soi_deg = float(sval[i, -1])
        dur_deg = bilinear(diq, drpm, dval, iq, rpm)
        out.append((float(rpm), iq, soi_deg - dur_deg))
    return out


def bilinear(xs, ys, z, x, y) -> float:
    xs = np.asarray(xs, float)
    ys = np.asarray(ys, float)
    if xs[0] > xs[-1]:
        xs = xs[::-1]
        z = z[::-1, :]
    if ys[0] > ys[-1]:
        ys = ys[::-1]
        z = z[:, ::-1]
    col = np.array([np.interp(y, ys, z[i]) for i in range(len(xs))])
    return float(np.interp(x, xs, col))
