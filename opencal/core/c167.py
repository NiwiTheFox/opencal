"""C166/C167 instruction-set emulator for running ECU code in isolation.

Purpose: execute functions from an EDC15 flash image (and patches written for
it) with chosen inputs, and observe registers, RAM and which flash pages they
read. It models the CPU core faithfully enough for calibration logic:

* GPRs through the context pointer CP, byte registers RLx/RHx;
* SFR / ESFR space, PSW flags N C V Z E, CSP:IP, system stack SP;
* data paging through DPP0..3, EXTP/EXTPR page and EXTS/EXTSR segment
  overrides, EXTR (ESFR) and ATOMIC sequences;
* the full instruction table of the bundled C166 disassembler (Hajo
  Noerenberg's GPL tables), decoded into typed operands.

Peripherals (ADC, timers, CAN, ports) are not modelled: reads return what
the test put in memory. Instructions with timing or power effects (IDLE,
PWRDN, SRVWDT, DISWDT, EINIT) are no-ops; SRST and TRAP stop execution.

Default memory map for EDC15P: 512 KB flash at 0x080000-0x0FFFFF, mirrored
at 0x000000-0x00FFFF (segment 0), internal RAM / SFRs at 0x00E000-0x00FFFF.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

TABLES = Path(__file__).resolve().parents[1] / "legacy" / "data" / "c166"

# SFR word addresses
DPP0, CSP, MDH, MDL, CP, SP = 0xFE00, 0xFE08, 0xFE0C, 0xFE0E, 0xFE10, 0xFE12
STKOV, STKUN = 0xFE14, 0xFE16
PSW, MDC, ZEROS, ONES = 0xFF10, 0xFF0E, 0xFF1C, 0xFF1E
F_N, F_C, F_V, F_Z, F_E = 1, 2, 4, 8, 16

CONDS = ["UC", "NET", "Z", "NZ", "V", "NV", "N", "NN", "C", "NC", "SGT", "SLE", "SLT", "SGE", "UGT", "ULE"]


class EmuError(Exception):
    pass


class Stop(Exception):
    """Execution ended normally (return from the called function)."""


# ------------------------------------------------------------------ decode

@dataclass
class Op:
    kind: str           # Rw Rb reg_w reg_b mem ind ind_post ind_pre ind_disp imm bit bitoff cc caddr seg rel irang mask trap
    a: int = 0
    b: int = 0


@dataclass
class Insn:
    addr: int
    length: int
    opcode: int
    mnem: str
    ops: list
    raw: bytes

    def __str__(self):
        return f"{self.addr:06X}  {self.raw.hex().upper():<8}  {self.mnem} {', '.join(_fmt(o) for o in self.ops)}"


def _sfr_names():
    out = {}
    try:
        with open(TABLES / "c166_sfr.txt", encoding="latin-1") as fh:
            for line in fh:
                if line.lstrip().startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    out[int(parts[0], 2)] = parts[1]
    except OSError:
        pass
    return out


SFR_NAMES = _sfr_names()


def _regname(r, byte):
    if r >= 0xF0:
        n = r & 15
        return (("RL" if n % 2 == 0 else "RH") + str(n // 2)) if byte else f"R{n}"
    return SFR_NAMES.get(r, f"SFR[{0xFE00 + 2 * r:04X}]")


def _bitname(qq):
    if qq >= 0xF0:
        return f"R{qq & 15}"
    if qq < 0x80:
        return f"{0xFD00 + 2 * qq:04X}h"
    return SFR_NAMES.get(qq, f"{0xFF00 + 2 * (qq - 0x80):04X}h") if False else f"{0xFF00 + 2 * (qq - 0x80):04X}h"


def _fmt(o: Op) -> str:
    return {"Rw": lambda: f"R{o.a}", "Rb": lambda: ("RL" if o.a % 2 == 0 else "RH") + str(o.a // 2),
            "reg_w": lambda: _regname(o.a, False), "reg_b": lambda: _regname(o.a, True), "mem": lambda: f"{o.a:04X}h",
            "ind": lambda: f"[R{o.a}]", "ind_post": lambda: f"[R{o.a}+]", "ind_pre": lambda: f"[-R{o.a}]",
            "ind_disp": lambda: f"[R{o.a}+#{o.b:04X}h]", "imm": lambda: f"#{o.a:X}h", "bit": lambda: f"{_bitname(o.a)}.{o.b}",
            "bitoff": lambda: _bitname(o.a), "cc": lambda: CONDS[o.a], "caddr": lambda: f"{o.a:04X}h",
            "seg": lambda: f"{o.a:02X}h", "rel": lambda: f"{o.a:+d}", "irang": lambda: f"#{o.a}",
            "mask": lambda: f"#{o.a:02X}h", "trap": lambda: f"#{o.a}"}.get(o.kind, lambda: o.kind)()


class _Tok(str):
    pass


def _mark(kind, *vals):
    return "\x01" + kind + ":" + ",".join(str(v) for v in vals) + "\x01"


def _le16(bits):
    return int(bits[8:16] + bits[0:8], 2)


_HELPERS = {
    "cRw": lambda b: _mark("Rw", int(b, 2)),
    "cRb": lambda b: _mark("Rb", int(b, 2)),          # 4-bit: low bit = H
    "cregb": lambda b: _mark("reg_b", int(b, 2)),
    "cregw": lambda b: _mark("reg_w", int(b, 2)),
    "cmem": lambda b: _mark("mem", _le16(b)),
    "cbitaddr": lambda qq, q: _mark("bit", int(qq, 2), int(q, 2)),
    "cbitoff": lambda qq: _mark("bitoff", int(qq, 2)),
    "cirang2": lambda b: _mark("irang", int(b, 2) + 1),
    "cdata3": lambda b: _mark("imm", int(b, 2)),
    "cdata4": lambda b: _mark("imm", int(b, 2)),
    "cdata8": lambda b: _mark("imm", int(b, 2)),
    "cdata16": lambda b: _mark("imm", _le16(b)),
    "cmask8": lambda b: _mark("mask", int(b, 2)),
    "ccaddr": lambda b: _mark("caddr", _le16(b)),
    "cseg": lambda b: _mark("seg", int(b, 2)),
    "crel": lambda b: _mark("rel", int(b, 2) - 256 if int(b, 2) >= 128 else int(b, 2)),
    "ctrap7": lambda b: _mark("trap", int(b, 2)),
    "ccc": lambda b: _mark("cc", int(b, 2)),
}


def _perl_to_py(fmt):
    held = []

    def hold(m):
        held.append(m.group(0))
        return "\x02%d\x02" % (len(held) - 1)
    tmp = re.sub(r'"[^"]*"', hold, fmt)
    tmp = tmp.replace(".", "+").replace("$", "")
    return re.sub(r"\x02(\d+)\x02", lambda m: held[int(m.group(1))], tmp)


def _eval(node, ns):
    """Evaluate the restricted table expression: strings, +, helper calls, A-D."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return ns[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _eval(node.left, ns) + _eval(node.right, ns)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _HELPERS:
        return _HELPERS[node.func.id](*[_eval(a, ns) for a in node.args])
    raise EmuError("unsupported table expression")


_OPERAND = re.compile(r"\x01(\w+):([0-9,\-]*)\x01")


def _parse_operand(text: str) -> Op:
    marks = _OPERAND.findall(text)
    plain = _OPERAND.sub("@", text).strip()
    vals = [[int(v) for v in m[1].split(",") if v != ""] for m in marks]
    if plain == "@":
        kind, v = marks[0][0], vals[0]
        return Op(kind, *v)
    if plain == "[@]":
        return Op("ind", vals[0][0])
    if plain == "[@+]":
        return Op("ind_post", vals[0][0])
    if plain == "[-@]":
        return Op("ind_pre", vals[0][0])
    if plain == "[@+@]":
        return Op("ind_disp", vals[0][0], vals[1][0])
    raise EmuError(f"operand form {plain!r}")


class Decoder:
    def __init__(self, table_dir: Path = TABLES):
        self.length: dict[int, int] = {}
        self.forms: dict[int, list] = {}
        with open(table_dir / "c166_is.txt", encoding="latin-1") as fh:
            for line in fh:
                if line.lstrip().startswith("#"):
                    continue
                m = re.match(r"^(\w\w)\s+([24])\s+(\S+)\s+(.+)", line)
                if not m:
                    continue
                oc = int(m.group(1), 16)
                self.length[oc] = int(m.group(2))
                body = ast.parse(_perl_to_py(m.group(4).rstrip()), mode="eval").body
                self.forms.setdefault(oc, []).append((re.compile("^(?:" + m.group(3) + ")$"), body))
        self.cache: dict[bytes, tuple] = {}

    SPECIAL = {0xCC: "NOP", 0xCB: "RET", 0xDB: "RETS", 0xFB: "RETI", 0xA5: "DISWDT", 0xA7: "SRVWDT",
               0xB5: "EINIT", 0x87: "IDLE", 0x97: "PWRDN", 0xB7: "SRST"}

    def decode(self, raw: bytes, addr: int) -> Insn:
        op = raw[0]
        if op in self.SPECIAL:
            return Insn(addr, 4 if op in (0xA5, 0xA7, 0xB5, 0x87, 0x97, 0xB7) else 2, op, self.SPECIAL[op], [], raw[:2])
        if op in (0xA1, 0xB1):                        # NEGB / CPLB Rb
            return Insn(addr, 2, op, "NEGB" if op == 0xA1 else "CPLB", [Op("Rb", raw[1] >> 4)], raw[:2])
        if op in (0xC0, 0xD0):                        # MOVBZ / MOVBS Rw, Rb
            return Insn(addr, 2, op, "MOVBZ" if op == 0xC0 else "MOVBS", [Op("Rw", raw[1] & 15), Op("Rb", raw[1] >> 4)], raw[:2])
        if op == 0xD7:
            mode = raw[1] >> 6
            n = ((raw[1] >> 4) & 3) + 1
            v = raw[2] | (raw[3] << 8)
            return Insn(addr, 4, op, ("EXTS", "EXTP", "EXTSR", "EXTPR")[mode], [Op("imm", v), Op("irang", n)], raw[:4])
        if op in (0x0A, 0x1A):
            mask, data = (raw[2], raw[3]) if op == 0x0A else (raw[3], raw[2])
            return Insn(addr, 4, op, "BFLDL" if op == 0x0A else "BFLDH",
                        [Op("bitoff", raw[1]), Op("mask", mask), Op("imm", data)], raw[:4])
        n = self.length.get(op, 2)
        key = bytes(raw[:n])
        hit = self.cache.get(key)
        if hit:
            return Insn(addr, n, op, hit[0], hit[1], key)
        bits = "".join(f"{x:08b}" for x in key[1:])
        for rx, body in self.forms.get(op, []):
            m = rx.fullmatch(bits)
            if not m:
                continue
            g = list(m.groups()) + [None] * 4
            text = _eval(body, {"A": g[0], "B": g[1], "C": g[2], "D": g[3]})
            if "INCOMPLETE" in text:
                continue
            mnem, _, rest = text.strip().partition(" ")
            parts = [p for p in _split_ops(rest.strip())] if rest.strip() else []
            ops = [_parse_operand(p) for p in parts]
            self.cache[key] = (mnem, ops)
            return Insn(addr, n, op, mnem, ops, key)
        raise EmuError(f"undecodable instruction {key.hex()} at {addr:06X}")


def _split_ops(s):
    out, depth, cur, inmark = [], 0, "", False
    for ch in s:
        if ch == "":
            inmark = not inmark
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0 and not inmark:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------------------------ CPU

@dataclass
class Access:
    kind: str           # "r" / "w" / "x"
    addr: int
    size: int
    value: int


class C167:
    def __init__(self, flash: bytes | None = None, flash_base: int = 0x080000, mirror_seg0: bool = True):
        self.mem = bytearray(0x1000000)
        self.rom_ranges: list[tuple[int, int]] = []
        if flash is not None:
            self.load_flash(flash, flash_base, mirror_seg0)
        self.dec = Decoder()
        self.csp = 0
        self.ip = 0
        self.ext_mode = None          # ("page"|"seg", value, register_only, remaining)
        self.extr_left = 0
        self.trace: list[Insn] | None = None
        self.accesses: list[Access] | None = None
        self.flash_reads: dict[int, int] = {}      # page -> count
        self.steps = 0
        self.write_rom = False
        self.hooks: dict[int, object] = {}          # addr24 -> callable(cpu) executed before insn
        self.reset_sfrs()

    # ------------------------------------------------------------- setup
    def load_flash(self, flash: bytes, base: int = 0x080000, mirror_seg0: bool = True):
        self.mem[base:base + len(flash)] = flash
        self.rom_ranges.append((base, base + len(flash)))
        if mirror_seg0:
            n = min(len(flash), 0xC000)   # 0xC000.. is RAM / XRAM / IRAM / SFR (DPP3 page)
            self.mem[0:n] = flash[:n]
            self.rom_ranges.append((0, n))

    def reset_sfrs(self):
        for i in range(4):
            self.wsfr(DPP0 + 2 * i, i)
        self.wsfr(CP, 0xFC00)
        self.wsfr(SP, 0xFC00)
        self.wsfr(STKOV, 0xFA00)
        self.wsfr(STKUN, 0xFC00)
        self.wsfr(PSW, 0)
        self.wsfr(ONES, 0xFFFF)
        self.wsfr(ZEROS, 0)

    # ------------------------------------------------------- raw memory
    def _rom(self, a):
        return any(s <= a < e for s, e in self.rom_ranges)

    def r8(self, a):
        a &= 0xFFFFFF
        v = self.mem[a]
        if self.accesses is not None:
            self.accesses.append(Access("r", a, 1, v))
        if 0x080000 <= a < 0x100000:
            self.flash_reads[a >> 14] = self.flash_reads.get(a >> 14, 0) + 1
        return v

    def r16(self, a):
        a &= 0xFFFFFE
        v = self.mem[a] | (self.mem[a + 1] << 8)
        if a in (ZEROS, ONES):
            v = 0 if a == ZEROS else 0xFFFF
        if self.accesses is not None:
            self.accesses.append(Access("r", a, 2, v))
        if 0x080000 <= a < 0x100000:
            self.flash_reads[a >> 14] = self.flash_reads.get(a >> 14, 0) + 1
        return v

    def w8(self, a, v):
        a &= 0xFFFFFF
        if self._rom(a) and not self.write_rom:
            raise EmuError(f"write to flash {a:06X} at {self.csp:02X}:{self.ip:04X}")
        self.mem[a] = v & 0xFF
        if self.accesses is not None:
            self.accesses.append(Access("w", a, 1, v & 0xFF))

    def w16(self, a, v):
        a &= 0xFFFFFE
        if self._rom(a) and not self.write_rom:
            raise EmuError(f"write to flash {a:06X} at {self.csp:02X}:{self.ip:04X}")
        self.mem[a] = v & 0xFF
        self.mem[a + 1] = (v >> 8) & 0xFF
        if self.accesses is not None:
            self.accesses.append(Access("w", a, 2, v & 0xFFFF))

    def rsfr(self, a):
        return self.mem[a] | (self.mem[a + 1] << 8)

    def wsfr(self, a, v):
        self.mem[a] = v & 0xFF
        self.mem[a + 1] = (v >> 8) & 0xFF

    # ---------------------------------------------------------- registers
    @property
    def psw(self):
        return self.rsfr(PSW)

    def flag(self, f):
        return bool(self.psw & f)

    def set_flags(self, **kw):
        p = self.psw
        for name, val in kw.items():
            bit = {"N": F_N, "C": F_C, "V": F_V, "Z": F_Z, "E": F_E}[name]
            p = (p | bit) if val else (p & ~bit)
        self.wsfr(PSW, p)

    def gpr_addr(self, n):
        return (self.rsfr(CP) + 2 * n) & 0xFFFF

    def R(self, n):
        return self.rsfr(self.gpr_addr(n))

    def setR(self, n, v):
        self.wsfr(self.gpr_addr(n), v & 0xFFFF)

    def Rb(self, n):
        return self.mem[self.gpr_addr(n >> 1) + (n & 1)]

    def setRb(self, n, v):
        self.mem[self.gpr_addr(n >> 1) + (n & 1)] = v & 0xFF

    def dpp(self, n):
        return self.rsfr(DPP0 + 2 * n) & 0x3FF

    # ------------------------------------------------------ address calc
    def data_addr(self, a16: int, use_ext=True) -> int:
        a16 &= 0xFFFF
        if use_ext and self.ext_mode and not self.ext_mode[2]:
            kind, val = self.ext_mode[0], self.ext_mode[1]
            if kind == "page":
                return (val << 14) | (a16 & 0x3FFF)
            return (val << 16) | a16
        return (self.dpp(a16 >> 14) << 14) | (a16 & 0x3FFF)

    def reg_addr(self, r, byte=False):
        """Short 8-bit register address: GPR, SFR or ESFR."""
        if r >= 0xF0:
            return ("gpr", r & 15)
        base = 0xF000 if self.extr_left else 0xFE00
        return ("sfr", base + 2 * r)

    def bit_word(self, qq):
        if qq >= 0xF0:
            return ("gpr", qq & 15)
        if qq < 0x80:
            return ("mem", 0xFD00 + 2 * qq)
        base = 0xF100 if self.extr_left else 0xFF00
        return ("mem", base + 2 * (qq - 0x80))

    # ------------------------------------------------------ operand I/O
    def read(self, o: Op, byte: bool):
        k = o.kind
        if k == "Rw":
            return self.R(o.a)
        if k == "Rb":
            return self.Rb(o.a)
        if k in ("reg_w", "reg_b"):
            t, a = self.reg_addr(o.a)
            if t == "gpr":
                return self.Rb(o.a & 15) if byte else self.R(o.a & 15)
            return self.r8(a) if byte else self.r16(a)
        if k == "mem":
            a = self.data_addr(o.a)
            return self.r8(a) if byte else self.r16(a)
        if k == "ind":
            a = self.data_addr(self.R(o.a))
            return self.r8(a) if byte else self.r16(a)
        if k == "ind_post":
            a = self.data_addr(self.R(o.a))
            v = self.r8(a) if byte else self.r16(a)
            self.setR(o.a, self.R(o.a) + (1 if byte else 2))
            return v
        if k == "ind_disp":
            a = self.data_addr(self.R(o.a) + o.b)
            return self.r8(a) if byte else self.r16(a)
        if k in ("imm", "mask"):
            return o.a & (0xFF if byte else 0xFFFF)
        raise EmuError(f"read {k}")

    def write(self, o: Op, byte: bool, v: int):
        k = o.kind
        if k == "Rw":
            return self.setR(o.a, v)
        if k == "Rb":
            return self.setRb(o.a, v)
        if k in ("reg_w", "reg_b"):
            t, a = self.reg_addr(o.a)
            if t == "gpr":
                return self.setRb(o.a & 15, v) if byte else self.setR(o.a & 15, v)
            return self.w8(a, v) if byte else self.w16(a, v)
        if k == "mem":
            a = self.data_addr(o.a)
            return self.w8(a, v) if byte else self.w16(a, v)
        if k == "ind":
            a = self.data_addr(self.R(o.a))
            return self.w8(a, v) if byte else self.w16(a, v)
        if k == "ind_pre":
            self.setR(o.a, self.R(o.a) - (1 if byte else 2))
            a = self.data_addr(self.R(o.a))
            return self.w8(a, v) if byte else self.w16(a, v)
        if k == "ind_post":
            a = self.data_addr(self.R(o.a))
            (self.w8(a, v) if byte else self.w16(a, v))
            return self.setR(o.a, self.R(o.a) + (1 if byte else 2))
        if k == "ind_disp":
            a = self.data_addr(self.R(o.a) + o.b)
            return self.w8(a, v) if byte else self.w16(a, v)
        raise EmuError(f"write {k}")

    # bits
    def bit_get(self, qq, q):
        t, a = self.bit_word(qq)
        w = self.R(a) if t == "gpr" else self.r16(a)
        return (w >> q) & 1

    def bit_set(self, qq, q, v):
        t, a = self.bit_word(qq)
        w = self.R(a) if t == "gpr" else self.r16(a)
        w = (w | (1 << q)) if v else (w & ~(1 << q))
        if t == "gpr":
            self.setR(a, w)
        else:
            self.w16(a, w)

    # stack
    def push(self, v):
        sp = (self.rsfr(SP) - 2) & 0xFFFF
        self.wsfr(SP, sp)
        self.w16(sp, v)                 # system stack: internal RAM, segment 0

    def pop(self):
        sp = self.rsfr(SP)
        v = self.r16(sp)
        self.wsfr(SP, (sp + 2) & 0xFFFF)
        return v

    # ---------------------------------------------------------- conditions
    def cond(self, cc):
        p = self.psw
        n, c, v, z, e = bool(p & F_N), bool(p & F_C), bool(p & F_V), bool(p & F_Z), bool(p & F_E)
        return [True, not z and not e, z, not z, v, not v, n, not n, c, not c,
                not z and n == v, z or n != v, n != v, n == v, not c and not z, c or z][cc]

    # ---------------------------------------------------------- execution
    @property
    def pc(self):
        return (self.csp << 16) | self.ip

    def fetch(self) -> Insn:
        a = self.pc
        raw = bytes(self.mem[a:a + 4])
        return self.dec.decode(raw, a)

    def step(self):
        a = self.pc
        if a in self.hooks:
            if self.hooks[a](self) is False:
                return
        ins = self.fetch()
        if self.trace is not None:
            self.trace.append(ins)
        self.ip = (self.ip + ins.length) & 0xFFFF
        ext_before = self.ext_mode
        extr_before = self.extr_left
        self.execute(ins)
        self.steps += 1
        # count down EXT* prefixes (the prefix itself does not count)
        if ext_before is not None and ins.mnem not in ("EXTP", "EXTS", "EXTPR", "EXTSR"):
            k, v, ro, n = ext_before
            self.ext_mode = (k, v, ro, n - 1) if n > 1 else None
        if extr_before and ins.mnem not in ("EXTR", "EXTPR", "EXTSR", "ATOMIC"):
            self.extr_left = extr_before - 1

    # flags helpers
    def _nz(self, r, byte):
        top = 0x80 if byte else 0x8000
        mask = 0xFF if byte else 0xFFFF
        return dict(N=bool(r & top), Z=(r & mask) == 0, E=(r & mask) == top)

    def _add(self, a, b, byte, carry=0, keepz=False):
        mask, top = (0xFF, 0x80) if byte else (0xFFFF, 0x8000)
        r = a + b + carry
        res = r & mask
        f = self._nz(res, byte)
        f["C"] = r > mask
        f["V"] = bool(~(a ^ b) & (a ^ res) & top)
        if keepz:
            f["Z"] = f["Z"] and self.flag(F_Z)
        self.set_flags(**f)
        return res

    def _sub(self, a, b, byte, borrow=0, keepz=False):
        mask, top = (0xFF, 0x80) if byte else (0xFFFF, 0x8000)
        r = a - b - borrow
        res = r & mask
        f = self._nz(res, byte)
        f["C"] = r < 0
        f["V"] = bool((a ^ b) & (a ^ res) & top)
        if keepz:
            f["Z"] = f["Z"] and self.flag(F_Z)
        self.set_flags(**f)
        return res

    def _logic(self, res, byte):
        f = self._nz(res, byte)
        f.update(C=False, V=False)
        self.set_flags(**f)
        return res

    ALU = {"ADD": ("add", 0), "ADDB": ("add", 1), "ADDC": ("addc", 0), "ADDCB": ("addc", 1),
           "SUB": ("sub", 0), "SUBB": ("sub", 1), "SUBC": ("subc", 0), "SUBCB": ("subc", 1),
           "CMP": ("cmp", 0), "CMPB": ("cmp", 1), "AND": ("and", 0), "ANDB": ("and", 1),
           "OR": ("or", 0), "ORB": ("or", 1), "XOR": ("xor", 0), "XORB": ("xor", 1)}

    def execute(self, ins: Insn):
        m, ops = ins.mnem, ins.ops
        if m in self.ALU:
            op, byte = self.ALU[m]
            byte = bool(byte)
            dst, src = ops
            a = self.read(dst, byte)
            b = self.read(src, byte)
            if op == "add":
                r = self._add(a, b, byte)
            elif op == "addc":
                r = self._add(a, b, byte, int(self.flag(F_C)), keepz=True)
            elif op == "sub":
                r = self._sub(a, b, byte)
            elif op == "subc":
                r = self._sub(a, b, byte, int(self.flag(F_C)), keepz=True)
            elif op == "cmp":
                self._sub(a, b, byte)
                return
            elif op == "and":
                r = self._logic(a & b, byte)
            elif op == "or":
                r = self._logic(a | b, byte)
            else:
                r = self._logic(a ^ b, byte)
            self.write(dst, byte, r)
            return
        if m in ("MOV", "MOVB"):
            byte = m == "MOVB"
            dst, src = ops
            v = self.read(src, byte)
            if dst.kind == "ind_pre":
                self.write(dst, byte, v)
            else:
                self.write(dst, byte, v)
            self.set_flags(**self._nz(v, byte))
            return
        if m in ("MOVBZ", "MOVBS"):
            dst, src = ops
            v = self.read(src, True)
            if m == "MOVBS" and v & 0x80:
                v |= 0xFF00
            self.write(dst, False, v)
            self.set_flags(**self._nz(v, False))
            return
        if m in ("NEG", "NEGB"):
            b = m == "NEGB"
            r = self._sub(0, self.read(ops[0], b), b)
            self.write(ops[0], b, r)
            return
        if m in ("CPL", "CPLB"):
            b = m == "CPLB"
            r = (~self.read(ops[0], b)) & (0xFF if b else 0xFFFF)
            self.write(ops[0], b, r)
            self.set_flags(**self._nz(r, b))
            return
        if m in ("SHL", "SHR", "ROL", "ROR", "ASHR"):
            return self._shift(m, ops)
        if m in ("MUL", "MULU"):
            a, b = self.read(ops[0], False), self.read(ops[1], False)
            if m == "MUL":
                a, b = _s16(a), _s16(b)
            r = (a * b) & 0xFFFFFFFF
            self.wsfr(MDH, r >> 16)
            self.wsfr(MDL, r & 0xFFFF)
            self.set_flags(N=bool(r & 0x80000000), Z=r == 0, C=False, E=False,
                           V=(m == "MUL" and not -0x8000 <= a * b <= 0x7FFF) or (m == "MULU" and r > 0xFFFF))
            return
        if m in ("DIV", "DIVU", "DIVL", "DIVLU"):
            return self._div(m, ops)
        if m in ("CMPI1", "CMPI2", "CMPD1", "CMPD2"):
            n = ops[0].a
            a, b = self.R(n), self.read(ops[1], False)
            self._sub(a, b, False)
            d = 1 if m.endswith("1") else 2
            self.setR(n, a + d if m.startswith("CMPI") else a - d)
            return
        if m in ("BSET", "BCLR"):
            o = ops[0]
            self.bit_set(o.a, o.b, m == "BSET")
            self.set_flags(N=False, C=False, V=False, E=False, Z=True)
            return
        if m in ("BMOV", "BMOVN", "BAND", "BOR", "BXOR", "BCMP"):
            d, s = ops
            bd, bs = self.bit_get(d.a, d.b), self.bit_get(s.a, s.b)
            if m == "BCMP":
                self.set_flags(N=bool(bd ^ bs), C=bool(bd & bs), V=bool(bd | bs), Z=not (bd | bs), E=False)
                return
            r = {"BMOV": bs, "BMOVN": 1 - bs, "BAND": bd & bs, "BOR": bd | bs, "BXOR": bd ^ bs}[m]
            self.bit_set(d.a, d.b, r)
            self.set_flags(N=bool(bd ^ bs), C=bool(bd & bs), V=bool(bd | bs), Z=not (bd | bs), E=False)
            return
        if m in ("BFLDL", "BFLDH"):
            t, a = self.bit_word(ops[0].a)
            w = self.R(a) if t == "gpr" else self.r16(a)
            mask, data = ops[1].a, ops[2].a
            sh = 0 if m == "BFLDL" else 8
            w = (w & ~(mask << sh)) | ((data & mask) << sh)
            self.setR(a, w) if t == "gpr" else self.w16(a, w)
            self.set_flags(**self._nz(w, False))
            return
        if m == "JMPR":
            cc, rel = ops
            if self.cond(cc.a):
                self.ip = (self.ip + 2 * rel.a) & 0xFFFF
            return
        if m == "JMPA":
            cc, t = ops
            if self.cond(cc.a):
                self.ip = t.a
            return
        if m == "JMPS":
            self.csp, self.ip = ops[0].a, ops[1].a
            return
        if m == "JMPI":
            cc, r = ops
            if self.cond(cc.a):
                self.ip = self.R(r.a)
            return
        if m in ("JB", "JNB", "JBC", "JNBS"):
            bit, rel = ops
            v = self.bit_get(bit.a, bit.b)
            take = v if m in ("JB", "JBC") else not v
            if m == "JBC" and v:
                self.bit_set(bit.a, bit.b, 0)
            if m == "JNBS" and not v:
                self.bit_set(bit.a, bit.b, 1)
            if take:
                self.ip = (self.ip + 2 * rel.a) & 0xFFFF
            return
        if m == "CALLR":
            self.push(self.ip)
            self.ip = (self.ip + 2 * ops[0].a) & 0xFFFF
            return
        if m == "CALLA":
            if self.cond(ops[0].a):
                self.push(self.ip)
                self.ip = ops[1].a
            return
        if m == "CALLI":
            if self.cond(ops[0].a):
                self.push(self.ip)
                self.ip = self.R(ops[1].a)
            return
        if m == "CALLS":
            self.push(self.csp)
            self.push(self.ip)
            self.csp, self.ip = ops[0].a, ops[1].a
            return
        if m == "PCALL":
            reg, t = ops
            self.push(self.read(reg, False))
            self.push(self.ip)
            self.ip = t.a
            return
        if m == "RET":
            self._ret(False)
            return
        if m == "RETS":
            self._ret(True)
            return
        if m == "RETP":
            self._ret(False)
            self.write(ops[0], False, self.pop())
            return
        if m == "RETI":
            self.ip = self.pop()
            self.csp = self.pop()
            self.wsfr(PSW, self.pop())
            return
        if m == "PUSH":
            self.push(self.read(ops[0], False))
            return
        if m == "POP":
            self.write(ops[0], False, self.pop())
            return
        if m == "SCXT":
            reg, src = ops
            self.push(self.read(reg, False))
            self.write(reg, False, self.read(src, False))
            return
        if m in ("EXTP", "EXTS", "EXTPR", "EXTSR"):
            v, n = ops[0].a, ops[1].a
            self.ext_mode = ("page" if m.startswith("EXTP") else "seg", v, False, n)
            if m.endswith("R"):
                self.extr_left = n
            return
        if m == "EXTR":
            self.extr_left = ops[0].a
            return
        if m in ("ATOMIC", "NOP", "PRIOR", "DISWDT", "SRVWDT", "EINIT", "IDLE", "PWRDN"):
            if m == "PRIOR":
                self.write(ops[0], False, 0)
            return
        if m in ("SRST", "TRAP"):
            raise Stop(m)
        raise EmuError(f"no semantics for {m} at {ins.addr:06X}")

    def _ret(self, inter):
        sp_before = self.rsfr(SP)
        if self._stop_sp is not None and sp_before >= self._stop_sp:
            raise Stop("return")
        self.ip = self.pop()
        if inter:
            self.csp = self.pop() & 0xFF

    def _shift(self, m, ops):
        n = self.read(ops[1], False) & 15
        v = self.R(ops[0].a)
        if n == 0:
            self.set_flags(**self._nz(v, False), C=False, V=False)
            return
        if m == "SHL":
            c = (v >> (16 - n)) & 1
            r = (v << n) & 0xFFFF
        elif m == "SHR":
            c = (v >> (n - 1)) & 1
            r = v >> n
        elif m == "ROL":
            r = ((v << n) | (v >> (16 - n))) & 0xFFFF
            c = r & 1
        elif m == "ROR":
            r = ((v >> n) | (v << (16 - n))) & 0xFFFF
            c = (r >> 15) & 1
        else:  # ASHR
            sv = _s16(v)
            c = (sv >> (n - 1)) & 1
            r = (sv >> n) & 0xFFFF
        self.setR(ops[0].a, r)
        self.set_flags(**self._nz(r, False), C=bool(c), V=False)

    def _div(self, m, ops):
        d = self.R(ops[0].a)
        if m in ("DIV", "DIVU"):
            a = self.rsfr(MDL)
        else:
            a = (self.rsfr(MDH) << 16) | self.rsfr(MDL)
        if d == 0:
            self.set_flags(V=True)
            return
        if m in ("DIV", "DIVL"):
            sa = _s16(a) if m == "DIV" else (a - (1 << 32) if a & 0x80000000 else a)
            sd = _s16(d)
            q = int(sa / sd)
            r = sa - q * sd
        else:
            q, r = divmod(a, d)
        self.wsfr(MDL, q & 0xFFFF)
        self.wsfr(MDH, r & 0xFFFF)
        self.set_flags(N=bool(q & 0x8000), Z=(q & 0xFFFF) == 0, C=False, E=False, V=not -0x8000 <= q <= 0xFFFF)

    # -------------------------------------------------------------- run
    _stop_sp = None

    def call(self, addr24: int, regs: dict | None = None, max_steps: int = 200000, trace: bool = False):
        """Call a function (intra- or inter-segment) and run until it returns."""
        for k, v in (regs or {}).items():
            self.setR(int(str(k).lstrip("R")), v)
        # fake CALLS frame: return to the sentinel 0xFF:FFF0
        self.push(0xFF)
        self.push(0xFFF0)
        self._stop_sp = self.rsfr(SP)
        self.csp, self.ip = addr24 >> 16, addr24 & 0xFFFF
        if trace:
            self.trace = []
        try:
            for _ in range(max_steps):
                self.step()
                if self.csp == 0xFF and self.ip == 0xFFF0:
                    break
            else:
                raise EmuError(f"no return after {max_steps} steps (at {self.pc:06X})")
        except Stop:
            pass
        finally:
            self._stop_sp = None
        return self


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v
