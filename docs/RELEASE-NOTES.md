# OpenCal 0.9.0 — Bounded EGR solution

Development preview. Extract the complete Windows ZIP and run OpenCal.exe. Python and Tcl/Tk are included; no installer or paid dependency is needed.

## What changed

- Solutions now includes Disable EGR for the checked standard EDC15P 038906019FJ / Bosch 0281010789 / SG 1376 layout.
- The source-backed strategy sets each supported EGR fresh-air request map to 850 mg/st (8500 raw, little-endian u16). It also disables the four EGR-related codes present in that layout: P3131, P3130, P1402 and P1441, across every matching bank.
- Support requires matching embedded identifiers, bounded 16 × 13 axis headers, plausible ordered RPM/IQ axes, request-value ranges and the complete expected EGR diagnostic layout in every bank. One incompatible bank refuses the entire operation.
- Preview lists the map ranges, codeblock IDs, all affected diagnostics and exact before/after bytes. Apply is one undo operation; repeat application is a no-op.
- Restore loaded original restores the exact input map and monitoring bytes. It does not invent factory settings when the input was already modified.
- Solutions is scrollable, review dialogs open centred over the workbench, and stale launch-control previews reject applying to a replaced project.
- All 0.8 comparison features are retained: codeblock/category groups, aligned side-by-side maps, a lighter read-only reference pane, controls that wrap in narrow panes, live shared edits and undo/redo.
- GPL VAGEDCSuite source used for the map-target strategy and saved byte-order convention is retained with license, revision and hashes. Proprietary reference-app code/data is not bundled.

## Validation

100 source tests passed (one portable-runtime-only check skipped); all 100 tests passed in the bundled runtime, plus GUI smoke. Native inspection confirmed the EGR preview, in-memory apply and one-step Undo returning to zero changed bytes. It exposed a partly off-screen review dialog; centred placement and a mapped-window regression check now cover that case. Added tests cover all map cells and EGR records, preservation of every unrelated byte, all-bank application, complete refusal of a bad bank, identity/header/value/diagnostic guards, repeat application, stale previews, replaced projects, exact original restoration and undo/redo. On the copied ORI, the supported checksum correction still produces matched checksums after the EGR record changes. Both private firmware copies remain unchanged on disk.

The supplied ORI already has its identified request table flat at 850 mg/st; its four related DTC records are enabled. V9 has the same target in three banks and all twelve related records already disabled. Therefore the normal ORI operation changes diagnostics only, and V9 requires no changes. Synthetic non-flat tables exercise the actual 208-cell-per-bank map transformation. These observations do not establish factory originality or vehicle EGR behaviour.

## Known issues and limits

- EGR automation is limited to the exact FJ / 1376 profile above. Other software, ECU families, early/compact layouts and different diagnostic layouts are refused. A future profile needs separate identification and validation.
- The 850 mg/st strategy is ported from GPL source and tested at byte level. Physical EGR operation and vehicle execution have not been validated. It is not a general EGR code patch or proof that every activation condition is disabled.
- EGR temperature and hysteresis maps are deliberately not overwritten by a name search. Only the checked request map and explicitly identified related records are edited.
- Restoring a tuned input's original bytes may retain its existing EGR modifications. A DTC stock reference is separate from the solution's exact loaded-original restore.
- Checksum correction and export remain separate actions. Unsupported or invalid checksum baselines cannot be treated as verified.
- C166/C167 disassembly/assembly and ECU multimap switching are not implemented in this release. Research and independent assembler fixtures are prepared for the next milestone.
- Map matching is currently checked standard V4.1 EDC15 or explicit synthetic fixtures. Unknown map layouts remain unmatched; hex comparisons use raw file offsets. The delta tab shows at most 4,096 cells plus axes while counts cover the full map.
- Arbitrary rectangular table paste is not implemented; 3D plots use indexed spacing and nonmonotonic interpolation uses index spacing. Very large files/many comparison windows can make recalculation slower.
- Windows builds are 64-bit, need the entire extracted folder, and have not been tested in a clean Windows VM.
