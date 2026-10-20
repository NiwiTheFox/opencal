# Bundled C166/C167 code workspace

Open a copied BIN or project, then choose **C166 / C167** at the far right of the workbench header. It opens a separate listing and source editor sharing the current project bytes. Nothing is exported by opening or assembling code.

## Configure addresses first

**Memory segments** maps file offsets to 24-bit CPU addresses. Each entry has `file`, `cpu` and `size`. The selected 80C166 assembler/decoder limits code addresses to 0..0x3FFFF; C167/C167CS use the 24-bit range. The initial mapping uses CPU origin zero, explicitly an unverified assumption. Configure the actual runtime addresses from independent ECU evidence before making a code patch. A patch must fit within one segment. Overlapping file/CPU segments are refused; map one bank at a time if the ECU reuses an address window.

The listing shows file offset, CPU address, raw bytes, instruction, direct target, label and comment. Enter an aligned file offset and 1..8192 decode bytes. Select a direct branch/call and use **Follow branch**; **Back** returns to a previous view. Search and references cover only the current decoded range. Indirect branches and DPP-dependent data addresses remain unresolved. **Patch at selection** copies the selected row's file offset to the patch target.

Red rows are unknown, reserved or truncated encodings. Linear decoding can interpret calibration/data bytes as plausible instructions; a successful decode is not evidence that the region executes. SFR operands use encoded `SFR16[0xNN]` / `SFR8[0xNN]` notation because EXTR/CP context has not been recovered. Bit addresses and GPR names are encoded operands, not a proof of physical RAM state. The decoder handles a broad C166/C167 table subset; additional C167CS instructions can remain unknown. Selecting 80C166 explicitly rejects the C167 extension forms.

## Assemble and preview

Choose the CPU, file offset and maximum patch capacity (up to 65536 bytes). Write instructions and labels in the source pane, then **Assemble → preview**. Example:

```asm
start: mov r3,#01234h
       jmpr uc,start
```

The workspace supplies CPU and runtime origin. Instructions may be indented or unindented. Labels use a trailing colon; comments start with `;`. Named condition codes use `uc`, `z`, `nz`, etc. Optional `ASSUME DPP0:020h,...` accepts literal page values; these are assembler assumptions rather than recovered CPU state. DB/DW accept literal byte/word values only. File includes, macros, user ORG/CPU/sections, holes and arbitrary directives are refused. EXTP/EXTPR immediate pages must be literal 0..0x3FF; this independently prevents the upstream assembler's accepted-but-truncated 0x400 case.

OpenCal runs its pinned bundled AS tools with hidden consoles, argument lists, a fresh temporary directory and timeouts. Before conversion, it checks object CPU/section/granularity and exact contiguous address coverage. Oversize output, holes, overlaps, missing symbols and invalid instruction ranges fail without changing the project. The preview shows before/after bytes and a decoded result. It is a bounded overwrite, not an insertion or relocation tool.

**Apply** checks the active project, source hash, CPU, mapping, address/capacity, input hash and original bytes. Apply creates one shared Undo operation and updates the main hex/map views. Changing any preview input requires a new review. Checksum correction and export remain separate. Existing BINs and projects cannot be overwritten by source export; source saves use new `.asm`, `.s` or `.txt` files.

Assembly source, labels, comments, CPU and mapping save inside `.ocproj`; binary patch history uses the existing shared Undo/Redo history. Older projects without code metadata still load. Source changes make the project unsaved even before a byte patch is applied.

## Engines and validation

Disassembly derives from GPL Hajo Noerenberg/Kristof tables, with OpenCal fixes and an AST whitelist interpreter instead of runtime eval. Upstream sources/notices remain in `third_party/c166-dis`. Assembly bundles official flamewing AS 1.42 Beta build 313 (`asw.exe`, `p2bin.exe`) and exact corresponding source/build/license materials in `third_party/asl`. Neither IDA nor Ghidra/Java is required.

Tests compare independent synthetic encoding/operand vectors, reject reserved bits and truncated input, exercise segment-wrap branches, and sweep 65536 first-two-byte combinations for decoder bounds/robustness. Wrapper tests cover 34 probes, including four assembler rejections and independent rejection of EXTP overflow. Tk tests cover previews, stale inputs/projects, Undo/Redo, saved metadata, listener cleanup and button visibility at the minimum window size. A 100-image private corpus pass decoded 139041 rows and exercised a bounded in-memory NOP patch/Undo with synthetic CPU mappings; copies remained unchanged. That is byte-level robustness evidence, not ECU execution validation.

Vehicle operation, complete C16x instruction validity, automatic DPP/EXT state recovery and working ECU map switching remain unverified. Native inspection in this development session hit a Windows app-approval timeout; widget/layout tests passed. No clean Windows VM check is claimed.
