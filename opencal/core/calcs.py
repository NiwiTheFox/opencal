"""Engineering calculators: air mass, AFR, torque/power estimate, turbo fit, dyno."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

R_AIR = 287.05  # J/(kg K)
STOICH = 14.5


@dataclass
class EngineSpec:
    displacement_l: float = 1.896
    cylinders: int = 4
    ve: float = 0.92                  # volumetric efficiency
    compressor_eff: float = 0.70
    intercooler_eff: float = 0.60
    ambient_c: float = 20.0
    ambient_mbar: float = 1013.0
    nm_per_mg: float = 6.2            # PD 1.9 TDI indicated: calibrated to rated figures


def charge_temp_c(boost_mbar_abs: float, e: EngineSpec) -> float:
    """Intake temperature after compressor + intercooler."""
    t1 = e.ambient_c + 273.15
    pr = max(boost_mbar_abs / e.ambient_mbar, 1.0)
    t2 = t1 + t1 * (pr ** 0.2857 - 1) / e.compressor_eff
    t3 = t2 - e.intercooler_eff * (t2 - t1)
    return t3 - 273.15


def air_mg_per_stroke(boost_mbar_abs: float, e: EngineSpec) -> float:
    t = charge_temp_c(boost_mbar_abs, e) + 273.15
    v_cyl = e.displacement_l / 1000 / e.cylinders
    kg = boost_mbar_abs * 100 * v_cyl * e.ve / (R_AIR * t)
    return kg * 1e6


def afr(air_mg: float, iq_mg: float) -> float:
    return air_mg / iq_mg if iq_mg > 0 else float("inf")


def lam(air_mg: float, iq_mg: float) -> float:
    return afr(air_mg, iq_mg) / STOICH


def iq_for_lambda(air_mg: float, target_lambda: float) -> float:
    return air_mg / (STOICH * target_lambda)


def boost_for_iq(iq_mg: float, target_lambda: float, e: EngineSpec, cap: float = 2450) -> float:
    """Boost (mbar abs) needed to burn ``iq_mg`` at ``target_lambda``."""
    need = iq_for_lambda(1, 1) * 0 + iq_mg * STOICH * target_lambda
    lo, hi = 800.0, 4000.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if air_mg_per_stroke(mid, e) < need:
            lo = mid
        else:
            hi = mid
    return min(hi, cap)


def torque_nm(iq_mg: float, e: EngineSpec) -> float:
    return iq_mg * e.nm_per_mg


def power_hp(torque: float, rpm: float) -> float:
    return torque * rpm / 7023.5  # metric hp


def eoi(soi_btdc: float, duration_ca: float) -> float:
    """End of injection in deg BTDC (negative = after TDC)."""
    return soi_btdc - duration_ca


# ------------------------------------------------------------- turbo fit --

@dataclass
class Compressor:
    name: str
    # (corrected mass flow kg/s, pressure ratio) along surge and choke lines
    surge: list = field(default_factory=list)
    choke: list = field(default_factory=list)
    max_pr: float = 2.6
    approximate: bool = True


TURBOS = {
    "GT1749V (VNT-15, 1.9 PD 100–130 hp)": Compressor(
        "GT1749V", surge=[(0.03, 1.3), (0.05, 1.8), (0.07, 2.3), (0.08, 2.5)],
        choke=[(0.10, 1.3), (0.13, 1.8), (0.145, 2.2), (0.15, 2.5)], max_pr=2.5),
    "GT1756V (VNT-17, 1.9 PD 150–160 hp)": Compressor(
        "GT1756V", surge=[(0.03, 1.3), (0.06, 1.9), (0.08, 2.4), (0.09, 2.7)],
        choke=[(0.12, 1.3), (0.15, 1.9), (0.17, 2.4), (0.175, 2.7)], max_pr=2.7),
    "GT2056V (hybrid-class)": Compressor(
        "GT2056V", surge=[(0.04, 1.3), (0.07, 1.9), (0.10, 2.5), (0.11, 2.8)],
        choke=[(0.15, 1.3), (0.19, 2.0), (0.21, 2.5), (0.22, 2.8)], max_pr=2.8),
}


def mass_flow_kg_s(rpm: float, boost_mbar_abs: float, e: EngineSpec) -> float:
    air = air_mg_per_stroke(boost_mbar_abs, e) / 1e6  # kg per cylinder per cycle
    return air * e.cylinders * rpm / 120.0


def in_envelope(c: Compressor, flow: float, pr: float, margin: float = 0.95) -> bool:
    s = np.array(c.surge)
    ch = np.array(c.choke)
    surge_flow = np.interp(pr, s[:, 1], s[:, 0])
    choke_flow = np.interp(pr, ch[:, 1], ch[:, 0]) * margin
    return surge_flow <= flow <= choke_flow and pr <= c.max_pr * margin


def fit_boost_curve(c: Compressor, rpms, target_mbar, e: EngineSpec, margin: float = 0.95):
    """Largest boost per rpm inside the compressor map, never above target."""
    out = []
    for rpm, tgt in zip(rpms, target_mbar):
        best = None
        for b in np.arange(tgt, e.ambient_mbar - 1, -10.0):
            pr = b / e.ambient_mbar
            if in_envelope(c, mass_flow_kg_s(rpm, b, e), pr, margin):
                best = float(b)
                break
        out.append(best)
    return out


# ------------------------------------------------------------------ dyno --

@dataclass
class DynoPoint:
    rpm: float
    iq: float
    boost: float
    limiter: str
    torque: float
    power: float
    lam: float


def virtual_dyno(f, bank=None, e: EngineSpec = EngineSpec(), rpms=None) -> list[DynoPoint]:
    """Full-load estimate from the calibration: the lowest fuel limit wins."""
    from .tuning import bilinear
    bank = f.active_bank if bank is None else bank
    rpms = list(rpms or range(1250, 5001, 250))
    dw = f.first("driver_wish", bank)
    sm = f.first("smoke", bank)
    tl = f.first("torque_limiter", bank)
    bt = f.first("boost_target", bank)
    out = []
    for rpm in rpms:
        limits = {}
        if dw is not None:
            limits["driver wish"] = float(np.interp(rpm, dw.x.values(f.buf), dw.values(f.buf)[:, -1]))
        if tl is not None:
            alt = tl.values(f.buf)
            row = int(np.argmin(np.abs(tl.x.values(f.buf) - e.ambient_mbar)))
            limits["torque limiter"] = float(np.interp(rpm, tl.y.values(f.buf), alt[row]))
        boost = e.ambient_mbar
        if bt is not None:
            boost = bilinear(bt.x.values(f.buf), bt.y.values(f.buf), bt.values(f.buf), rpm,
                             min(limits.values()) if limits else 40)
        air = air_mg_per_stroke(boost, e)
        if sm is not None:
            limits["smoke limiter"] = bilinear(sm.x.values(f.buf), sm.y.values(f.buf), sm.values(f.buf), rpm, air)
        if not limits:
            continue
        name, iq = min(limits.items(), key=lambda kv: kv[1])
        t = torque_nm(iq, e)
        out.append(DynoPoint(rpm, iq, boost, name, t, power_hp(t, rpm), lam(air, iq)))
    return out
