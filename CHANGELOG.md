# Changelog

Versions follow `2.MINOR.PATCH`: MINOR for feature updates, PATCH for bug fixes.
Every release lists its changes, known bugs and what is planned next.

## 2.0.0 (pre-release)

Complete rewrite with a new Qt interface. 1.x is kept on the `old` branch.

### Changes

- New interface: header with file identity, codeblock switcher and live checksum status;
  searchable map sidebar; overview dashboard; heat-coloured map editor with 2D graph and 3D surface.
- New map discovery: axis-header scanner with map-group/selector parsing, value-range-based
  identification that works across software versions (axis ids differ per software).
- Codeblock model: banks span base−0x4000…base+0xC000; ids read from the bank pointer.
- Checksums: tdi41, tdi41 v2 and 2002 layouts, auto-detected, fixed on save; tested against C# vectors.
- Editing: set/add/percent/percent-of-original, interpolate, smooth, Excel copy/paste, axis editor,
  restore original, transactions with one-step undo, change history.
- Tuning: Auto Stage 1 plan/apply, multimap by coding (fill empty banks, ids), copy/empty/repair bank,
  DTC disable/enable with exact restore, EGR off (+ EGR fault codes), duplicate smoke limiter,
  launch-control activation, SVBL, MAP/MAF switch, MAP-sensor linearisation.
- Checks: *Safe to flash?* pre-flash check.
- Calculators: AFR/lambda from boost, power/torque, end of injection, turbo compressor fit; virtual dyno.
- Datalogs: VCDS/generic CSV import and overlay on maps.
- ECU: K-line KWP2000 diagnostics (identification, fault codes, live measuring blocks, CSV log) and a simulator.
- EEPROM editor: immobiliser, VIN, immobiliser ID, login code, mileage.
- Mappacks: TunerPro XDF import/export, OpenCal JSON, ZedSuite/WinOLS JSON import.
- Projects with versions, notes and ZIP backup.
- Self-contained Windows executable built by GitHub Actions.

### Known bugs and limits

- Map names are heuristic. A few secondary tables can be misnamed (for example a second
  "IQ by MAP limiter" or "N75 duty cycle 2"); always check address, size and values.
- Only 512 KB EDC15P/V V4.1 layouts are supported for maps and checksums. 256 KB EDC15V files
  open but have no map identification or checksum support yet.
- K-line diagnostics have been tested against the simulator only, not on a car yet.
- Multimap by coding: which coding selects which codeblock id is not verified per software;
  there is no on-the-fly switching (cruise stalk) patch yet.
- Launch-control activation is experimental and unverified on a vehicle.
- End-of-injection, dyno and turbo-fit figures are estimates (one SOI/duration map pair,
  a fixed Nm-per-mg factor, approximate compressor envelopes).
- XDF import reads 16-bit tables only. 1.x project files (`.ocproj`) cannot be opened.
- The single-file executable takes a few seconds to start (it unpacks itself); the ZIP starts faster.

### Planned for the next update (2.1.0)

- Validate K-line diagnostics on real cars; add KW1281 fallback.
- Flash read/write over K-line (with automatic backup and verify).
- Multimap on-the-fly switching patch (C166) and research into live tuning.
- Per-software definition packs and more named maps (SVRL rpm limiter, idle, pre-injection).
- 256 KB EDC15V and EDC15C support.
- Workbench: several maps side by side; map overlays coloured by log deviation.
- Import 1.x projects.

---

# OpenCal 1.x (old branch)

# 1.0.0

Bundled C166/C167 mapped disassembly and source workspace, AS assembly previews and guarded bounded patches, saved source/notes/mapping and shared Undo/Redo. See docs/C166-WORKSPACE.md.

# 0.9.1

Expanded EDC15 layouts, compact checksums and shared fault-path DTCs, early map classification, broader guarded EGR previews, correctness audit and regression fixes. See docs/RELEASE-NOTES.md and docs/SUPPORT.md.


## 0.9.0 — 2026-10-20

Checked FJ/1376 EGR fresh-air request and related DTC solution, all-bank guards, exact byte preview, one-step undo and original restoration. Scrollable Solutions and replaced-project launch-control guard. Retains the live grouped side-by-side comparison editor. See [release notes](docs/RELEASE-NOTES.md) for support boundaries and known issues.

## 0.8.0 — 2026-10-20

Live hex and map comparison windows; editable active maps beside lighter-grey read-only reference maps; codeblock/category groups; compatible ORI bank matching; current/reference/delta values; shared undo/redo and immediate updates in the main editor. See [release notes](docs/RELEASE-NOTES.md) for validation and known issues.

## 0.7.0 — 2026-10-19

English DTC descriptions and system grouping; white-text state buttons with green/red rows; grouped and individual codeblock control; persistent live DTC display; exact stock-reference restoration with project persistence. See [release notes](docs/RELEASE-NOTES.md) for validation and known issues. Upcoming comparison/EGR/C166 work is in [the roadmap](docs/ROADMAP.md).

## 0.6.1 — 2026-10-19

- Added a portable Windows download containing Python and Tcl/Tk. Extract the
  folder and run OpenCal.exe; no Python installation is needed.
- Added an isolated runtime path, runtime manifest, retained component licenses,
  and bundled-runtime checks before release publication.
- Fixed map groups losing their expanded/collapsed state after an edit or undo.

Known issues: keep the entire extracted folder together. The portable build is
64-bit Windows only. Remaining editing/detection limitations from 0.6 apply.

## 0.6.0 — 2026-10-19

- Added ROM X/Y axis editing with before/after previews and shared-storage details.
- Added inline table-cell editing, batch set/add/percent operations, interpolation,
  numeric CSV import, map restoration and guarded copying to matching banks.
- Fixed stale axis headers after edits and undo/redo; older imported projects can
  recover their axis encoding from retained descriptors.
- Replaced the fixed hexdump page with file-wide scrolling, keyboard navigation,
  horizontal scrolling and click-to-select byte addresses.
- Added codeblock groups and firmware metadata IDs. Bank addresses no longer
  masquerade as codeblock numbers; unreadable IDs remain explicitly unknown.
- Added a resizable table/graph split, clearer table styling and centered dialogs.
- Kept custom launch-control axes visible using the loaded original's evidence.
- Strengthened stored-value bounds and damaged project undo/redo rejection.
- Added public packaging checks and a test-gated GitHub preview-release workflow.

Known issues: rectangular cell selection/paste is not implemented; legacy axes
without recoverable encoding are read-only; 3D uses indexed spacing. Detection
and ECU execution limits are detailed in [release notes](docs/RELEASE-NOTES.md).
The sidebar also resets expanded groups after edits/undo in 0.6.0; fixed in 0.6.1.

## 0.5.0 — 2026-10-18

- Added the Solutions tab and source-backed launch-control speed-axis activation.
- Added exact byte previews, one-operation undo and original-axis restoration.
- Matched upstream TypeScript output on the private stock and tuned fixtures.
- Kept generated solution definitions in sync through undo and redo.

Known issues in 0.5: no dedicated X/Y editor; fixed-page hexdump lacks file-wide
scrolling; large tables may clip lower controls; codeblock labels use bank
addresses inconsistently. Customising the launch-control speed axis via hex
can hide the generated map. These are addressed by the 0.6 changes above.

## 0.4.0 — 2026-10-18

- Added a dedicated single-value editor and separate SVRL/SVBL shortcuts.
- Fixed scalar presentation, sidebar sizing, font hierarchy and combobox colors.
- Preserved raw/physical display preferences across edits.

Known issues in 0.4: X/Y axes are not editable through a dedicated dialog;
hexdump navigation is page-based; large tables can push the graph/controls out
of view; tuned-map labels use inconsistent bank/codeblock wording.

All versions are development previews. Source-level and byte-level checks do not
establish on-vehicle behaviour, flashing compatibility or calibration suitability.
