Implemented 1.0.0: bundled disassembly/source workspace and guarded AS previews. Remaining: broader independent decoder validation, richer analysis, expanded ECU support and separately validated switching logic.

Version policy updated 20 October 2026: 0.9.x maintenance, bundled C166 tools in 1.0.0, subsequent features 1.x.0 and quick fixes 1.0.x.

# OpenCal update roadmap

Agreed scope: 19 October 2026. Starting release: 0.6.1.

Progress: 0.7 published; 0.8 completed and release-tested. 0.9 adds a bounded FJ/1376 EGR solution; additional profiles need evidence. C166/C167 milestones remain pending. The user selected all-bank DTC toggles with individual controls and a read-only comparison file. Comparison maps also use codeblock/category groups and side-by-side editable/read-only panes.

## Working rules

- Work only with fresh local copies under `outputs/to use`, in a subfolder for each BIN. BIN and project names start with `codex`. Do not open or edit USB files in tuning tools.
- Keep each release in its own folder. Publish tested source, portable Windows build, checksums, changelog and known issues to NiwiTheFox/opencal. Bundle all required runtimes and free tools.
- Keep originals immutable, changes reversible and exports separate. Private firmware, customer files and reference exports stay out of GitHub.
- These milestones are development releases. A successful byte-level test does not establish vehicle behaviour.

## 0.7 — English DTCs and clearer controls

- Use the English descriptions already present in the supplied GPL ZedSuite source. Preserve VAG/P-code relationships and translate system categories too. Check coverage rather than silently falling back to French.
- Group by relevant system, then fault code, with expandable codeblock/record details. Search by description, code and codeblock. Offer enabled/disabled filters and counts.
- Each DTC gets a real button displaying its current state. Enabled row text is green; disabled row text is red. Button text stays white, including selection and focus states. Mixed groups get an explicit Mixed state.
- The group button applies to all matching codeblocks. Expanded records allow individual control. Each action is one undoable operation and preserves the scroll position and grouping.
- Re-enabling restores exact known enabled monitoring bytes from the loaded original or a validated matching stock reference. If neither exists, explain what reference is missing; never invent universal monitoring values.
- Keep the DTC display current after unrelated edits, undo and redo; fix the existing disappearing-list issue.
- Verify translation coverage, duplicate records, mixed states, exact restoration, unrelated bytes, undo/redo and native layout/keyboard behaviour.

## 0.8 — Live comparison windows

- Compare BIN opens two independent windows: side-by-side hex and a list/editor of changed maps.
- Both windows edit the active project. The comparison BIN remains read-only. Main-window edits, comparison edits and undo/redo update every view automatically through shared document notifications.
- Hex view has synchronized scrolling, highlighted changed bytes, next/previous difference, address navigation and active-side editing. Handle unequal lengths explicitly without shifting or resizing ECU data.
- Map comparison includes changed table cells and changed axes, with values/units and codeblock identity. Use definitions on the reference side only when compatible; unmatched layouts remain explicitly unmatched.
- Show current/reference/delta values; reuse the existing map editor for active-side editing. A map can also be opened in the main editor.
- Keep the selected map open even when an edit removes its last difference. Preserve selection/scroll and dispose listeners when windows close or the project changes.
- Test edits in every view, undo/redo, stale selections, incompatible files, no-difference files, end-of-file changes and closing/reopening windows.

## 0.9 — EGR solution for verified EDC15P layouts

- Examine fresh local copies of stock `38906019FJ-SG 1376 ori.bin` and tuned `V9 MY CAR 96 DTC Disabled.bin`. V9 has other changes, so their differences are evidence to investigate rather than an EGR-only golden patch.
- Review the GPL VAG Suite EGR map-edit routine, map detection, scaling and final saved byte order. Identify actual EGR request/activation maps; never edit every map containing the word EGR.
- Define supported software/layout profiles with explicit map semantics, addresses/structural anchors, encoding and expected ranges. Unsupported or ambiguous inputs cannot apply an automatic solution.
- Preview all proposed map edits and the explicit list of related DTC records, across matching codeblocks. Show which maps and codes will change and why.
- Apply map and DTC changes as one undoable operation. Support exact restoration and idempotent reapplication. Checksum handling uses only supported algorithms.
- Verify changed ranges against the intended maps/records, preservation of all other bytes, bank consistency, stale previews, undo, export/reload and already-modified inputs. State remaining vehicle validation limits.

## 1.0.0 — C166/C167 disassembler workspace

- Add a far-right `C166 / C167` launcher opening a separate code workspace.
- Include file-offset and CPU-address columns, configurable memory segments/base address, bytes, mnemonics and operands. Do not assume all ECU images have one load address.
- Include address/search navigation, labels/comments saved with the project, follow direct branches/calls, history and cross-references where determinable.
- Represent unknown/truncated instructions and undecidable DPP-dependent addresses explicitly. Do not claim every data region is executable code or every indirect target is resolved.
- Evaluate the free GPL Python C166 decoder against Infineon's instruction manual and a second implementation. The MIT Ghidra C166 module is a useful independent reference; users will not need IDA or Ghidra installed.
- Test valid instruction variants, lengths, reserved encodings, signed relative branches, segment boundaries and EXTP/EXTS/DPP handling. Keep decode coverage visible.

## 1.0.0 — Assembler and guarded code editing

- Evaluate Macro Assembler AS and TPASM C166 support, exact license terms, Windows builds and syntax compatibility. Bundle a suitable free engine; do not require users to install a compiler or assembler.
- Add source editing with labels, origin, instruction/directive errors and an assemble-to-preview action. Show original bytes, assembled bytes and decoded result before applying.
- Patches are bounded overwrites in the active project, with checked original bytes and one undo operation. Reject oversize output, out-of-range branches, unresolved symbols and stale previews.
- Cross-check encoding against documented examples and an independent assembler/decoder. Decode/encode round trips alone are not enough because matching bugs can pass them.
- Preserve code comments, memory configuration and patch history in projects; migrate older projects safely.
- Keep the architecture/patch engine separable for a future dedicated multimap app. ECU map-switching patches remain a later milestone requiring separate evidence and testing.

## Research references

`C166-RESEARCH.md` records completed primary-source research, the recommended AS engine and verified decoder defects; the implementation milestones above remain pending.

- Infineon C166 Family Instruction Set Manual, V2.0: https://www.keil.com/dd/docs/datashts/infineon/c166ism.pdf — instruction encoding, device differences and addressing rules.
- Python C166 decoder candidate: https://github.com/ayyo42069/c166-disasm-plugin — GPL claim in source; standalone decoder without IDA imports is available. Verify source/table provenance before incorporation.
- Independent MIT C166/C167 processor module: https://github.com/keyhana/c166-ghidra-module — DPP/EXT handling, processor definitions and analysis reference.
- Macro Assembler AS candidate: https://github.com/Clownacy/asl-releases — C166 backend and Windows build support; See `C166-RESEARCH.md` for the pinned engine, checked license notices and Windows fixture results.
- TPASM candidate: https://github.com/SuperIlu/TPASM and its README_C166.TXT — C166 assembly syntax and limitations; See `C166-RESEARCH.md` for the pinned engine, checked license notices and Windows fixture results.
- Supplied ZedSuite source: English descriptions in `src/lib/ecu/bosch/dtc/translations/en.ts`, bilingual database and system translation helper. Existing source provenance is recorded in OpenCal's notices.
- Locally reviewed GPL VAG Suite fork: https://github.com/skaldamramra/VAGEDCSuite — `EDC15PTuner.cs` contains an EGR map-edit routine. Its existence is not proof that its strategy applies to every detected map or ECU.

## Release gate for every milestone

Run relevant model and GUI tests, then regress the existing editing/export paths. Check fresh copied firmware remains unchanged on disk, exact undo restoration, project save/reload and portable execution. Inspect native Windows layout, scrolling, focus and resizing. Validate the downloadable GitHub archive and ensure no private inputs are included. Record remaining known issues honestly.
