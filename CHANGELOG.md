# Changelog

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
