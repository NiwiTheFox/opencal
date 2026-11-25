"""Time-domain simulation of an engine start and a full-load pull from the maps.

Not a physics-grade engine model: a transparent loop that runs the
calibration's own fuel, boost and limiter tables step by step, so you can see
which map limits fuel where, whether boost overshoots into limp mode, where
the engine would smoke and how the car accelerates.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import calcs
from . import patterns as P
from .tuning import bilinear

DT = 0.02


@dataclass
class Car:
    mass_kg: float = 1350.0
    gear_ratio: float = 1.39          # 3rd gear (02J box)
    final_drive: float = 3.389
    tyre_radius_m: float = 0.316      # 205/55 R16
    drag_area: float = 0.68           # Cd*A, m²
    rolling: float = 0.012
    driveline_eff: float = 0.88
    inertia_kg: float = 120.0         # rotating mass equivalent


@dataclass
class SimParams:
    coolant_c: float = 85.0
    start_rpm: float = 1250.0
    end_rpm: float = 4500.0
    spool_tau_s: float = 0.9          # turbo time constant at 2000 rpm
    overshoot: float = 0.06           # boost controller overshoot fraction
    engine: calcs.EngineSpec = field(default_factory=calcs.EngineSpec)
    car: Car = field(default_factory=Car)


@dataclass
class Sample:
    t: float
    phase: str
    rpm: float
    speed_kmh: float
    pedal: float
    iq: float
    limiter: str
    boost: float
    boost_target: float
    air: float
    lam: float
    torque: float
    power: float
    soi: float | None
    eoi: float | None
    n75: float | None


@dataclass
class Event:
    t: float
    level: str
    text: str


@dataclass
class SimResult:
    samples: list[Sample] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    started: bool = False
    start_time: float | None = None
    pull_time: float | None = None      # seconds start_rpm -> end_rpm
    peak_power: Sample | None = None
    peak_torque: Sample | None = None

    def series(self, name: str, phase: str | None = None) -> np.ndarray:
        return np.array([getattr(s, name) for s in self.samples if phase is None or s.phase == phase], float)


class _Tables:
    """Lookups into the active bank's maps, each optional."""

    def __init__(self, f, bank):
        self.f = f
        b = f.buf
        self.dw = f.first("driver_wish", bank)
        self.sm = f.first("smoke", bank)
        self.tl = f.first("torque_limiter", bank)
        self.iqm = f.first("iq_by_map", bank)
        self.bt = f.first("boost_target", bank)
        self.bl = f.first("boost_limit", bank)
        self.n75 = f.first("n75", bank)
        self.siq = f.first("start_iq", bank)
        soi = f.find("soi", bank)
        self.soi = soi[min(len(soi) - 1, max(0, len(soi) // 2 + 1))] if soi else None
        dur = f.find("duration", bank)
        self.dur = dur[min(1, len(dur) - 1)] if dur else None
        sv = next((s for s in P.find_scalars(b) if s.kind == "svbl"), None)
        self.svbl = sv.value(b) if sv else None
        self.b = b

    def look(self, m, x, y):
        if m is None:
            return None
        if not m.is3d:
            return float(np.interp(y, m.x.values(self.b), m.values(self.b)[0]))
        return bilinear(m.x.values(self.b), m.y.values(self.b), m.values(self.b), x, y)

    def limits(self, rpm, pedal, air, boost, atm):
        lim = {}
        v = self.look(self.dw, rpm, pedal)
        if v is not None:
            lim["driver wish"] = v
        v = self.look(self.sm, rpm, air)
        if v is not None:
            lim["smoke limiter"] = v
        if self.tl is not None:
            lim["torque limiter"] = bilinear(self.tl.x.values(self.b), self.tl.y.values(self.b),
                                             self.tl.values(self.b), atm, rpm)
        v = self.look(self.iqm, rpm, boost)
        if v is not None:
            lim["IQ by MAP"] = v
        return lim


def simulate(f, bank: int | None = None, p: SimParams | None = None) -> SimResult:
    p = p or SimParams()
    e, car = p.engine, p.car
    bank = f.active_bank if bank is None else bank
    tb = _Tables(f, bank)
    r = SimResult()
    atm = e.ambient_mbar
    t = 0.0
    rpm = 0.0
    boost = atm
    limp = False
    smoke_flag = eoi_flag = False

    def record(phase, pedal, iq, limiter, target, speed):
        air = calcs.air_mg_per_stroke(boost, e)
        torque = brake_torque(iq, rpm, air, e) if iq > 0 else 0.0
        soi = tb.look(tb.soi, rpm, iq) if tb.soi is not None else None
        dur = tb.look(tb.dur, iq, rpm) if tb.dur is not None else None
        eoi = (soi - dur) if soi is not None and dur is not None else None
        n75 = tb.look(tb.n75, rpm, iq) if tb.n75 is not None else None
        s = Sample(round(t, 3), phase, rpm, speed, pedal, iq, limiter, boost, target, air,
                   calcs.lam(air, iq) if iq > 0 else float("inf"), torque, calcs.power_hp(torque, rpm), soi, eoi, n75)
        r.samples.append(s)
        return s

    # ---------------------------------------------------------- start ---
    temp_k = p.coolant_c
    crank_iq = None
    if tb.siq is not None:
        crank_iq = tb.look(tb.siq, 250, temp_k + 273.1 if tb.siq.y.unit != "°C" else temp_k)
    if crank_iq is None or crank_iq < 8:
        r.events.append(Event(0.0, "warning", "Start-fuel map not identified in this bank: using a typical 30 mg/st"))
        crank_iq = 30.0
    r.events.append(Event(0.0, "info", f"Cranking at {p.coolant_c:.0f} °C, start fuel {crank_iq:.1f} mg/st"))
    idle = 850.0
    while t < 4.0:
        if rpm < 180 and t < 1.0:
            rpm = min(rpm + 400 * DT / 0.2, 220)          # starter
            iq = crank_iq if rpm > 150 else 0.0
        elif rpm < idle - 50:
            iq = crank_iq if rpm < 500 else max(4.0, 12.0 - (rpm - 500) / 60)
            net = iq * e.nm_per_mg - _friction(rpm) - 6
            rpm = max(rpm + net / 0.25 * DT * 9.55 * 0.5, 150)
        else:
            iq = 4.0 + max(0.0, (idle - rpm) * 0.02)
            rpm += (idle - rpm) * 2.0 * DT
        if not r.started and rpm > 500:
            r.started, r.start_time = True, round(t, 2)
            r.events.append(Event(t, "ok", f"Engine started after {t:.2f} s"))
        record("start", 0.0, iq, "start fuel" if rpm < 500 else "idle", atm, 0.0)
        t += DT
    if not r.started:
        r.events.append(Event(t, "error", "Engine did not start: start fuel too low or missing."))
        return r

    # ----------------------------------------------------------- pull ---
    speed = p.start_rpm / 60 * 2 * math.pi * car.tyre_radius_m / (car.gear_ratio * car.final_drive)  # m/s
    rpm = p.start_rpm
    r.events.append(Event(t, "info", f"Pull from {p.start_rpm:.0f} rpm, gear ratio {car.gear_ratio}"))
    t_pull0 = t
    last_rpm = rpm
    stalled_for = 0.0
    while rpm < p.end_rpm and t - t_pull0 < 40:
        pedal = min((t - t_pull0) / 0.2, 1.0) * 100.0
        air = calcs.air_mg_per_stroke(boost, e)
        lim = tb.limits(rpm, pedal, air, boost, atm)
        if not lim:
            r.events.append(Event(t, "error", "No fuel maps identified in this bank."))
            break
        name, iq = min(lim.items(), key=lambda kv: kv[1])
        if limp:
            iq = min(iq, 0.6 * lim.get("driver wish", iq))
            name = "limp mode"
        target = tb.look(tb.bt, rpm, iq) if tb.bt is not None else atm
        if tb.bl is not None:
            blim = bilinear(tb.bl.x.values(tb.b), tb.bl.y.values(tb.b), tb.bl.values(tb.b), atm, rpm)
            target = min(target, blim)
        if limp:
            target = atm + 300
        tau = p.spool_tau_s * (2000.0 / max(rpm, 900)) ** 1.3
        over = target * (1 + p.overshoot) if boost < target else target
        boost += (over - boost) * DT / tau
        boost = max(min(boost, MAP_SENSOR_CEILING), atm)   # physical sensor/plumbing ceiling only
        if tb.svbl and boost > tb.svbl and not limp:
            limp = True
            r.events.append(Event(t, "error", f"Boost {boost:.0f} mbar above SVBL {tb.svbl:.0f} mbar → limp mode at {rpm:.0f} rpm"))
        s = record("pull", pedal, iq, name, target, speed * 3.6)
        if s.lam < 1.15 and not smoke_flag:
            smoke_flag = True
            r.events.append(Event(t, "warning", f"λ {s.lam:.2f} at {rpm:.0f} rpm: visible smoke ({name})"))
        if s.eoi is not None and s.eoi < -15 and not eoi_flag:
            eoi_flag = True
            r.events.append(Event(t, "warning", f"End of injection {abs(s.eoi):.0f}° ATDC at {rpm:.0f} rpm (hot exhaust)"))
        # vehicle
        wheel = s.torque * car.gear_ratio * car.final_drive * car.driveline_eff / car.tyre_radius_m
        resist = car.rolling * car.mass_kg * 9.81 + 0.5 * 1.2 * car.drag_area * speed ** 2
        acc = (wheel - resist) / (car.mass_kg + car.inertia_kg)
        speed = max(speed + acc * DT, 0.1)
        rpm = speed * car.gear_ratio * car.final_drive / (2 * math.pi * car.tyre_radius_m) * 60
        if rpm <= last_rpm + 0.01:
            stalled_for += DT
            if stalled_for > 1.0:
                lvl = "info" if rpm > 3800 else "error"
                r.events.append(Event(t, lvl, f"Stops pulling at {rpm:.0f} rpm: fuel cut by {name}"
                                              + (" (rpm limit)" if rpm > 3800 else "")))
                break
        else:
            stalled_for = 0.0
        last_rpm = rpm
        t += DT
    pull = [s for s in r.samples if s.phase == "pull"]
    if pull and pull[-1].rpm >= p.end_rpm - 25:
        r.pull_time = round(pull[-1].t - t_pull0, 2)
        r.events.append(Event(t, "ok", f"{p.start_rpm:.0f}→{p.end_rpm:.0f} rpm in {r.pull_time:.2f} s, "
                                       f"{pull[0].speed_kmh:.0f}→{pull[-1].speed_kmh:.0f} km/h"))
    if pull:
        r.peak_power = max(pull, key=lambda s: s.power)
        r.peak_torque = max(pull, key=lambda s: s.torque)
        r.events.append(Event(t, "ok", f"Peak ≈ {r.peak_power.power:.0f} hp @ {r.peak_power.rpm:.0f} rpm, "
                                       f"{r.peak_torque.torque:.0f} Nm @ {r.peak_torque.rpm:.0f} rpm (estimate)"))
        used = {}
        for s in pull:
            used[s.limiter] = used.get(s.limiter, 0) + 1
        share = ", ".join(f"{k} {v * 100 // len(pull)}%" for k, v in sorted(used.items(), key=lambda kv: -kv[1]))
        r.events.append(Event(t, "info", f"Fuel set by: {share}"))
    return r


MAP_SENSOR_CEILING = 2550.0        # mbar absolute: stock 2.5-bar sensor + a little


def _friction(rpm: float) -> float:
    """Friction + pumping torque (FMEP) of a 1.9 TDI, Nm. Grows with rpm."""
    return 11.0 + 0.0038 * rpm + 1.3e-6 * rpm * rpm


def _comb_eff(rpm: float) -> float:
    """How much of the fuel's torque the engine actually makes vs rpm.

    Near full it holds flat in the mid range, then falls off at the top as
    there is less time to burn and fill the cylinder (why a diesel's power
    peaks around 3800-4000 and then drops rather than climbing to redline).
    """
    corner = 2900.0
    if rpm <= corner:
        return 1.0
    # lose ~3% per 1000 rpm above the corner, floored
    return max(0.74, 1.0 - 0.00003 * (rpm - corner))


def brake_torque(iq: float, rpm: float, air: float, e: calcs.EngineSpec) -> float:
    """Brake torque (Nm) from injected quantity at this rpm.

    Indicated torque is proportional to the fuel actually burned, limited by
    the air available (a diesel cannot burn past roughly lambda 1), then the
    pumping/friction torque is subtracted. ``nm_per_mg`` calibrates the
    indicated side so a stock 1.9 TDI lands on its rated figures.
    """
    burnable = min(iq, air / calcs.STOICH)          # can't burn more than the air allows
    indicated = burnable * e.nm_per_mg * _comb_eff(rpm)
    return max(indicated - _friction(rpm), 0.0)
