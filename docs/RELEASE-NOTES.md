# OpenCal 0.6.0 — 19 October 2026

This update addresses the reported map-editing, codeblock-label and hexdump problems.

## Changes

- Edit ROM X/Y breakpoints through a physical-value dialog and a stored-byte
  preview. Shared axes refresh across related maps, including after undo/redo
  and project reopening. Old imported projects recover encoding when possible.
- Edit table cells in place with Enter/Esc. Preview batch set/add/percentage
  changes, endpoint interpolation, numeric CSV import and whole-map restoration.
- Copy a table to other calibration banks only when definitions, encodings,
  relative addresses and current axis headers/bytes match.
- Scroll the hexdump through the entire BIN with its scrollbar, wheel or keyboard.
  Click a hex or ASCII byte to select its edit address.
- Group supported codeblocks using firmware metadata IDs. The private tuned
  fixture's IDs are 4/5/3; they are not inferred from bank position. Invalid
  metadata is labelled unknown.
- Resize the table/graph split. Keep lower controls visible at smaller sizes.
- Retain custom launch-control axes using evidence from the loaded original.
- Reject out-of-range stored rounding and inconsistent project undo/redo data.
- Provide a friendlier README, cumulative changelog and test-gated release workflow.

## Validation

79 unit/integration/widget tests pass on the development Python 3.13 and launcher Python 3.14 runs. The
copied supported corpus passes 14,373 axis edit/undo cases and 9,660 cell
edit/undo cases across 4,073 map grids in 31 unique binaries. All tested copied
BINs remain byte-for-byte unchanged on disk. The GUI regression rendered all
71 original-fixture maps, 213 ORI-derived tuned maps and 203 separately imported
reference-comparison maps. Older imported projects were reopened and axis edits
were undone exactly. These are software checks, not vehicle tests.

## Known issues and limits

- Map detection remains incomplete outside the validated standard EDC15 layouts.
  Candidate names, scaling and dimensions still require review.
- Cell selection supports one directly edited cell or selected rows for batch
  operations. Arbitrary rectangular cell selection/paste is not implemented.
- Legacy axes without recoverable storage metadata stay read-only. Reimport a
  supported mappack or detect again; the app will not guess an encoding.
- The 3D surface uses row/column indices rather than physical axis spacing.
- Non-monotonic interpolation axes use index spacing. Interpolation changes
  stored values and rounds to the map's numeric precision.
- ROM axis edits do not automatically preserve monotonic order; original maps
  can contain non-monotonic selector axes. Review breakpoints before applying.
- Preview dialogs remain separate windows. An operation is rejected if the BIN,
  definitions or open project has changed since its preview.
- Launch-control vehicle behaviour and ECU multimap switching remain unverified.
  Codeblock groups and project snapshots do not establish switchable ECU maps.
- Checksum correction covers the enabled standard V4.1 / 2002 layout only.
  A matched checksum does not validate engine operation or flashing suitability.
- Windows builds use an installed Python/Tk runtime; a bundled runtime is not
  included. GitHub's public tests skip private-fixture checks.

See [CHANGELOG.md](../CHANGELOG.md) for earlier versions and
[SOURCE-REVIEW.md](SOURCE-REVIEW.md) for the additional public source research.
