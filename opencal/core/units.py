"""Display units. Maps keep their native scaling; conversion happens at display.

Each family has a native unit (what the ECU tables use after scaling) and
choices. ``convert(value, native_unit)`` returns (shown_value, shown_unit).
"""
from __future__ import annotations

from dataclasses import dataclass

# family -> {unit: (to_native factor, offset)} with  native = shown * f + o
FAMILIES = {
    "pressure": {"native": "mbar", "choices": {"mbar": (1.0, 0.0), "bar": (1000.0, 0.0), "kPa": (10.0, 0.0),
                                                "psi": (68.9476, 0.0)}},
    "power": {"native": "hp", "choices": {"hp": (1.0, 0.0), "kW": (1 / 0.73549875, 0.0), "PS": (1.0, 0.0),
                                          "bhp": (1.0138696, 0.0)}},
    "torque": {"native": "Nm", "choices": {"Nm": (1.0, 0.0), "lb-ft": (1.3558179, 0.0), "kgm": (9.80665, 0.0)}},
    "temperature": {"native": "°C", "choices": {"°C": (1.0, 0.0), "°F": (5 / 9, -32 * 5 / 9), "K": (1.0, -273.15)}},
    "speed": {"native": "km/h", "choices": {"km/h": (1.0, 0.0), "mph": (1.609344, 0.0)}},
    "fuel": {"native": "mg/st", "choices": {"mg/st": (1.0, 0.0), "mm³/st": (0.832, 0.0)}},  # diesel ~0.832 mg/mm³
}

UNIT_FAMILY = {"mbar": "pressure", "hp": "power", "Nm": "torque", "°C": "temperature", "km/h": "speed",
               "mg/st": "fuel"}

_choice = {k: v["native"] for k, v in FAMILIES.items()}


def set_choice(family: str, unit: str) -> None:
    if unit in FAMILIES[family]["choices"]:
        _choice[family] = unit


def choice(family: str) -> str:
    return _choice[family]


@dataclass(frozen=True)
class Conv:
    native: str
    shown: str
    f: float
    o: float

    def to_shown(self, v):
        return (v - self.o) / self.f

    def to_native(self, v):
        return v * self.f + self.o

    @property
    def identity(self) -> bool:
        return self.f == 1.0 and self.o == 0.0


def conv(native_unit: str) -> Conv:
    fam = UNIT_FAMILY.get(native_unit)
    if fam is None:
        return Conv(native_unit, native_unit, 1.0, 0.0)
    shown = _choice[fam]
    f, o = FAMILIES[fam]["choices"][shown]
    return Conv(native_unit, shown, f, o)


def fmt(value: float, native_unit: str, decimals: int = 0) -> str:
    c = conv(native_unit)
    v = c.to_shown(value)
    if c.shown == "bar":
        decimals = max(decimals, 2)
    return f"{v:,.{decimals}f} {c.shown}"


def load(settings) -> None:
    for fam in FAMILIES:
        v = settings.value(f"units/{fam}")
        if v:
            set_choice(fam, str(v))


def save(settings) -> None:
    for fam in FAMILIES:
        settings.setValue(f"units/{fam}", _choice[fam])
