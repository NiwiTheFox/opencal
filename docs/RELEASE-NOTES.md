# OpenCal 2.0.0 (pre-release)

A complete rewrite with a new Qt interface. OpenCal 1.x stays available on the
[`old` branch](https://github.com/NiwiTheFox/opencal/tree/old).

## Download

- `OpenCal-2.0.0-win64.exe`: single self-contained executable, nothing to install.
- `OpenCal-2.0.0-win64.zip`: portable folder build (faster start). Extract and run `OpenCal.exe`.
- `SHA256SUMS.txt`: checksums.

The executable is not code-signed; Windows SmartScreen may ask you to confirm (More info › Run anyway).

## Changes

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

## Known bugs and limits

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

## Planned for the next update (2.1.0)

- Validate K-line diagnostics on real cars; add KW1281 fallback.
- Flash read/write over K-line (with automatic backup and verify).
- Multimap on-the-fly switching patch (C166) and research into live tuning.
- Per-software definition packs and more named maps (SVRL rpm limiter, idle, pre-injection).
- 256 KB EDC15V and EDC15C support.
- Workbench: several maps side by side; map overlays coloured by log deviation.
- Import 1.x projects.
