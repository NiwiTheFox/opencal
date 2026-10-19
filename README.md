# OpenCal 0.4

Free, open-source ECU calibration workbench for Windows. Open a BIN, explore
maps, inspect bytes, compare files and keep your edits in a project.

No account, subscription or paid runtime dependencies. Current ECU-specific
tools focus on selected standard Bosch EDC15P-family layouts.

## Get started

1. Extract the OpenCal folder.
2. Install Python 3.11 or newer with Tk if needed.
3. Double-click **OpenCal.exe** or **Launch.cmd**.
4. Choose **Open BIN**, then select a map in the sidebar.

The EXE launches your installed Python; a runtime is not bundled. For practice,
open `examples/synthetic.bin` and import `examples/synthetic.definitions.json`.
These are artificial examples, not vehicle firmware.

## Working with your file

Double-click a table cell to edit it. Use Raw/Physical to change displayed units,
Show original to compare, and Undo/Redo to step backward or forward. Dedicated
tabs provide hex inspection, supported ECU/checksum/DTC tools, comparison and
named snapshots. Save a project to continue later; export a separate BIN to
write your changes. The loaded original stays preserved.

SVRL is the RPM limiter; SVBL is the boost limiter. Their shortcuts are separate.
Map detection remains experimental. Matching checksums do not validate a tune
or make an exported BIN ready to flash. ECU multimap switching is unverified.

See [release notes](docs/RELEASE-NOTES.md) for this version's changes and limits.
Source includes attributed GPL ports from ZedSuite. OpenCal is independent.

## License and development

GPL-3.0-only. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
Run tests with `python -m unittest discover -s tests -v` and
`python -m tests.gui_smoke`. Private fixture tests skip in public packages.
Please do not upload customer firmware or private projects to issues.
