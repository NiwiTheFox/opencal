"""Map discovery and identification for Bosch EDC15P/V calibration data.

EDC15 stores every table with self-describing axes. An axis is a header of
two little-endian words, ``id`` and ``count``, followed by ``count`` 16-bit
breakpoints. The id is the RAM address of the input variable, so it differs
between software versions.

* 2D curve: one axis, then ``count`` values.
* 3D map:   axis A, axis B, then ``A*B`` values, B varying fastest. The
  first axis (A) is the row axis, the second (B) the column axis.
* Map groups: several axes in a row, then N maps of one shape followed by a
  selector table (``id``, ``n``, n breakpoints, n indexes ``0x0i00``). Used
  for SOI per temperature, multiple smoke limiters and similar sets.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

AXIS_FAMILIES = {0xDB, 0xC0, 0xC1, 0xC2, 0xC4, 0xC5, 0xE0, 0xE4, 0xE5, 0xE9,
                 0xEA, 0xEB, 0xEC, 0xDA, 0xDD, 0xDE, 0xF9, 0xFE, 0xE8}


def is_axis_id(v: int) -> bool:
    return (v >> 8) in AXIS_FAMILIES


def valid_len(n: int, axis_id: int) -> bool:
    if ((axis_id >> 8) & 0xF0) == 0xE0:
        return 0 < n <= 32
    return 0 < n < 32


def u16(buf, a: int) -> int:
    return buf[a] | (buf[a + 1] << 8)


@dataclass
class Axis:
    id: int
    address: int          # address of the first breakpoint
    count: int
    factor: float = 1.0
    offset: float = 0.0
    name: str = ""
    unit: str = ""
    signed: bool = False

    @property
    def header(self) -> int:
        return self.address - 4

    def raw(self, buf) -> np.ndarray:
        r = np.frombuffer(bytes(buf[self.address:self.address + 2 * self.count]), "<u2").astype(np.int64)
        if self.signed:
            r = np.where(r >= 0x8000, r - 0x10000, r)
        return r

    def values(self, buf) -> np.ndarray:
        return self.raw(buf) * self.factor + self.offset

    def to_raw(self, values) -> np.ndarray:
        raw = np.rint((np.asarray(values, float) - self.offset) / self.factor).astype(np.int64)
        return np.clip(raw, -0x8000 if self.signed else 0, 0x7FFF if self.signed else 0xFFFF)

    def write_values(self, buf, values) -> None:
        raw = self.to_raw(values)
        buf[self.address:self.address + 2 * self.count] = (raw & 0xFFFF).astype("<u2").tobytes()


@dataclass
class Map:
    address: int                       # address of the first data word
    x: Axis                            # row axis (first header)
    y: Axis | None = None              # column axis (second header); None = curve
    name: str = ""
    category: str = "Unidentified"
    description: str = ""
    factor: float = 1.0
    offset: float = 0.0
    unit: str = ""
    signed: bool = False
    bank: int = 0                      # 64 KB page the data lives in
    codeblock: int | None = None
    group: int | None = None           # header address of a map group
    group_index: int | None = None
    identified: bool = False
    kind: str = ""                     # stable identity key, e.g. "smoke"
    tags: set = field(default_factory=set)

    # A curve is shown as a single row along its axis.
    @property
    def rows(self) -> int:
        return self.x.count if self.y is not None else 1

    @property
    def cols(self) -> int:
        return self.y.count if self.y is not None else self.x.count

    @property
    def row_axis(self) -> Axis | None:
        return self.x if self.y is not None else None

    @property
    def col_axis(self) -> Axis:
        return self.y if self.y is not None else self.x

    @property
    def size(self) -> int:
        return 2 * self.rows * self.cols

    @property
    def end(self) -> int:
        return self.address + self.size

    @property
    def is3d(self) -> bool:
        return self.y is not None

    @property
    def key(self) -> str:
        return f"{self.address:05X}"

    def raw(self, buf) -> np.ndarray:
        a = np.frombuffer(bytes(buf[self.address:self.end]), "<u2").astype(np.int64)
        if self.signed:
            a = np.where(a >= 0x8000, a - 0x10000, a)
        return a.reshape(self.rows, self.cols)

    def values(self, buf) -> np.ndarray:
        return self.raw(buf) * self.factor + self.offset

    def to_raw(self, values) -> np.ndarray:
        raw = np.rint((np.asarray(values, float) - self.offset) / self.factor).astype(np.int64)
        lo, hi = (-0x8000, 0x7FFF) if self.signed else (0, 0xFFFF)
        return np.clip(raw, lo, hi)

    def write_values(self, buf, values) -> None:
        self.write_raw(buf, self.to_raw(values))

    def write_raw(self, buf, raw) -> None:
        raw = np.asarray(raw, np.int64).reshape(self.rows, self.cols)
        buf[self.address:self.end] = (raw & 0xFFFF).astype("<u2").tobytes()

    def label(self) -> str:
        return self.name or f"{'3D' if self.is3d else '2D'} {self.key} ({self.rows}x{self.cols})"

    def same_shape(self, other: "Map") -> bool:
        return (self.rows, self.cols) == (other.rows, other.cols)


# ------------------------------------------------------------- scanning ----

def _axis_at(buf, t: int, maxlen: int = 32) -> Axis | None:
    if t < 0 or t + 4 > len(buf):
        return None
    aid = u16(buf, t)
    if not is_axis_id(aid):
        return None
    n = u16(buf, t + 2)
    if not valid_len(n, aid) or n > maxlen or t + 4 + 2 * n > len(buf):
        return None
    return Axis(aid, t + 4, n, signed=(aid >> 8) == 0xC1)


def _monotonic(buf, ax: Axis) -> bool:
    r = ax.raw(buf)
    if len(r) < 2:
        return True
    d = np.diff(r)
    return bool(np.all(d >= 0) or np.all(d <= 0))


def _selector_at(buf, t: int) -> int:
    """Return the entry count of a selector table at ``t`` or 0."""
    ax = _axis_at(buf, t, 10)
    if not ax:
        return 0
    idx = ax.address + 2 * ax.count
    if idx + 2 * ax.count > len(buf):
        return 0
    prev = -1
    for i in range(ax.count):
        lo, hi = buf[idx + 2 * i], buf[idx + 2 * i + 1]
        if lo not in (0, 0x40) or hi > 9:
            return 0
        v = (lo << 8) | hi
        if v < prev:
            return 0
        prev = v
    return ax.count


def _chain(buf, t: int) -> list[Axis]:
    out = []
    while True:
        ax = _axis_at(buf, t)
        if not ax or not _monotonic(buf, ax):
            return out
        out.append(ax)
        t = ax.address + 2 * ax.count


def _parse_group(buf, axes: list[Axis], found: dict) -> int:
    """Parse a map group that follows a run of 4+ axes. Returns end address."""
    pos = axes[-1].address + 2 * axes[-1].count
    pairs = [(axes[i], axes[i + 1]) for i in range(0, len(axes) - 1, 2)]
    header = axes[0].header
    gidx = 0
    budget = 0x1410
    t = pos
    while budget > 0 and t < len(buf) - 8:
        n = _selector_at(buf, t)
        if n:
            words = (t - pos) // 2
            shape = None
            if words > 0 and words % n == 0:
                per = words // n
                for a, b in pairs:
                    if a.count * b.count == per:
                        shape = (a, b)
                        break
            if shape is None:
                break
            a, b = shape
            for i in range(n):
                addr = pos + i * per * 2
                m = Map(addr, Axis(a.id, a.address, a.count, signed=a.signed),
                        Axis(b.id, b.address, b.count, signed=b.signed),
                        group=header, group_index=gidx)
                found.setdefault(addr, m)
                gidx += 1
            pos = t + 4 + 4 * n
            t = pos
            budget = 0x1410
            continue
        t += 2
        budget -= 2
    return pos


def scan(buf, start: int = 0x40000, end: int | None = None) -> list[Map]:
    """Find every axis-described table between ``start`` and ``end``."""
    end = (len(buf) - 0x10) if end is None else min(end, len(buf) - 0x10)
    found: dict[int, Map] = {}
    t = start
    while t < end:
        axes = _chain(buf, t)
        if not axes:
            t += 2
            continue
        if len(axes) >= 4:
            stop = _parse_group(buf, axes, found)
            if stop > axes[-1].address:
                t = max(stop, t + 2)
                continue
        if len(axes) >= 2:
            x, y = axes[0], axes[1]
            data = y.address + 2 * y.count
            if len(axes) == 3:
                # A third header before the data: one-axis selector, skip it.
                z = axes[2]
                data += max(16, 4 + 2 * z.count) if z.count > 1 else 0
                data = z.address + 2 * z.count if z.count <= 1 else data
            m = Map(data, x, y)
            if m.size < 1600 and m.end <= len(buf):
                found.setdefault(m.address, m)
                t = m.end
                continue
        x = axes[0]
        m = Map(x.address + 2 * x.count, x)
        if m.end <= len(buf):
            found.setdefault(m.address, m)
            t = m.end
            continue
        t += 2
    return sorted(found.values(), key=lambda m: m.address)


# ------------------------------------------------------------ identities ---

@dataclass
class Rule:
    kind: str
    name: str
    category: str
    shape: tuple | None = None          # (rows, cols); None = any
    rows: tuple = (1, 32)
    cols: tuple = (1, 32)
    factor: float = 1.0
    offset: float = 0.0
    unit: str = ""
    xaxis: tuple = ("", "", 1.0, 0.0)    # name, unit, factor, offset (rows)
    yaxis: tuple = ("", "", 1.0, 0.0)    # columns
    test: object = None
    numbered: bool = False
    description: str = ""


RPM = ("Engine speed", "rpm", 1.0, 0.0)
IQ = ("Injection quantity", "mg/st", 0.01, 0.0)
AIR = ("Airflow", "mg/st", 0.1, 0.0)
PEDAL = ("Pedal", "%", 0.01, 0.0)
ATM = ("Atmospheric pressure", "mbar", 1.0, 0.0)
BOOST = ("Boost pressure", "mbar", 1.0, 0.0)
TEMPK = ("Temperature", "°C", 0.1, -273.1)
SPEED = ("Vehicle speed", "km/h", 0.15625, 0.0)


def _rng(buf, ax) -> tuple[int, int]:
    r = ax.raw(buf)
    return int(r.min()), int(r.max())


def _drange(buf, m) -> tuple[int, int]:
    r = m.raw(buf)
    return int(r.min()), int(r.max())


def is_rpm(buf, ax) -> bool:
    lo, hi = _rng(buf, ax)
    return ax.count >= 5 and lo <= 1500 and 3500 <= hi <= 7000


def is_pedal(buf, ax) -> bool:
    lo, hi = _rng(buf, ax)
    return lo <= 200 and 9000 <= hi <= 10000


def is_air(buf, ax) -> bool:
    lo, hi = _rng(buf, ax)
    return 1500 <= lo and 7000 <= hi <= 16000 and not is_pedal(buf, ax)


def is_atm(buf, ax) -> bool:
    lo, hi = _rng(buf, ax)
    return ax.count <= 10 and 550 <= lo and hi <= 1200


def is_boost(buf, ax) -> bool:
    lo, hi = _rng(buf, ax)
    return 400 <= lo <= 1300 and 1500 <= hi <= 3500


def is_tempk(buf, ax) -> bool:
    lo, hi = _rng(buf, ax)
    return 2000 <= lo and hi <= 4600 and hi - lo >= 300


def _t(fn):
    def wrap(buf, m):
        try:
            return bool(fn(buf, m))
        except Exception:
            return False
    return wrap


RULES: list[Rule] = [
    Rule("soi", "Start of injection", "Injection", rows=(10, 20), cols=(8, 16), factor=-0.023437,
         offset=78, unit="°BTDC", xaxis=RPM, yaxis=IQ, numbered=True,
         test=_t(lambda b, m: m.group is not None and m.rows * m.cols in (224, 208, 192, 160)
                 and is_rpm(b, m.x) and 1500 <= _drange(b, m)[1] <= 4500)),
    Rule("smoke", "Smoke limiter", "Limiters", rows=(10, 20), cols=(8, 20), factor=0.01, unit="mg/st",
         xaxis=RPM, yaxis=AIR,
         test=_t(lambda b, m: is_rpm(b, m.x) and is_air(b, m.y) and 300 <= _drange(b, m)[1] <= 12000),
         description="Most fuel the ECU allows for the measured airflow. Sets smoke."),
    Rule("driver_wish", "Driver wish", "Torque", rows=(8, 20), cols=(6, 16), factor=0.01, unit="mg/st",
         xaxis=RPM, yaxis=PEDAL,
         test=_t(lambda b, m: is_rpm(b, m.x) and is_pedal(b, m.y) and _drange(b, m)[1] <= 9000),
         description="Fuel requested from pedal position and rpm."),
    Rule("inverse_driver_wish", "Inverse driver wish", "Torque", rows=(8, 20), cols=(8, 20),
         factor=0.01, unit="%", xaxis=RPM, yaxis=IQ,
         test=_t(lambda b, m: is_rpm(b, m.x) and _drange(b, m)[1] == 10000 and _drange(b, m)[0] == 0
                 and not is_pedal(b, m.y)),
         description="Pedal position from fuel quantity. Keep in step with driver wish."),
    Rule("torque_limiter", "Torque limiter", "Limiters", rows=(2, 4), cols=(15, 32), factor=0.01,
         unit="mg/st", xaxis=ATM, yaxis=RPM,
         test=_t(lambda b, m: is_atm(b, m.x) and is_rpm(b, m.y)),
         description="Most fuel per rpm and altitude. Sets the torque curve."),
    Rule("iq_by_map", "IQ by MAP limiter", "Limiters", rows=(8, 20), cols=(5, 16), factor=0.01,
         unit="mg/st", xaxis=RPM, yaxis=BOOST,
         test=_t(lambda b, m: is_rpm(b, m.x) and is_boost(b, m.y) and _drange(b, m)[1] <= 9000)),
    Rule("boost_limit", "Boost limit map", "Boost", rows=(4, 12), cols=(6, 16), unit="mbar",
         xaxis=ATM, yaxis=RPM,
         test=_t(lambda b, m: is_atm(b, m.x) and is_rpm(b, m.y) and 900 <= _drange(b, m)[1] <= 3500
                 and _drange(b, m)[0] >= 500)),
    Rule("boost_target", "Boost target map", "Boost", rows=(10, 20), cols=(8, 16), unit="mbar",
         xaxis=RPM, yaxis=IQ,
         test=_t(lambda b, m: is_rpm(b, m.x) and (m.y.id >> 8) in (0xC0, 0xEA, 0xEC)
                 and 1200 <= _drange(b, m)[1] <= 3200 and m.rows * m.cols in (160, 140, 130, 120))),
    Rule("egr", "EGR (airflow target)", "EGR", rows=(8, 20), cols=(8, 20), factor=0.1, unit="mg/st",
         xaxis=RPM, yaxis=IQ, numbered=True,
         test=_t(lambda b, m: is_rpm(b, m.x) and m.rows * m.cols >= 100 and (m.y.id >> 8) in (0xE9, 0xC0)
                 and 3000 <= _drange(b, m)[1] <= 9000 and _drange(b, m)[0] >= 1000)),
    Rule("n75", "N75 duty cycle", "Boost", rows=(10, 20), cols=(8, 16), factor=-0.01, offset=100,
         unit="%", xaxis=RPM, yaxis=IQ,
         test=_t(lambda b, m: is_rpm(b, m.x) and (m.y.id >> 8) in (0xEA, 0xE9) and _drange(b, m)[1] <= 10000
                 and _drange(b, m)[1] >= 3000 and _drange(b, m)[0] < 1000)),
    Rule("duration", "Injection duration", "Injection", rows=(8, 20), cols=(8, 20), factor=0.023437,
         unit="°CA", xaxis=IQ, yaxis=RPM, numbered=True,
         test=_t(lambda b, m: (m.x.id >> 8) in (0xC4, 0xC5) and is_rpm(b, m.y))),
    Rule("launch", "Launch control map", "Limiters", shape=(25, 14), factor=0.01, unit="mg/st",
         xaxis=RPM, yaxis=SPEED),
    Rule("soi_limit", "SOI limiter (temperature)", "Injection", rows=(10, 18), cols=(8, 14),
         factor=-0.023437, offset=78, unit="°BTDC", xaxis=RPM, yaxis=TEMPK,
         test=_t(lambda b, m: is_rpm(b, m.x) and is_tempk(b, m.y) and m.group is None
                 and 1500 <= _drange(b, m)[1] <= 4500)),
    Rule("boost_temp", "Boost correction by temperature", "Boost", rows=(8, 20), cols=(6, 14),
         unit="mbar", xaxis=BOOST, yaxis=TEMPK,
         test=_t(lambda b, m: (m.x.id >> 8) == 0xDA and is_tempk(b, m.y))),
    Rule("maf_lin", "MAF linearization", "Air", shape=(1, 32), unit="",
         test=_t(lambda b, m: not m.is3d)),
    Rule("map_lin", "MAP linearization", "Boost", shape=(1, 2), unit="mbar",
         test=_t(lambda b, m: not m.is3d and m.x.id in (0xEBA2, 0xEBA4, 0xE9BC))),
    Rule("start_iq", "Start IQ", "Misc", rows=(6, 12), cols=(6, 12), factor=0.01, unit="mg/st",
         xaxis=RPM, yaxis=TEMPK, numbered=True,
         test=_t(lambda b, m: is_rpm(b, m.x) and (m.y.id >> 8) == 0xC1 and _drange(b, m)[1] <= 9000)),
]


def _shape_ok(r: Rule, m: Map) -> bool:
    if r.shape and (m.rows, m.cols) != r.shape:
        return False
    if not (r.rows[0] <= m.rows <= r.rows[1] and r.cols[0] <= m.cols <= r.cols[1]):
        return False
    return True


def apply_rule(r: Rule, m: Map, name: str) -> None:
    m.kind = r.kind
    m.name = name
    m.category = r.category
    m.description = r.description
    m.factor, m.offset, m.unit = r.factor, r.offset, r.unit
    for ax, spec in ((m.x, r.xaxis), (m.y, r.yaxis)):
        if ax is None or not spec[0]:
            continue
        ax.name, ax.unit, ax.factor, ax.offset = spec
        if spec[1] == "°C":
            ax.signed = False
    m.identified = True


def _default_axis_labels(buf, m: Map) -> None:
    for ax in (m.x, m.y):
        if ax is None or ax.name:
            continue
        if is_rpm(buf, ax):
            ax.name, ax.unit = "Engine speed", "rpm"
        elif is_pedal(buf, ax):
            ax.name, ax.unit, ax.factor = "Pedal", "%", 0.01
        elif is_tempk(buf, ax):
            ax.name, ax.unit, ax.factor, ax.offset = "Temperature", "°C", 0.1, -273.1
        elif is_atm(buf, ax):
            ax.name, ax.unit = "Pressure", "mbar"


def bank_of(addr: int) -> int:
    """Calibration bank base for an address.

    An EDC15P codeblock spans base-0x4000 .. base+0xC000: its limiter page
    sits in the last 16 KB of the previous 64 KB page.
    """
    return (addr + 0x4000) & ~0xFFFF


def identify(buf, maps: list[Map], banks: dict[int, int | None] | None = None) -> None:
    """Name maps that match a known rule and attach scaling and units."""
    banks = banks or {}
    counters: dict[tuple, int] = {}
    for m in maps:
        m.bank = bank_of(m.address)
        m.codeblock = banks.get(m.bank)
        for r in RULES:
            if not _shape_ok(r, m):
                continue
            if r.test is not None and not r.test(buf, m):
                continue
            key = (r.kind, m.bank)
            n = counters.get(key, 0)
            counters[key] = n + 1
            if r.numbered:
                name = f"{r.name} {n:02d}"
            else:
                name = r.name if n == 0 else f"{r.name} {n + 1}"
            apply_rule(r, m, name)
            break
        if not m.identified and m.is3d and m.rows * m.cols >= 16:
            d = m.raw(buf)
            if d.min() != d.max():
                m.category = "Detected maps"
        _default_axis_labels(buf, m)


def find(maps: list[Map], kind: str) -> list[Map]:
    return [m for m in maps if m.kind == kind]
