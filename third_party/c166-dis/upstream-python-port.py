# c166_disasm.py  --  Linear C166/C167 disassembler as an IDA Pro plugin.
#
# IDA's stock C166 module fragments DPP-banked EDC15 code into 2-4 byte "functions"
# and mis-renders operands, which makes tracing the fuel/CAN routines painful. This
# plugin gives a clean *linear* decode of any address range (no function-boundary
# guessing), rendered straight to the Output window or returned to a caller.
#
# It is a faithful Python port of Hajo Noerenberg's `c166-dis.pl` and reuses the
# very same opcode tables (c166_is.txt / c166_cc.txt / c166_sfr.txt), which must
# sit next to this file. Output matches the Perl tool byte-for-byte.
#
# Programmatic use (e.g. from the MCP console):
#     import c166_disasm as c
#     print(c.disasm(0x94640, 0x40))          # start EA, length -> text
#
# Interactive use: Edit > Plugins > "C166 linear disassembler" (hotkey Ctrl-Shift-D)
# prompts for a start address + length and prints the listing.
#
# Author: Kristof  (krstoff.com)
# Port license follows the original: GPL-3.0. Original (C) 2000 Hajo Noerenberg.

import os
import re

try:
    import ida_bytes
    import ida_idaapi
    import ida_kernwin
    import idc
    _HAVE_IDA = True
except ImportError:  # allow standalone testing with plain CPython
    _HAVE_IDA = False


# --------------------------------------------------------------------------- #
#  Core decoder (pure Python, no IDA dependency)
# --------------------------------------------------------------------------- #

class C166Disassembler:
    """Table-driven C166 decoder. Loads the three .txt tables from `table_dir`
    (defaults to this file's directory)."""

    def __init__(self, table_dir=None):
        if table_dir is None:
            table_dir = os.path.dirname(os.path.abspath(__file__))
        self.clen = {}          # opcode -> instruction length (2 or 4)
        self.cpatt = {}         # opcode -> [compiled bit-pattern regex, ...]
        self.cout = {}          # opcode -> [python format expression, ...]
        self.ccc = {}           # 4-bit string -> condition-code name
        self.csfr = {}          # 8-bit string -> SFR name
        self._ip = 0            # current instruction address (for crel)
        self._fread = 2         # current instruction length (for crel)
        self._load(table_dir)

    # ---- table loading -------------------------------------------------- #

    def _load(self, d):
        for bits, name in self._pairs(os.path.join(d, "c166_cc.txt")):
            self.ccc[bits] = name
        for bits, name in self._pairs(os.path.join(d, "c166_sfr.txt")):
            self.csfr[bits] = name
        with open(os.path.join(d, "c166_is.txt"), "r", encoding="latin-1") as f:
            for line in f:
                if line.lstrip().startswith("#"):
                    continue
                m = re.match(r"^(\w\w)\s+([24])\s+(\S+)\s+(.+)", line)
                if not m:
                    continue
                oc = int(m.group(1), 16)
                self.clen[oc] = int(m.group(2))
                self.cpatt.setdefault(oc, []).append(re.compile("^" + m.group(3)))
                self.cout.setdefault(oc, []).append(self._perl_to_py(m.group(4).rstrip()))

    @staticmethod
    def _pairs(path):
        with open(path, "r", encoding="latin-1") as f:
            for line in f:
                if line.lstrip().startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    yield parts[0], parts[1]

    @staticmethod
    def _perl_to_py(fmt):
        """Translate a Perl concat expression (e.g. '"ADD ".cRw($A)') into Python.
        Every top-level '.' is string concatenation; '$X' are capture groups."""
        held = []
        def hold(m):
            held.append(m.group(0))
            return "\x01%d\x01" % (len(held) - 1)
        tmp = re.sub(r'"[^"]*"', hold, fmt)      # protect string literals
        tmp = tmp.replace(".", "+").replace("$", "")
        tmp = re.sub(r"\x01(\d+)\x01", lambda m: held[int(m.group(1))], tmp)
        return tmp

    # ---- operand-formatting helpers (mirror the Perl subs) -------------- #

    @staticmethod
    def cRw(b):
        return "R%d" % int(b, 2)

    @staticmethod
    def cRb(b):
        return ("RL" if b[3] == "0" else "RH") + str(int(b[0:3], 2))

    def cregb(self, b):
        if b[0:4] == "1111":
            return self.cRb(b[4:8])
        return self.csfr.get(b, "0x%02X" % int(b, 2))

    def cregw(self, b):
        if b[0:4] == "1111":
            return self.cRw(b[4:8])
        return self.csfr.get(b, "0x%02X" % int(b, 2))

    @staticmethod
    def cmem(b):
        return "0x%04X" % int(b[8:16] + b[0:8], 2)      # byte-swapped (LE)

    def cbitaddr(self, qq, q):
        return "%s.%d" % (self.cregw(qq), int(q, 2))

    @staticmethod
    def cbitoff(_qq):
        return "(INCOMPLETE bitoff)"

    @staticmethod
    def cirang2(b):
        return "#%d" % int(b, 2)

    @staticmethod
    def cdata3(b):
        return "#%d" % int(b, 2)

    @staticmethod
    def cdata4(b):
        return "#%d" % int(b, 2)

    @staticmethod
    def cdata8(b):
        return "#0x%02X" % int(b, 2)

    @staticmethod
    def cdata16(b):
        return "#0x%04X" % int(b[8:16] + b[0:8], 2)

    @staticmethod
    def cmask8(_b):
        return "(INCOMPLETE mask8)"

    @staticmethod
    def ccaddr(b):
        return "0x%04X" % int(b[8:16] + b[0:8], 2)

    @staticmethod
    def cseg(b):
        return "0x%02X" % int(b, 2)

    def crel(self, b):
        t = int(b, 2)
        if t >= 128:
            t -= 256
        return "0x%08X" % (self._ip + self._fread + 2 * t)

    @staticmethod
    def ctrap7(_b):
        return "(INCOMPLETE trap7)"

    def ccc_(self, b):
        return self.ccc.get(b, "cc_?")

    def _namespace(self, groups):
        ns = {"A": groups[0], "B": groups[1], "C": groups[2], "D": groups[3]}
        for h in ("cRw", "cRb", "cregb", "cregw", "cmem", "cbitaddr", "cbitoff",
                  "cirang2", "cdata3", "cdata4", "cdata8", "cdata16", "cmask8",
                  "ccaddr", "cseg", "crel", "ctrap7"):
            ns[h] = getattr(self, h)
        ns["ccc"] = self.ccc_
        return ns

    # ---- decode --------------------------------------------------------- #

    def decode_one(self, buf, off, ea):
        """Decode one instruction from `buf` at byte offset `off`, whose runtime
        address is `ea`. Returns (length, raw_hex, text)."""
        oc = buf[off]
        length = self.clen.get(oc, 2)
        if off + length > len(buf):
            length = 2
        raw = buf[off:off + length]
        self._ip, self._fread = ea, length
        # bits of the operand bytes (everything after the opcode byte)
        bits = "".join("{:08b}".format(x) for x in raw[1:])
        text = "(unknown 0x%02X)" % oc
        for rx, fexpr in zip(self.cpatt.get(oc, []), self.cout.get(oc, [])):
            m = rx.match(bits)
            if m:
                g = list(m.groups()) + [None, None, None, None]
                try:
                    text = eval(fexpr, {"__builtins__": {}}, self._namespace(g))  # noqa: S307
                except Exception as e:                                            # pragma: no cover
                    text = "(decode error: %s)" % e
                break
        return length, raw.hex().upper(), text

    def decode_range(self, buf, base_ea, length):
        """Linearly decode `length` bytes of `buf` (which begins at `base_ea`).
        Returns a list of (ea, raw_hex, text)."""
        out, off = [], 0
        while off < length and off < len(buf):
            ln, raw, text = self.decode_one(buf, off, base_ea + off)
            out.append((base_ea + off, raw, text))
            off += ln
        return out


# --------------------------------------------------------------------------- #
#  Convenience API (used both by the plugin action and programmatically)
# --------------------------------------------------------------------------- #

_DIS = None


def _dis():
    global _DIS
    if _DIS is None:
        _DIS = C166Disassembler()
    return _DIS


def disasm(start_ea, length):
    """Linear-disassemble `length` bytes starting at `start_ea` (reads live IDA
    bytes) and return the listing as one string."""
    if not _HAVE_IDA:
        raise RuntimeError("disasm() needs IDA; use decode_range() standalone")
    buf = ida_bytes.get_bytes(start_ea, length)
    if buf is None:
        return "(no bytes at 0x%X)" % start_ea
    rows = _dis().decode_range(buf, start_ea, length)
    return "\n".join("%08X  %-8s  %s" % (ea, raw, text) for ea, raw, text in rows)


# --------------------------------------------------------------------------- #
#  IDA plugin wrapper (modern plugmod_t framework)
# --------------------------------------------------------------------------- #

if _HAVE_IDA:

    class _C166Plugmod(ida_idaapi.plugmod_t):
        def run(self, arg):
            ea = ida_kernwin.get_screen_ea()
            ea = ida_kernwin.ask_addr(ea, "C166 linear disassembler: start address")
            if ea is None:
                return 0
            n = ida_kernwin.ask_long(0x40, "Number of bytes to disassemble")
            if n is None or n <= 0:
                return 0
            print("; --- C166 linear disasm 0x%X..0x%X ---" % (ea, ea + n))
            print(disasm(ea, n))
            return 1

    class C166DisasmPlugin(ida_idaapi.plugin_t):
        flags = ida_idaapi.PLUGIN_UNL | ida_idaapi.PLUGIN_MULTI
        comment = "Clean linear C166/C167 disassembly for DPP-banked EDC15 code"
        help = "Prompts for a start address + length and prints a linear decode"
        wanted_name = "C166 linear disassembler"
        wanted_hotkey = "Ctrl-Shift-D"

        def init(self):
            print("[c166_disasm] loaded (author: Kristof / krstoff.com) - Ctrl-Shift-D")
            return _C166Plugmod()

    def PLUGIN_ENTRY():
        return C166DisasmPlugin()
