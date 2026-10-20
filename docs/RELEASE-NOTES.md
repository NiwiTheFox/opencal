# OpenCal 1.0.0 — Bundled C166/C167 workspace

Development preview. Extract the complete Windows ZIP and run OpenCal.exe. Python, Tcl/Tk, the decoder and AS assembler tools are included; no separate installation is required.

## Changes

- Add a far-right **C166 / C167** launcher opening a separate mapped disassembly and source workspace.
- Display file/CPU addresses, raw bytes, instructions, direct branches, labels and comments. Add range navigation, search, branch follow/back and current-range references.
- Bundle a hardened GPL decoder and official pinned AS assembler/converter with corresponding source, licenses and build instructions. Fix MOVBS/MOVBZ operand types, extension counts/pages, bit addresses, bitfield order, TRAP, fixed-pattern validation, range truncation and segmented relative targets.
- Assemble source to a checked contiguous output preview, then apply a bounded overwrite with project/byte/hash/source/mapping guards and one shared Undo operation. Main views update live. Separate checksum correction and BIN export are retained.
- Save source, CPU, segments and notes inside projects; older projects remain compatible. Keep all 0.9.1 expanded EDC15 layout/checksum/map/DTC features.

## Validation

133 source tests and GUI smoke passed (two environment/private-only checks skipped). C166 tests cover independent encoding/operand fixtures, 34 assembly probes including expected rejection cases, all 65536 first-two-byte combinations for robustness, source restrictions, exact object address coverage, bounds/stale-preview guards, Undo/Redo, project persistence and minimum-window controls. A separate 100-image copied corpus check decoded 139041 rows and applied/undid bounded synthetic NOP patches entirely in memory. No firmware copies were changed on disk. Bundled/runtime and published-download checks are also performed during release.

## Known issues and limits

- ECU execution and map switching are unverified. Do not infer runnable code from linear decoding. CPU segments are explicit user assumptions; initial origin is zero.
- DPP/EXT/CP-dependent physical data references and indirect control flow are unresolved. Some C167CS/other C16x forms remain unknown. A robustness sweep does not prove all decoder outputs correct.
- Assembly supports restricted source fragments rather than whole projects, includes/macros, relocation or insertion. DB/DW accept literal values only. Patches are aligned, bounded overwrites and require a mapped CPU segment.
- EDC15 support remains feature/layout-specific; complete P/P+/P++ coverage is not claimed. Early checksums/DTCs, compact ORI relocation and some solutions remain unavailable. See SUPPORT.md.
- Windows x64 requires the complete folder. No clean-VM or physical ECU test is claimed. Native visual inspection hit an app-approval timeout; automated widget and layout checks passed.

See C166-WORKSPACE.md for operation and source/license provenance. New feature releases follow 1.x.0; quick fixes follow 1.0.x (and the corresponding patch series for later feature releases).
