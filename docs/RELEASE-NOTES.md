# OpenCal 0.7.0 — English DTC workspace

Development preview. Extract the whole Windows ZIP and run OpenCal.exe. Python and Tcl/Tk are included; no installation or account is required.

## What changed

- All 1,776 bundled DTC descriptions and system categories are English, using the supplied GPL ZedSuite English/bilingual sources with complete coverage checks.
- DTCs are grouped by system and fault code. Each code has a real Enabled/Disabled button: enabled row text is green, disabled row text red, and button text stays white. Mixed states are explicit.
- A group button edits all matching codeblocks as one undo operation. Expand a code to inspect and control individual records. Search includes descriptions, P-codes, VAG codes and codeblock labels; state filters and counts are available.
- DTC records stay visible and update after edits, undo and redo. Expansion and scroll position are preserved.
- Load stock DTC reference enables exact restoration for a tuned input already disabled when opened. Embedded ECU/hardware/software IDs, per-bank IDs and whole DTC record topology are checked; ambiguous banks are refused. Loaded-original enabled bytes take priority. No generic enabled monitoring values are guessed.
- The checked reference is retained inside a saved project with an integrity hash. Attaching it marks the project unsaved and never changes calibration bytes.
- A staged roadmap covers live comparison, verified EGR solutions, C166/C167 disassembly and assembly.

## Validation

88 local tests passed (one portable-only test skipped in the source run), including synthetic duplicate/mixed DTC records, individual and grouped edits, exact undo/redo, reference mismatches, project-reference integrity and the copied stock/V9 reference (504 records). Existing editing, axes, hex, checksum, detection and export regressions passed. GUI smoke passed. Native Windows inspection of the copied V9 file confirmed English grouping, white button labels, green/red states, all-bank toggling and exact undo to zero changed bytes. Original firmware was not opened from USB or changed.

## Known issues and limits

- DTC enabling needs exact known enabled bytes in the loaded original or a validated matching stock reference. A factory-disabled reference cannot recover an enabled state. Mixed group buttons enable matching records; use expanded record controls for individual changes.
- DTC scanning supports selected standard V4.1 classic EDC15 record layouts; unsupported/fault-path layouts remain unsupported. These are firmware monitoring settings, not live fault readings.
- A stock reference contains private firmware inside your project. Projects and reference data are not included in public releases.
- Opening projects with this new reference field in older OpenCal releases will ignore that optional restoration reference. Use 0.7 or newer to retain it when resaving.
- Map discovery and semantics still need review outside the validated standard EDC15 layouts. Other ECU families, generic EDC16 checksums and ECU map-switching patches remain unsupported.
- Existing table editing selects cells or whole rows; arbitrary rectangular paste is not implemented. 3D plots use indexed spacing. Nonmonotonic axis interpolation uses index spacing.
- Launch-control byte edits have source parity tests but no vehicle execution validation. Matching checksums do not validate calibration or execution.
- Live comparison windows, automatic EGR and the C166/C167 code workspace are planned, not implemented in this release.
- Windows portable builds are 64-bit and require the whole extracted folder. No clean Windows VM validation has been performed.
