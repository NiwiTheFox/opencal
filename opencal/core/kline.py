"""K-line diagnostics (ISO 14230 / KWP2000) for EDC15 over a KKL / FTDI cable.

Covers what is safe to do over OBD: identification, fault codes and live
measuring blocks for datalogging. Flash programming is deliberately not here.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

TESTER = 0xF1
ECU = 0x01


class KLineError(Exception):
    pass


def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def frame(payload: bytes, target: int = ECU, source: int = TESTER) -> bytes:
    if not 0 < len(payload) <= 63:
        raise KLineError("payload length 1..63")
    body = bytes([0x80 | len(payload), target, source]) + payload
    return body + bytes([checksum(body)])


def parse_frame(raw: bytes) -> tuple[int, int, bytes]:
    if len(raw) < 4:
        raise KLineError("short frame")
    fmt = raw[0]
    n = fmt & 0x3F
    if fmt & 0xC0 != 0x80 or n == 0:
        raise KLineError(f"unsupported header 0x{fmt:02X}")
    if len(raw) != 3 + n + 1:
        raise KLineError("length mismatch")
    if checksum(raw[:-1]) != raw[-1]:
        raise KLineError("checksum mismatch")
    return raw[1], raw[2], raw[3:3 + n]


# ------------------------------------------------------------- transports --

class SerialTransport:
    """KKL cable through pyserial. The adapter echoes every sent byte."""

    def __init__(self, port: str, baud: int = 10400, timeout: float = 0.5):
        import serial  # pyserial
        self.ser = serial.Serial(port, baud, timeout=timeout)
        self.echo = True

    def fast_init(self) -> None:
        self.ser.reset_input_buffer()
        time.sleep(0.3)  # W5: bus idle
        self.ser.break_condition = True
        time.sleep(0.025)
        self.ser.break_condition = False
        time.sleep(0.025)

    def send(self, data: bytes) -> None:
        for b in data:  # P4 inter-byte time
            self.ser.write(bytes([b]))
            time.sleep(0.0015)
        if self.echo:
            got = self.ser.read(len(data))
            if got != data:
                raise KLineError("no echo from the cable (K-line not connected?)")

    def recv(self, timeout: float = 1.0) -> bytes:
        self.ser.timeout = timeout
        hdr = self.ser.read(1)
        if not hdr:
            raise KLineError("ECU: no answer")
        n = hdr[0] & 0x3F
        rest = self.ser.read(2 + n + 1)
        if len(rest) != 3 + n:
            raise KLineError("ECU: incomplete answer")
        return hdr + rest

    def close(self) -> None:
        self.ser.close()


class SimulatedEcu:
    """An in-memory EDC15 that answers the services this module uses."""

    def __init__(self):
        self.dtcs = [(0x4552, 0x24), (0x0201, 0x60)]  # (code, status)
        self.t0 = time.time()
        self.rx: list[bytes] = []
        self.started = False

    def fast_init(self):
        pass

    def send(self, data: bytes):
        tgt, src, p = parse_frame(data)
        self.rx.append(self._answer(p))

    def recv(self, timeout: float = 1.0) -> bytes:
        if not self.rx:
            raise KLineError("ECU: no answer")
        return self.rx.pop(0)

    def close(self):
        pass

    def _ok(self, payload: bytes) -> bytes:
        return frame(payload, TESTER, ECU)

    def _answer(self, p: bytes) -> bytes:
        sid = p[0]
        if sid == 0x81:
            self.started = True
            return self._ok(bytes([0xC1, 0xEF, 0x8F]))
        if not self.started:
            return self._ok(bytes([0x7F, sid, 0x22]))
        if sid == 0x10:
            return self._ok(bytes([0x50, p[1]]))
        if sid == 0x1A:
            return self._ok(bytes([0x5A, p[1]]) + b"038906019FJ 1,9l R4 EDC  SG  1376 ")
        if sid == 0x18:
            body = bytes([0x58, len(self.dtcs)])
            for code, st in self.dtcs:
                body += bytes([code >> 8, code & 0xFF, st])
            return self._ok(body)
        if sid == 0x14:
            self.dtcs = []
            return self._ok(bytes([0x54, 0xFF, 0x00]))
        if sid == 0x21:
            t = time.time() - self.t0
            rpm = 900 + int(1500 * (1 + __import__("math").sin(t / 3)))
            return self._ok(bytes([0x61, p[1]]) + _block(p[1], rpm))
        if sid == 0x3E:
            return self._ok(bytes([0x7E]))
        if sid == 0x82:
            self.started = False
            return self._ok(bytes([0xC2]))
        return self._ok(bytes([0x7F, sid, 0x11]))


def _block(group: int, rpm: int) -> bytes:
    """Fake VAG measuring block: 4 triplets (type, a, b)."""
    iq = 5 + (rpm - 900) / 3000 * 40
    boost = 1000 + (rpm - 900) / 3000 * 1300
    trip = [(0x01, 250, round(rpm / 0.2 / 250)),            # rpm
            (0x31, 50, round(iq * 10 / 50 * 4)),            # mg/st
            (0x12, 250, round(boost / 0.04 / 250)),         # mbar
            (0x05, 10, round(85 * 10 / 10 + 100))]          # °C
    return b"".join(bytes(t) for t in trip)


# ----------------------------------------------------------- measuring --

@dataclass
class Value:
    value: float
    unit: str
    raw: tuple


def decode_triplet(t: int, a: int, b: int) -> Value:
    f = {
        0x01: (lambda: 0.2 * a * b, "rpm"),
        0x02: (lambda: a * 0.002 * b, "%"),
        0x05: (lambda: a * (b - 100) * 0.1, "°C"),
        0x06: (lambda: 0.001 * a * b, "V"),
        0x07: (lambda: 0.01 * a * b, "km/h"),
        0x08: (lambda: 0.1 * a * b, ""),
        0x0F: (lambda: 0.01 * a * b, "ms"),
        0x12: (lambda: 0.04 * a * b, "mbar"),
        0x16: (lambda: 0.001 * a * b, "ms"),
        0x17: (lambda: b / 256 * a, "%"),
        0x21: (lambda: (100 * b / a) if a else 0.0, "%"),
        0x22: (lambda: (b - 128) * 0.01 * a, "kW"),
        0x31: (lambda: (b / 4) * a * 0.1, "mg/st"),
        0x33: (lambda: ((b - 128) / 255) * a, "mg/st"),
        0x10: (lambda: float(b), "bin"),
    }.get(t)
    if f is None:
        return Value(float(a * 256 + b), "", (t, a, b))
    return Value(round(f[0](), 3), f[1], (t, a, b))


@dataclass
class Session:
    transport: object
    log: list = field(default_factory=list)

    def request(self, payload: bytes, timeout: float = 1.0) -> bytes:
        self.transport.send(frame(payload))
        for _ in range(8):
            raw = self.transport.recv(timeout)
            _, _, p = parse_frame(raw)
            self.log.append((payload.hex(), p.hex()))
            if p[0] == 0x7F and len(p) >= 3 and p[2] == 0x78:   # response pending
                continue
            if p[0] == 0x7F:
                raise KLineError(f"ECU refused service 0x{payload[0]:02X} (NRC 0x{p[2]:02X})")
            if p[0] != (payload[0] | 0x40):
                raise KLineError(f"unexpected answer 0x{p[0]:02X}")
            return p
        raise KLineError("ECU kept answering 'pending'")

    def connect(self) -> None:
        self.transport.fast_init()
        try:
            self.request(bytes([0x81]))
        except KLineError as e:
            raise KLineError(f"ECU: no answer to fast init (ignition on? K-line connected?) [{e}]")
        self.request(bytes([0x10, 0x89]))

    def identify(self) -> str:
        p = self.request(bytes([0x1A, 0x9B]))
        return p[2:].decode("ascii", "replace").strip()

    def read_dtcs(self) -> list[tuple[str, int]]:
        p = self.request(bytes([0x18, 0x02, 0xFF, 0x00]))
        n = p[1]
        out = []
        for i in range(n):
            hi, lo, st = p[2 + 3 * i:5 + 3 * i]
            out.append((f"{(hi << 8) | lo:05d}", st))
        return out

    def clear_dtcs(self) -> None:
        self.request(bytes([0x14, 0xFF, 0x00]))

    def read_group(self, group: int) -> list[Value]:
        p = self.request(bytes([0x21, group]))
        data = p[2:]
        return [decode_triplet(*data[i:i + 3]) for i in range(0, len(data) - 2, 3)]

    def keepalive(self) -> None:
        self.request(bytes([0x3E]))

    def close(self) -> None:
        try:
            self.request(bytes([0x82]))
        except KLineError:
            pass
        self.transport.close()


def list_ports() -> list[str]:
    try:
        from serial.tools import list_ports as lp
        return [p.device for p in lp.comports()]
    except Exception:
        return []
