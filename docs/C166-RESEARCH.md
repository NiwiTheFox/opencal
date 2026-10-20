# C166/C167 engines for OpenCal

Research date: 20 October 2026. Scope: an offline GPL-3.0-only Windows Python/Tk application; no user firmware or USB files were read. Findings come from checked-out source, license notices, the processor manual, and synthetic assembly probes. All research checkouts and probe files are under `work/c166-research`; OpenCal source was not modified.

## Recommendation

**Bundle the official flamewing AS Windows x64 `asw.exe` and `p2bin.exe` for assembly. Use a bounded Python decoder for disassembly, retaining GPL3 attribution if derived from Hajo's tables. Do not ship the current Python plugin unchanged.** The downloaded AS tools ran here without installation and reproduced the complete upstream C166 fixture byte for byte. AS's included `dasl.exe` is **not** a C166 disassembler: its source initializes only the 6800, 87C800 and 4004 decoder families, and its CPU listing has no C166. [AS disassembler source](https://github.com/flamewing/asl-releases/blob/592c5fa57b874266bfb625aedaa5197fcd09cec1/das.c)

### Exact assembler to pin

| Item | Inspected value |
| --- | --- |
| Project | [flamewing/asl-releases](https://github.com/flamewing/asl-releases), the actively maintained project referenced by Clownacy's fork |
| Release | [`snapshot-v1.4.2.20261014-run38518630251`](https://github.com/flamewing/asl-releases/releases/tag/snapshot-v1.4.2.20261014-run38518630251) |
| Source commit | `592c5fa57b874266bfb625aedaa5197fcd09cec1` |
| Exact source archive | [commit source ZIP](https://github.com/flamewing/asl-releases/archive/592c5fa57b874266bfb625aedaa5197fcd09cec1.zip), also checked out locally in `work/c166-research/asl-release-source` |
| Actual engine version | AS 1.42 Beta, build 313; CMake project 1.42.313 |
| Windows package | [official x86_64 ZIP](https://github.com/flamewing/asl-releases/releases/download/snapshot-v1.4.2.20261014-run38518630251/asl-windows-x86_64-v1.4.2.20261014-run38518630251.zip) |
| ZIP SHA256 | `c5352406bceabf76a06fc5edbc7adc9fb00a0d0a8e221aa43308ca3c4d6e4302` |
| `asw.exe` SHA256 | `95e7b654977971a479631db55720edeb75aa483dde441ffc30c24169809c124a` |
| `p2bin.exe` SHA256 | `a874c5aabe1abd6b1d3530a49b6d7ad03a8bedca9a9356d94a0fc15743726256` |

Version comes from [version.c](https://github.com/flamewing/asl-releases/blob/592c5fa57b874266bfb625aedaa5197fcd09cec1/version.c); release metadata was retrieved from GitHub's public releases API without credentials. The release tools are available locally in `work/c166-research/asl-windows`. Their PE imports were inspected with Microsoft's `dumpbin`: only KERNEL32 and Windows UCRT API DLLs, no MinGW/MSYS DLLs. Message catalogs are embedded in this release. This establishes a practical Windows 10/11 distribution route; it is not a clean-VM compatibility test. [Build and embedded-message configuration](https://github.com/flamewing/asl-releases/blob/592c5fa57b874266bfb625aedaa5197fcd09cec1/CMakeLists.txt)

### Assembly integration

Run the absolute bundled executable paths with an argument list, `shell=False`, hidden console, timeout and captured output. Work in a fresh temporary directory. A source fragment must begin with the correct processor and **runtime origin**, for example:

```asm
        cpu 80c167
        org 080000h
start:  nop
        mov r3,#01234h
        jmpr uc,start
```

Tested command shape:

```text
asw.exe patch.asm -o patch.p -q -gnuerrors -n
p2bin.exe patch.p patch.bin -q
```

Alternatively pass `-cpu 80c167` instead of a CPU directive. Conditions are `uc`, `z`, `nz`, etc.; `CC_UC`/`CC_Z` from the Python disassembler are not accepted. AS supports `80C166`, `80C167` and `80C167CS`; pick the actual target. Use `ASSUME DPP0:...,DPP1:...,DPP2:...,DPP3:...` when assembling physical data addresses that need DPP translation. EXTS/EXTP sequences also influence AS address translation. The defaults are DPP0..3 = 0..3; they are assembler assumptions, not recovered firmware state. [C166 backend, conditions, assumptions and prefix handling](https://github.com/flamewing/asl-releases/blob/592c5fa57b874266bfb625aedaa5197fcd09cec1/code166.c)

For an in-place patch, require successful assembler and converter exit status, exact output size, contiguous expected address coverage, and no bytes outside the requested region. Reject unexpected origins/sections and directives that introduce holes; `p2bin` can fill gaps, so output length alone is insufficient. Prefer explicit `JMPR`, `JMPA`, `JMPS`, `CALLR`, `CALLA`, `CALLS` when encoding must remain stable; generic `JMP`/`CALL` select forms. Show assembled bytes and a diff before applying. Treat assembly text as a local file-reading language because of `INCLUDE`; a restricted fragment editor should allow only the needed instruction/directive subset. These are integration recommendations, not functionality supplied by the engines. [AS command and output documentation](https://github.com/flamewing/asl-releases/blob/592c5fa57b874266bfb625aedaa5197fcd09cec1/doc/assembler-usage.md)

**Observed AS range caveat:** `extp #0400h,#1` succeeds and emits `D7 40 00 00`, truncating the page to zero. OpenCal must independently constrain EXTP/EXTPR immediate pages to 0..0x3FF rather than relying solely on AS exit status. The test fixture records this accepted-but-truncated case explicitly.

### Build route

The pinned source uses C11 and CMake >=3.19, supports Visual Studio 2022, and embeds messages by default. Upstream's MSVC workflow configures with `cmake -S . -B build -A x64 -G "Visual Studio 17 2022"`, then builds Release. Build on a developer/CI machine and bundle the results; users need no compiler. Source and CI references: [CMakeLists](https://github.com/flamewing/asl-releases/blob/592c5fa57b874266bfb625aedaa5197fcd09cec1/CMakeLists.txt), [MSVC CI](https://github.com/flamewing/asl-releases/blob/592c5fa57b874266bfb625aedaa5197fcd09cec1/.github/workflows/ci-windows-msvc.yml).

Local discovery found MSVC 14.44.35207, bundled CMake 3.31.6 and Ninja under Visual Studio BuildTools. A source configure attempt failed because this sandbox denies MSBuild access to `AppData/Local/Microsoft SDKs`; **a local source rebuild is not claimed**. The public release binaries were successfully executed and tested.

## Tested encoding evidence

The pinned release assembled upstream [`tests/t_166/t_166.asm`](https://github.com/flamewing/asl-releases/blob/592c5fa57b874266bfb625aedaa5197fcd09cec1/tests/t_166/t_166.asm), using its `include` directory. `p2bin` produced 3,298 bytes with SHA256 `99e02818e6bda8f93f53f26f780f7f635c6636b790c1c658da1a2aef4a6c3e4a`, identical to upstream `t_166.ori`. This is regression evidence, not a proof of every hardware encoding.

A separate synthetic probe at origin `0x80000` produced:

| Address | Source | Encoded bytes |
| --- | --- | --- |
| 080000 | `nop` | `CC 00` |
| 080002 | `mov r1,r2` | `F0 12` |
| 080004 | `mov r3,#01234h` | `E6 F3 34 12` |
| 080008 | `movb rl1,#056h` | `E7 F2 56 00` |
| 08000C | `jmpr uc,080000h` | `0D F9` |
| 08000E | `jmpa z,080020h` | `EA 20 20 00` |
| 080012 | `jmps 08h,01234h` | `FA 08 34 12` |
| 080016 | `calls 08h,05678h` | `DA 08 78 56` |
| 08001A | `exts #08h,#1` | `D7 00 08 00` |
| 08001E | `mov r4,080100h` after EXTS | `F2 F4 00 01` |
| 080022 | `extp #020h,#4` | `D7 70 20 00` |
| 080026 | `mov r5,080102h` after EXTP | `F2 F5 02 01` |
| 080030 | `extr #1` | `D1 80` |
| 080036 | `atomic #4` | `D1 30` |
| 080040 | `bfldl 0ff00h,#0c3h,#03ch` | `0A 80 C3 3C` |
| 080044 | `trap #7` | `9B 0E` |
| 080046 | `ret` | `CB 00` |
| 080048 | `reti` | `FB 88` |
| 08004A | `rets` | `DB 00` |

Local reproducible files: `work/c166-research/probe.asm`, `probe.lst`, `probe.bin`, `upstream-t166.bin`. The integration fixture `work/c166-research/c166-as-fixtures.json` contains 34 synthetic assembly cases: 30 successful encodings and four expected rejections (relative offsets below -256/above +254 bytes, odd relative target, zero extension count). It includes DPP/EXTS/EXTP address-resolution cases, bit RAM/SFR/GPR cases, page truncation, fixed-bit/truncation decoder rejection inputs, and a separately labeled manual-derived IP-wrap case. Reproduce using `work/c166-research/make_fixture.py`.

## Disassembler findings and traps

The inspected [Python plugin](https://github.com/ayyo42069/c166-disasm-plugin/blob/35d4488ee6b35d246dfc0dc87e0667b385f9d43e/c166_disasm.py) is commit `35d4488ee6b35d246dfc0dc87e0667b385f9d43e`. Its three tables are byte-for-byte identical to [Hajo Noerenberg's original](https://github.com/hn/c166-dis/tree/31b605362ac55b2710b8c87a29e83ba73b18899b), commit `31b605362ac55b2710b8c87a29e83ba73b18899b`; original program identifies itself as V0.2 ALPHA. Tables cover 236 first-byte opcodes and 275 pattern forms. This is useful breadth, not validated completeness.

Source inspection and synthetic probes found these concrete problems:

- `eval` executes translated expressions from a configurable table directory. Empty builtins do not make arbitrary expressions safe. Parse only a fixed whitelist of literal strings, concatenation, named helpers and A-D captures, or convert the tables once into typed operands. Do not evaluate table text at runtime.
- `irang2` prints raw bits 0..3, missing the +1 conversion. Thus valid `D7 00 08 00` prints `EXTS #0x08,#0` instead of `#1`; `D1 30` prints `ATOMIC #3` instead of `#4`.
- Immediate EXTP/EXTPR forms are explicitly incomplete and incorrectly render an R-register. Their regex checks only the first operand byte, accepting invalid fixed bits and unused trailing values. Require full-pattern matches and correct page-width constraints.
- BFLDH/BFLDL and TRAP contain unfinished helpers. BFLDL also swaps mask/data captures: `0A 80 C3 3C` ends in printed data `#0xC3`, whereas the assembled instruction uses data `#0x3C`. BFLDH intentionally has the opposite byte order from BFLDL: AS assembles `bfldh 0fd02h,#03ch,#0c3h` as `1A 01 C3 3C`; do not apply a shared mask/data byte order to both opcodes.
- Bit addresses reuse ordinary SFR register decoding incorrectly: `0F 00` prints `BSET DPP0.0`; it refers to bit-addressable RAM at `0xFD00.0`. Apply separate bit-address rules and EXTR context. [Independent MIT SLEIGH bit-address implementation](https://github.com/keyhana/c166-ghidra-module/blob/6a579b9a6f594fb53250e5e43a9af6b27ebf216c/data/languages/c166.sinc)
- Truncated input is returned as a nominal two-byte instruction with only one actual byte. `decode_range(..., length=2)` can return all four bytes of a four-byte instruction when its buffer is longer. Check both selected-range bounds and buffer bounds before decoding.
- Relative targets use an unbounded flat addition. At EA `0x8FFFE`, bytes `0D 01` print `0x90002`; preserve CSP while wrapping 16-bit IP. Absolute JMPA output is only `0x0020`, losing useful CSP context.
- No DPP or extended addressing state is tracked. Direct `0x0100` after EXTS #8 is not a resolved physical address. Keep encoded operands visible; resolve references only with known DPP/CSP/override state, and show unknown when state is absent.

These defects are present in source, not speculative warnings. Feeding the complete 3,298-byte AS fixture through the Python decoder produced 1,390 rows including 55 explicitly incomplete/unknown/error rows; successful-looking rows were not all independently validated. A sweep of all two-byte candidates for its two-byte opcode families exercised 35,328 cases without exceptions, but included 128 incomplete TRAP outputs; this is robustness coverage only.

The authoritative [Infineon C166 Instruction Set Manual V2.0, March 2001](https://www.keil.com/dd/docs/datashts/infineon/c166ism.pdf) defines NOP as `CC 00` (printed p.105), BFLDL order as opcode/bit-offset/mask/data (p.53), extension range as 1..4 (p.138), and EXTP/EXTS addressing behavior (pp.78-85,137). Relative branches change IP within CSP (p.139); direct code addresses need CSP context. DPP translation uses the selected page and low fourteen address bits; EXTS uses a segment and full sixteen-bit offset. Validate fixed bits and processor-specific availability, not just the first opcode byte.

The [MIT Ghidra module](https://github.com/keyhana/c166-ghidra-module/tree/6a579b9a6f594fb53250e5e43a9af6b27ebf216c), commit `6a579b9a6f594fb53250e5e43a9af6b27ebf216c`, has SLEIGH definitions plus Java context analyzers. It is a useful independent reference, but bundling it as the engine adds Ghidra/Java infrastructure. Its source has a separate context counter and register/page/segment modes. It was not built or runtime-tested here. [Definition](https://github.com/keyhana/c166-ghidra-module/blob/6a579b9a6f594fb53250e5e43a9af6b27ebf216c/data/languages/c166.sinc)

## License and redistribution decision

- **AS:** inspected C166 backend, core and all 436 C/header files with SPDX notices specify `GPL-2.0-only OR GPL-3.0-only`. Select GPL-3.0-only for the bundle; preserve notices, provide GPLv3 text, pin the exact source and supply corresponding source/build instructions with binary distribution. The package's `COPYING` is GPLv2 and README badge says GPLv2; do not infer incompatibility from the badge or silently replace original notices. Add an explicit distribution note recording the GPL3 choice. This is a source-based compatibility assessment, not a provenance audit of every historical contribution. [C166 license notice](https://github.com/flamewing/asl-releases/blob/592c5fa57b874266bfb625aedaa5197fcd09cec1/code166.c), [GPLv3 source obligations](https://www.gnu.org/licenses/gpl-3.0.html#section6)
- **Hajo/Python:** original Perl source explicitly grants GPL version 3.0; Python header says its port follows GPL-3.0. Compatible with OpenCal's GPL-3.0-only when notices and corresponding source are supplied. Retain both Hajo and port author attribution if using their code. Tables lack individual license headers; they travel with the original GPL program and the port expressly reuses them. Preserve provenance instead of claiming new ownership. [Original grant](https://github.com/hn/c166-dis/blob/31b605362ac55b2710b8c87a29e83ba73b18899b/c166-dis.pl), [port notice](https://github.com/ayyo42069/c166-disasm-plugin/blob/35d4488ee6b35d246dfc0dc87e0667b385f9d43e/c166_disasm.py)
- **Ghidra module:** its [LICENSE](https://github.com/keyhana/c166-ghidra-module/blob/6a579b9a6f594fb53250e5e43a9af6b27ebf216c/LICENSE) grants MIT, copyright 2024 Keyhan Asadi; retain the license if deriving code from its implementation. MIT permits incorporation into a GPL3 application. This module's MIT license does not license the whole Ghidra distribution.
- **TPASM:** commit `35ff0711532c71f3657d4ca972488a1dfdf10884`, release V1.12. [LICENSE.TXT](https://github.com/SuperIlu/TPASM/blob/35ff0711532c71f3657d4ca972488a1dfdf10884/LICENSE.TXT) is GPLv2; inspected backend refers to this license without an explicit later-version grant. Do not assume GPL3 permission for incorporation into OpenCal. Separate executable aggregation may be possible, but requires its own GPLv2 compliance. Its [C166 limitations](https://github.com/SuperIlu/TPASM/blob/35ff0711532c71f3657d4ca972488a1dfdf10884/README_C166.TXT) include no pipeline/protected-sequence checks and a single generic C166 target. It was not run; AS is better supported by the evidence here.
- **Clownacy fork:** inspected commit `c09c45a09c2bb043c43c327aa83016bdd184218f`, build 212, same dual-license backend. Its public latest-release API returned 404, while flamewing supplied current verified Windows binaries. Prefer the pinned flamewing release above. [Clownacy backend](https://github.com/Clownacy/asl-releases/blob/c09c45a09c2bb043c43c327aa83016bdd184218f/code166.c)

No proprietary assembler/disassembler binary was executed. No external account credentials were used. No source was published. Remaining release checks: clean Windows VM smoke test, full decoder validity tests against selected C167 variant, and inclusion of exact corresponding-source/license materials in the downloadable OpenCal distribution.
