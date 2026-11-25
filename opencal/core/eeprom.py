"""EDC15P/V 95040 EEPROM dump (512 bytes): immobiliser, VIN, SKC, mileage.

Offsets follow the freeware VAG EDC15P Suite. Each value is stored twice;
both copies are written.
"""
from __future__ import annotations

from dataclasses import dataclass

SIZE = 512
IMMO_ON = 0x73
IMMO_OFF = 0x60


class EepromError(Exception):
    pass


@dataclass
class Eeprom:
    data: bytearray
    path: str | None = None

    @classmethod
    def load(cls, path: str) -> "Eeprom":
        with open(path, "rb") as f:
            raw = f.read()
        return cls.from_bytes(raw, path)

    @classmethod
    def from_bytes(cls, raw: bytes, path: str | None = None) -> "Eeprom":
        if len(raw) < 0x200:
            raise EepromError("File is too small to be an EDC15 EEPROM dump.")
        return cls(bytearray(raw[:SIZE] if len(raw) >= SIZE else raw), path)

    # --------------------------------------------------------------- read --
    @property
    def immo_active(self) -> bool:
        return self.data[0x1B0] != IMMO_OFF

    @property
    def vin(self) -> str:
        return bytes(self.data[0x140:0x151]).decode("ascii", "replace")

    @property
    def immo_id(self) -> str:
        return bytes(self.data[0x131:0x13F]).decode("ascii", "replace")

    @property
    def skc(self) -> int:
        """Login / SKC code as stored (decimal, 4-5 digits)."""
        return self.data[0x160] | (self.data[0x161] << 8)

    @property
    def mileage_km(self) -> float:
        v = (self.data[0x1BF] | (self.data[0x1C0] << 8) | (self.data[0x1C1] << 16)
             | ((self.data[0x1C2] & 0x7F) << 24))
        return v / 100.0

    # -------------------------------------------------------------- write --
    def set_immo(self, active: bool) -> None:
        b = IMMO_ON if active else IMMO_OFF
        self.data[0x1B0] = b
        self.data[0x1DE] = b

    def set_vin(self, vin: str) -> None:
        if len(vin) != 17 or not vin.isascii():
            raise EepromError("A VIN has 17 characters.")
        raw = vin.upper().encode()
        self.data[0x140:0x151] = raw
        self.data[0x172:0x183] = raw

    def set_immo_id(self, immo: str) -> None:
        if len(immo) != 14 or not immo.isascii():
            raise EepromError("The immobiliser ID has 14 characters.")
        raw = immo.encode()
        self.data[0x131:0x13F] = raw
        self.data[0x163:0x171] = raw

    def set_skc(self, code: int) -> None:
        if not 0 <= code <= 0xFFFF:
            raise EepromError("Login code out of range.")
        self.data[0x160] = code & 0xFF
        self.data[0x161] = code >> 8

    def save(self, path: str | None = None) -> None:
        path = path or self.path
        if not path:
            raise EepromError("No file name")
        with open(path, "wb") as f:
            f.write(self.data)
        self.path = path
