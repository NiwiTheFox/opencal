"""GPL-3.0-only. Derived from Hajo Noerenberg/Kristof C166 decoder.
OpenCal bounded decoder; upstream sources and notices in third_party/c166-dis.
No state recovery: DPP/EXTR-dependent physical data targets remain unresolved.
"""
import ast,os,re
from pathlib import Path


def interpret(node,names):
    """Interpret only table string concatenation and named formatting helpers."""
    if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
    if isinstance(node,ast.Name) and node.id in ('A','B','C','D'):return names[node.id]
    if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):return interpret(node.left,names)+interpret(node.right,names)
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in names and callable(names[node.func.id]) and not node.keywords:
        return names[node.func.id](*(interpret(arg,names) for arg in node.args))
    raise ValueError('Unsupported decoder table expression.')


class C166Disassembler:
    """Table-driven C166 decoder. Loads the three .txt tables from `table_dir`
    (defaults to this file's directory)."""

    def __init__(self, table_dir=None, cpu="80c167"):
        if cpu not in ("80c166","80c167","80c167cs"):raise ValueError("Unsupported C166 CPU variant.")
        self.cpu=cpu
        if table_dir is None:
            table_dir = str(Path(__file__).parent/'data/c166')
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
                self.cpatt.setdefault(oc, []).append(re.compile("^(?:" + m.group(3) + ")$"))
                self.cout.setdefault(oc, []).append(ast.parse(self._perl_to_py(m.group(4).rstrip()),mode="eval").body)

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
        return "SFR8[0x%02X]" % int(b,2)

    def cregw(self, b):
        if b[0:4] == "1111":
            return self.cRw(b[4:8])
        return "SFR16[0x%02X]" % int(b,2)

    @staticmethod
    def cmem(b):
        return "0x%04X" % int(b[8:16] + b[0:8], 2)      # byte-swapped (LE)

    def cbitaddr(self, qq, q):
        return "%s.%d" % (self.cbitoff(qq), int(q, 2))

    @staticmethod
    def cbitoff(_qq):
        value=int(_qq,2)
        return "R%d" % (value-0xf0) if value>=0xf0 else "0x%04X" % ((0xfd00+value*2) if value<0x80 else (0xff00+(value-0x80)*2))

    @staticmethod
    def cirang2(b):
        return "#%d" % (int(b, 2)+1)

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
        return "#0x%02X" % int(_b,2)

    def ccaddr(self,b):
        target=int(b[8:16]+b[0:8],2)
        return "0x%06X" % ((self._ip&0xff0000)|target) if self._opcode in (0xea,0xca) else "0x%04X" % target

    @staticmethod
    def cseg(b):
        return "0x%02X" % int(b, 2)

    def crel(self, b):
        t = int(b, 2)
        if t >= 128:
            t -= 256
        return "0x%06X" % ((self._ip&0xff0000)|((self._ip+self._fread+2*t)&0xffff))

    @staticmethod
    def ctrap7(_b):
        return "#%d" % int(_b,2)

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

    def decode_one(self,buf,off,ea):
        if type(off) is not int or not 0<=off<len(buf) or not 0<=ea<=(0x3ffff if self.cpu=='80c166' else 0xffffff):
            raise ValueError('Invalid decode offset or CPU address.')
        opcode=buf[off];length=self.clen.get(opcode,2);raw=bytes(buf[off:off+length])
        if len(raw)<length:return len(raw),raw.hex().upper(),'(truncated instruction)'
        if self.cpu=='80c166' and opcode in (0xd1,0xd7,0xdc):return length,raw.hex().upper(),'(unknown: instruction requires C167)'
        self._ip,self._fread,self._opcode=ea,length,opcode
        if opcode in (0xd0,0xc0):
            return length,raw.hex().upper(),f'{"MOVBS" if opcode==0xd0 else "MOVBZ"} R{raw[1]&15},{self.cRb(f"{raw[1]>>4:04b}")}'
        if opcode==0xd7:
            mode=raw[1]>>6;count=((raw[1]>>4)&3)+1;value=int.from_bytes(raw[2:4],'little')
            if raw[1]&15 or value>(0x3ff if mode&1 else 0xff):
                return length,raw.hex().upper(),'(unknown reserved extension encoding)'
            name=('EXTS','EXTP','EXTSR','EXTPR')[mode]
            return length,raw.hex().upper(),f'{name} #0x{value:X},#{count}'
        if opcode in (0x0a,0x1a):
            address=self.cbitoff(f'{raw[1]:08b}')
            mask,value=(raw[2],raw[3]) if opcode==0x0a else (raw[3],raw[2])
            return length,raw.hex().upper(),f'{"BFLDL" if opcode==0x0a else "BFLDH"} {address},#0x{mask:02X},#0x{value:02X}'
        bits=''.join(f'{x:08b}' for x in raw[1:]);text='(unknown encoding)'
        for rx,expression in zip(self.cpatt.get(opcode,[]),self.cout.get(opcode,[])):
            match=rx.fullmatch(bits)
            if match:
                groups=list(match.groups())+[None]*4
                text=interpret(expression,self._namespace(groups))
                if 'INCOMPLETE' in text:text='(unknown incomplete table entry)'
                break
        text=re.sub(r'\bCC_','',text)
        return length,raw.hex().upper(),text

    def decode_range(self,buf,base_ea,length):
        if type(length) is not int or not 0<=length<=len(buf) or not 0<=base_ea<=0xffffff or base_ea+length>(0x40000 if self.cpu=='80c166' else 0x1000000):
            raise ValueError('Invalid decode range.')
        selected=bytes(buf[:length]);rows=[];off=0
        while off<length:
            count,raw,text=self.decode_one(selected,off,base_ea+off)
            rows.append((base_ea+off,raw,text));off+=count
        return rows
