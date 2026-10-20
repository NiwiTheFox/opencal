# OpenCal

**Explore ECU maps, understand your changes, and keep your original file safe.**

OpenCal is a free, offline Windows app for exploring ECU binaries, inspecting
maps, editing calibration values, and keeping track of your changes. Its current
focus is Bosch EDC15P-family software used in VAG diesel ECUs.

Free to use and open source. No subscription, credits, or account required.

> OpenCal is in active development. Map detection and supported solutions are
> experimental, and an exported file is not automatically ready to flash.

## What you can do

- **Explore your BIN:** browse maps by category, search by name or address, and
  inspect the underlying bytes in the hex editor. Supported codeblocks are
  grouped using the IDs stored in the firmware.
- **See the calibration:** switch between numeric tables, 2D curves and a 3D
  surface. Single-value settings have a simple editor with clear units.
- **Edit with context:** view original and modified values, choose raw or physical
  units, edit cells in place, and undo or redo binary changes.
- **Edit X/Y axes:** change supported ROM breakpoints, review shared storage,
  and see headers update as you apply, undo, or reopen a project.
- **Work on a whole table:** preview set/add/percentage changes, interpolate
  between endpoints, import numeric CSV values, or restore the original map.
- **Bring your definitions:** import supported ZedSuite/WinOLS JSON mappacks,
  or use a compatible original-file mappack with layout checks.
- **Keep a project:** save your BIN, definitions, edits and named snapshots in a
  self-contained project you can reopen later.
- **Review before exporting:** compare binaries, check supported checksums,
  inspect supported DTC records, and export to a separate BIN with an audit file.
- **Inspect supported solutions:** preview the source-backed launch-control
  speed-axis change on supported layouts, with undo and original restoration.

Your loaded BIN is kept as the original. Edits stay in the project until you
choose to export, and exports use a new file rather than replacing the input.

## Get started

### Windows

1. Download the **Windows ZIP** from the release assets.
2. Extract the whole folder to a location of your choice.
3. Open **OpenCal.exe** in the extracted folder.
4. Choose **Open BIN**, then select a map in the left sidebar.
5. Double-click a table cell to edit it, then press **Enter** to apply or **Esc**
   to cancel. Use **Undo** to step back.

The Windows ZIP includes Python and Tcl/Tk. You do not need to install Python,
pip packages, a compiler, ZedSuite or VAG EDC Suite. It runs offline and does not
change your system's Python installation. Keep the `runtime` folder beside the EXE.

The separate **source ZIP** is for contributors and needs Python 3.11+ with Tk.
Its launcher uses an installed Python when no bundled runtime is present.

To start from a terminal in this folder:

```console
python -m opencal
```

### Try it without a real ECU file

Open `examples/synthetic.bin`, then import
`examples/synthetic.definitions.json` using **Import mappack**. Try changing a
value, switching views, and undoing your edit. These artificial example files
let you learn the workflow without using vehicle firmware.

## Find your way around

| Where | What you'll find |
| --- | --- |
| Left sidebar | Your project, map categories, and map search |
| Map editor | Tables, curves, surfaces, and single-value settings |
| Hexdump | The BIN's bytes, with inspection and editing tools |
| ECU tools & DTCs | Supported identification, checksum, and fault-code tools |
| Analysis & compare | Differences between binaries |
| Versions | Named snapshots of your calibration work |
| Solutions | Preview and apply the supported launch-control change |

In the map editor, **Physical** shows converted values with units, while **Raw**
shows the numbers stored in the file. Turn on **Show original** to compare your
edits with the loaded BIN.

Use **Edit X axis** or **Edit Y axis** to change ROM breakpoints. Axis dialogs
always show physical values and use a preview before applying. You can also
double-click an X heading or Y row label. Shared axes update in every map that
uses those bytes. Older imported projects recover axis storage from their
retained mappack when possible; otherwise reimport the pack or detect maps again.

**Table actions** includes batch edits, CSV import, original restoration and
copying values to matching calibration banks. Use Ctrl/Shift to select rows for
a batch edit. CSV import/export uses numeric physical values in storage order,
without headers. The divider between the table and graph is draggable.

The **Hexdump** scrollbar and mouse wheel navigate the whole file. Page Up/Down
move through the viewport; Ctrl+Home/End jump to the start/end. Click a hex or
ASCII byte to select the address used by **Edit bytes**.

## A simple workflow

1. **Start with a copy** of your original BIN and open it in OpenCal.
2. **Review the detected maps.** Import a compatible mappack if you have one.
3. **Select and inspect a map.** Check its name, address, dimensions and units.
4. **Make a change.** Compare it with the original and use Undo whenever needed.
5. **Save a project** to keep your work and snapshots together.
6. **Check and export.** Review supported checksums, then export a new BIN and
   its accompanying audit report.

**SVRL** is the engine-speed limiter, shown in **rpm**. **SVBL** is the
single-value boost limiter, shown in **mbar**. They have separate shortcuts so
you can jump to the setting you intended to inspect.

## Compatibility today

| Area | Current support |
| --- | --- |
| BIN inspection, hex editing and comparison | Available independently of ECU-specific detection |
| Map discovery | Selected standard 512 KiB EDC15 V4.1 layouts; EDC15P is the main focus |
| JSON mappacks | Supported ZedSuite/WinOLS field layouts, with validation |
| X/Y axis editing | ROM axes with explicit type, byte order, scaling and bounded storage |
| Copy table to other banks | Matching definitions, encodings and current axis bytes required |
| ORI-to-tuned definitions | Requires matching identifiers and compatible bank/axis layouts |
| Checksum verification and correction | Supported standard V4.1 / 2002 layout only |
| DTC tools | Selected classic EDC15 record layouts |
| Launch-control solution | Pattern-checked speed-axis change; vehicle behaviour unverified |
| EDC16 and other EDC15 layouts | Not supported by the ECU-specific editing tools yet |
| ECU multimap switching | Research in progress; no verified switching patch |

Detected maps remain **candidates**. Different reference tools can disagree on
names, scaling or dimensions. A matching checksum confirms the supported checksum
calculation; it does not establish that a calibration is suitable for an ECU.

Named project snapshots are useful versions of your work. They are separate from
switchable maps running inside an ECU.

## Built in the open

OpenCal combines original work with attributed ports from the GPL-licensed
[ZedSuite project](https://github.com/LeZed97/ZedSuite). It uses its own interface
and does not require either reference application to run.

The source detector has been compared with fresh reference exports on supplied
EDC15 files. Tests also cover byte preservation, undo/redo, project integrity,
checksum correction, unsupported inputs and UI workflows. Detailed results and
known limits are kept in [the release notes](docs/RELEASE-NOTES.md).

Private ECU files, customer binaries, personal projects and reference-app exports
are not included in public source releases. Public packages start with an empty
user reference-profile catalog; the source detector and synthetic examples remain
available.

## Common questions

**Do I need Python, ZedSuite or VAG EDC Suite installed?**  
No. The Windows download includes its own Python/Tk runtime. Only the source
download needs a separately installed Python.

**What is a mappack?**  
It is a set of map definitions: where a map lives in the BIN, its size, and how
to display its values. Importing one adds definitions; it does not copy another
file's calibration values into your BIN.

**Why are some maps missing?**  
Automatic detection currently covers selected layouts. A compatible mappack can
add definitions the detector has missed. Check its addresses, dimensions and
scaling before editing.

**Should I save a project or export a BIN?**  
Save a project when you want to continue working later. Export a BIN when you
want a separate binary containing your changes. Keep your untouched original.

## Roadmap

- Broader map-discovery coverage and more independent reference comparisons.
- Richer cell selection, visualisation and calibration review.
- More checksum providers, enabled only after suitable validation.
- Continued Windows packaging and UI improvements.
- Further software-specific research into SVRL and ECU multimap switching.

## Contributing

Bug reports, reproducible steps and small improvements are welcome. Include the
OpenCal version, what you expected, what happened, and a screenshot when useful.
Use a synthetic example or a file you have permission to share; do not post
customer firmware or personal data.

To run the tests:

```console
python -m unittest discover -s tests -v
python -m tests.gui_smoke
```

Tests that need private development files skip when those files are unavailable.

## License

OpenCal is licensed under **GPL-3.0-only**. You may use, study, modify and
redistribute it under that license. See [LICENSE](LICENSE) and [NOTICE](NOTICE)
for the full terms and third-party attribution.

Windows bundles also retain the Python, Tcl/Tk and component license notices in
`runtime-licenses`. Runtime versions and packaging changes are recorded in
`RUNTIME-MANIFEST.json`.

OpenCal is independent and is not endorsed by ZedSuite, Bosch, or Volkswagen Group.

## DTC controls

Read the DTC records under **ECU tools & DTCs**. Codes are grouped by system. Click a code’s state button to toggle every matching record; expand its arrow to control individual codeblocks. Green means enabled, red means disabled, and Mixed means the records differ. These are monitoring settings in the BIN, not live vehicle faults.

If a tuned file was already disabled when loaded, use **Load stock DTC reference…** with its matching copied original. OpenCal checks identities and record layouts before it can restore exact enabled bytes. Save a project to retain the checked reference.

See [the update roadmap](docs/ROADMAP.md) for the next releases.

## Compare two files

Open **Analysis & compare → Compare BIN** and choose a copied reference BIN. Two windows open: synchronized hex and changed maps grouped by codeblock/category. Maps open side by side: edit your active project on the left, inspect the lighter-grey read-only reference on the right. Both windows share the main editor’s data and undo history, so changes appear immediately. The values tab shows the active value, reference and difference; use its Edit selected button or Enter to edit an active value.

Map comparisons require compatible definitions and supported matching layouts. A stock bank can be compared with matching banks in a tuned file. Raw hex comparisons always use file offsets. No reference bytes are overwritten.

## EGR solution

Under **Solutions**, choose **Preview disable EGR**. The initial supported profile is standard **038906019FJ / 0281010789 / SG 1376**. OpenCal checks every bank before proposing the 850 mg/st request-map target and its four related diagnostic codes. Review the maps, diagnostics and exact bytes, then apply one undoable change. Correct supported checksums and export a separate BIN when ready.

The target strategy is source-backed and tested at byte level; vehicle behaviour remains unverified. Other software is refused. **Restore loaded original** returns to the exact input file, which may already contain modifications.

Coverage is feature-specific. See [EDC15 support](docs/SUPPORT.md) and [source audit](docs/AUDIT-0.9.1.md). C166 tools are planned for 1.0.0; new feature versions follow 1.x.0 and quick fixes 1.0.x.
