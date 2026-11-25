# OpenCal 2.1.0 (pre-release)

Tested against 93 real EDC15P files (single-map and multimap, ATD/ASZ/ARL/AXR/AVF/BPX and others,
cruise-control and pedal-switched multimaps) and three 95040 EEPROM dumps.

## Download

- `OpenCal-2.1.0-win64.exe`: single self-contained executable, nothing to install.
- `OpenCal-2.1.0-win64.zip`: portable folder build (faster start). Extract and run `OpenCal.exe`.
- `SHA256SUMS.txt`: checksums.

Not code-signed: Windows SmartScreen may ask you to confirm (More info › Run anyway).

## Changes

- **Virtual dyno is now a simulation**: cranking with the start-fuel map, firing and idle, then a
  full-load pull in a chosen gear. Each step it spools the turbo toward the boost target, measures
  airflow and takes fuel as the lowest of driver wish, smoke, torque limiter and IQ-by-MAP, then
  computes torque and vehicle acceleration. Animated gauges, power curve against the original, run
  trace (rpm, boost actual/target, fuel, lambda) and an event log (start time, smoke, overboost →
  SVBL limp mode, late end of injection, rpm limit, which map set the fuel).
- **Units**: Options › Units: pressure mbar/bar/kPa/psi, power hp/kW/PS/bhp, torque Nm/lb-ft/kgm,
  temperature °C/°F/K, speed km/h/mph, fuel mg/st or mm³/st. Applies to tables, axes, editing,
  dyno, overview and calculators. The file keeps its native scaling.
- **Codeblock on every map** in the sidebar (`· CB 3`), and in the editor header.
- **Multimap**: the overview shows how many calibrations a file has; Compare with file reports code
  differences against a stock read (switching patch hooks and routine). OpenCal never touches the
  code area when editing maps, so cruise-control / pedal switching patches are preserved.
- **Checksum safety**: the checksum algorithm is now locked from the file as opened. If the file
  arrived with wrong checksums, OpenCal no longer guesses; it asks which layout to use (or saves
  uncorrected on request). Fixes a 2.0 risk of correcting with the wrong algorithm.
- **EEPROM**: `.e2p` files open directly (File › Open or drop) in the EEPROM editor.
- **Start fuel**: an unrelated table was named Start IQ on several softwares; the rule now requires
  realistic start fuel, and the dyno warns and uses a typical value when none is found.
- **Map identification**: torque limiter now found on all tested software (altitude axis from 500
  mbar); N75 identified by its axis family; signed SOI tables (LA/GL/NF software) named and shown in
  real degrees; injection-duration tables read as signed; exact 3/128 angle factor (no more 0.0017°).
- `tools/survey.py`: runs a folder of files through the engine and prints a compatibility table.

## Known bugs and limits

- EGR (airflow target) maps are not identified on about a quarter of tested banks, mostly ASZ/AG
  software; EGR off then changes nothing there. N75, driver wish, boost limit and SOI are missed on
  a few software versions.
- Older "compact" EDC15P software (seen: 038906019CJ SG1086) has a different table structure:
  driver wish and SOI are not identified there. Checksums, DTCs and the rest work.
- Early EDC15P files without V4.1 banks (e.g. 038906019AM SG0813, 115 hp PD) open read-only in
  practice: no map naming, no checksum layout.
- 256 KB EDC15V and 2 MB EDC16 files are refused; not supported yet.
- K-line works with plain KKL / FTDI serial cables only (tested against the simulator). The MPPS v18
  and HEX-V2 interfaces use proprietary protocols and are not supported.
- Multimap: switching patches are detected and preserved, but OpenCal cannot yet create one.
- The dyno is a model: a fixed Nm-per-mg factor, simple turbo lag and vehicle; use it to compare maps,
  not as a power figure.
- Event texts in the dyno log are in native units (mbar, hp, Nm) whatever the Units setting.

## Planned for the next update (2.2.0)

- Better EGR / N75 identification and per-software definition packs.
- Multimap switching patch builder (C166), starting with SG 1376 using a supplied reference pair.
- MPPS v18 interface research (read/write over K-line) from user-supplied USB captures.
- 256 KB EDC15V and EDC15C support; EDC16 read-only viewer.
- Datalog overlay coloured by deviation in the map editor; workbench with maps side by side.
