"""C167 emulator verified against code assembled by the bundled AS assembler.

Expected values come from the C166 instruction-set semantics (Infineon ISM),
computed by hand, not from the emulator.
"""
import unittest

from opencal.core.asm166 import AsmError, assemble
from opencal.core.c167 import F_C, F_N, F_V, F_Z, C167, EmuError

ORG = 0x80000


def run(src, regs=None, setup=None, flash=None):
    code = assemble(src, ORG)
    image = bytearray(flash or b"\xff" * 0x80000)
    image[:len(code)] = code
    cpu = C167(bytes(image))
    if setup:
        setup(cpu)
    cpu.call(ORG, regs or {})
    return cpu


class Arithmetic(unittest.TestCase):
    def test_add_carry_zero(self):
        c = run("mov r1,#0FFFFh\n add r1,#1\n rets")
        self.assertEqual(c.R(1), 0)
        self.assertTrue(c.flag(F_C) and c.flag(F_Z))

    def test_add_signed_overflow(self):
        c = run("mov r1,#7FFFh\n add r1,#1\n rets")
        self.assertEqual(c.R(1), 0x8000)
        self.assertTrue(c.flag(F_V) and c.flag(F_N))
        self.assertFalse(c.flag(F_C))

    def test_sub_borrow(self):
        c = run("mov r2,#5\n sub r2,#6\n rets")
        self.assertEqual(c.R(2), 0xFFFF)
        self.assertTrue(c.flag(F_C) and c.flag(F_N))

    def test_addc_subc_32bit(self):
        # 0x0001FFFF + 0x00000001 = 0x00020000 using ADD/ADDC
        c = run("mov r1,#0FFFFh\n mov r2,#1\n add r1,#1\n addc r2,#0\n rets")
        self.assertEqual((c.R(2), c.R(1)), (2, 0))

    def test_logic(self):
        c = run("mov r1,#0F0F0h\n and r1,#0FF00h\n mov r2,#00F0h\n or r2,#000Fh\n mov r3,#0FFFFh\n xor r3,#00FFh\n rets")
        self.assertEqual((c.R(1), c.R(2), c.R(3)), (0xF000, 0x00FF, 0xFF00))

    def test_byte_ops_and_regs(self):
        c = run("mov r4,#1234h\n movb rl4,#0FFh\n addb rh4,#1\n rets")
        self.assertEqual(c.R(4), 0x13FF)

    def test_movbz_movbs(self):
        c = run("movb rl1,#80h\n movbz r2,rl1\n movbs r3,rl1\n rets")
        self.assertEqual((c.R(2), c.R(3)), (0x0080, 0xFF80))

    def test_neg_cpl(self):
        c = run("mov r1,#5\n neg r1\n mov r2,#0F0Fh\n cpl r2\n rets")
        self.assertEqual((c.R(1), c.R(2)), (0xFFFB, 0xF0F0))

    def test_mul_div(self):
        c = run("mov r1,#300\n mov r2,#400\n mulu r1,r2\n mov r3,0FE0Eh\n mov r4,0FE0Ch\n rets")
        self.assertEqual((c.R(4) << 16) | c.R(3), 120000)
        c = run("mov r1,#0FFF6h\n mov 0FE0Eh,r1\n mov r2,#3\n div r2\n mov r3,0FE0Eh\n mov r4,0FE0Ch\n rets")   # -10 / 3
        self.assertEqual((c.R(3), c.R(4)), (0xFFFD, 0xFFFF))   # -3 rem -1
        c = run("mov r1,#1\n mov 0FE0Ch,r1\n mov r1,#86A0h\n mov 0FE0Eh,r1\n mov r2,#1000\n divlu r2\n mov r3,0FE0Eh\n rets")   # 100000/1000
        self.assertEqual(c.R(3), 100)

    def test_shifts(self):
        c = run("mov r1,#8001h\n shl r1,#1\n mov r2,#8001h\n shr r2,#1\n mov r3,#8000h\n ashr r3,#3\n"
                " mov r4,#8001h\n rol r4,#4\n mov r5,#8001h\n ror r5,#4\n rets")
        self.assertEqual([c.R(i) for i in range(1, 6)], [0x0002, 0x4000, 0xF000, 0x0018, 0x1800])

    def test_cmpi_loop(self):
        c = run("mov r1,#0\n mov r2,#0\nl1: add r2,#3\n cmpi1 r1,#4\n jmpr ne,l1\n rets")
        self.assertEqual((c.R(1), c.R(2)), (5, 15))


class Branches(unittest.TestCase):
    def _cond(self, a, b, cc):
        c = run(f"mov r1,#{a}\n mov r3,#0\n cmp r1,#{b}\n jmpr {cc},yes\n rets\nyes: mov r3,#1\n rets")
        return c.R(3) == 1

    def test_unsigned_and_signed_conditions(self):
        self.assertTrue(self._cond("5", "3", "ugt"))
        self.assertFalse(self._cond("3", "5", "ugt"))
        self.assertTrue(self._cond("0FFFFh", "1", "ugt"))     # 65535 > 1 unsigned
        self.assertTrue(self._cond("0FFFFh", "1", "slt"))     # -1 < 1 signed
        self.assertTrue(self._cond("3", "3", "eq"))
        self.assertTrue(self._cond("3", "3", "ule"))
        self.assertTrue(self._cond("2", "3", "ult"))
        self.assertTrue(self._cond("4", "3", "sge"))
        self.assertFalse(self._cond("3", "4", "sgt"))

    def test_calls_and_returns(self):
        src = ("mov r1,#1\n callr f1\n calls 08h,f2 & 0FFFFh\n db 0CAh,00h\n dw f1 & 0FFFFh\n rets\n"
               "f1: add r1,#10\n ret\n"
               "f2: add r1,#100\n rets")
        c = run(src)
        self.assertEqual(c.R(1), 121)   # f1 twice (CALLR, CALLA) + f2

    def test_push_pop_stack(self):
        c = run("mov r1,#1111h\n mov r2,#2222h\n push r1\n push r2\n pop r1\n pop r2\n rets")
        self.assertEqual((c.R(1), c.R(2)), (0x2222, 0x1111))

    def test_jmpi_table(self):
        c = run("mov r4,#(tgt & 0FFFFh)\n jmpi uc,[r4]\n mov r1,#1\n rets\ntgt: mov r1,#2\n rets")
        self.assertEqual(c.R(1), 2)


class Memory(unittest.TestCase):
    def test_dpp_paging(self):
        # DPP0 = page 0x3C (CPU 0xF0000): read a word from flash at 0xF0010 via address 0x0010
        flash = bytearray(b"\xff" * 0x80000)
        flash[0x70010:0x70012] = (0xBEEF).to_bytes(2, "little")
        c = run("db 0E6h,00h,3Ch,00h\n assume dpp0:3Ch\n mov r1,0010h\n rets", flash=flash)   # MOV DPP0,#3Ch
        self.assertEqual(c.R(1), 0xBEEF)
        self.assertIn(0x3C, c.flash_reads)

    def test_extp_and_exts(self):
        flash = bytearray(b"\xff" * 0x80000)
        flash[0x70100:0x70102] = (0x1357).to_bytes(2, "little")
        flash[0x50200:0x50202] = (0x2468).to_bytes(2, "little")
        c = run("extp #3Ch,#1\n mov r1,0100h\n exts #0Dh,#1\n mov r2,0200h\n mov r3,#0\n rets", flash=flash)
        self.assertEqual((c.R(1), c.R(2)), (0x1357, 0x2468))

    def test_extp_count(self):
        # EXTP #pag,#1 applies to exactly one following instruction
        flash = bytearray(b"\xff" * 0x80000)
        flash[0x70000:0x70002] = b"\x11\x11"
        def setup(cpu):
            cpu.wsfr(0xFE00, 3)           # DPP0 -> page 3 (RAM 0xC000)
            cpu.mem[0xC000:0xC002] = b"\x22\x22"
        c = run("extp #3Ch,#1\n mov r1,0000h\n mov r2,0000h\n rets", flash=flash, setup=setup)
        self.assertEqual((c.R(1), c.R(2)), (0x1111, 0x2222))

    def test_indirect_modes(self):
        def setup(cpu):
            cpu.mem[0xF600:0xF606] = bytes([1, 0, 2, 0, 3, 0])
        c = run("mov r4,#0F600h\n mov r1,[r4+]\n mov r2,[r4+]\n mov r3,[r4]\n mov r5,[r4-4]\n"
                " mov r6,#0F700h\n mov [-r6],r3\n mov r7,0F6FEh\n rets", setup=setup)
        self.assertEqual([c.R(i) for i in (1, 2, 3, 5, 7)], [1, 2, 3, 1, 3])

    def test_bits(self):
        def setup(cpu):
            cpu.mem[0xFD10] = 0
        c = run("bset 0FD10h.3\n mov r1,0FD10h\n jb 0FD10h.3,set\n mov r2,#0\n rets\n"
                "set: mov r2,#1\n bclr 0FD10h.3\n mov r3,0FD10h\n rets", setup=setup)
        self.assertEqual((c.R(1), c.R(2), c.R(3)), (8, 1, 0))

    def test_bfldl(self):
        c = run("mov r1,#0FFFFh\n mov 0FD20h,r1\n bfldl 0FD20h,#0Fh,#05h\n mov r2,0FD20h\n rets")
        self.assertEqual(c.R(2), 0xFFF5)

    def test_flash_write_is_refused(self):
        with self.assertRaises(EmuError):
            run("db 0E6h,00h,3Ch,00h\n assume dpp0:3Ch\n mov r1,#1\n mov 0000h,r1\n rets")


if __name__ == "__main__":
    unittest.main()
