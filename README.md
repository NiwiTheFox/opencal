# OpenCal 2

**Free, offline calibration editor for Bosch EDC15P/V diesel ECUs (VAG 1.9 / 2.0 TDI PD).**
Open a read, find the maps, tune them, check the result and save a flash-ready file with corrected
checksums. No account, no tokens, no ECU locking.

> OpenCal 2.0 is a **pre-release**. Map identification is heuristic and tuning tools are aids, not
> guarantees. Always keep your original read, review every change, and verify on the car with logs.

## Download

Get the latest pre-release from the [Releases page](https://github.com/NiwiTheFox/opencal/releases):

| File | What it is |
| --- | --- |
| `OpenCal-2.x.x-win64.exe` | Single self-contained executable. Double-click to run. |
| `OpenCal-2.x.x-win64.zip` | Portable folder build; starts faster. Extract and run `OpenCal.exe`. |
| `SHA256SUMS.txt` | Checksums of the downloads. |

Everything is bundled: Python, Qt, numpy, plotting, serial support and data. Nothing to install.
Windows may show a SmartScreen warning because the executable is not code-signed:
choose **More info › Run anyway**.

## What it does

**Editor**
- Opens 512 KB EDC15P/V V4.1 files, reads part number, software, Bosch number and codeblocks.
- Finds every axis-described table, names the important ones (driver wish, smoke limiter,
  torque limiter, IQ by MAP, boost target / limit, N75, SOI, injection duration, EGR, start IQ,
  MAF/MAP linearisation…) and shows them with physical units.
- Heat-coloured table editor: type or double-click to edit, `+`/`−` steps, set / add / percent /
  percent-of-original on a selection, interpolate, smooth, copy/paste (Excel-compatible),
  restore original, edit shared axes. 2D graph with original as dashed lines, 3D surface.
- Codeblock switcher for multi-map files; *Changed* group lists every edited map.
- Full undo/redo, change history, compare with the original or any other file and copy maps across.
- Hex viewer with changes highlighted, C166/C167 disassembly.

**Checks and saving**
- Checksums for the standard V4.1 layouts (tdi41, tdi41 v2, 2002), verified on load and
  corrected on save. Arithmetic is tested against independently compiled vectors.
- *Safe to flash?* pre-flash check: checksums, empty maps in a bank, boost above the MAP-sensor
  range, boost limit/SVBL below target, smoke limiter effectively off, late end of injection.
- Projects: every saved version kept next to the untouched original, with notes and ZIP backup.

**Tuning tools**
- **Auto Stage 1**: builds a reviewable plan from the file's own calibration (fuel, smoke limit
  held at a chosen lambda, torque limiter, boost with a MAP-sensor cap, boost limit, SVBL), then applies it as one undo step.
- **Multimap by coding**: fills empty banks with copies of the calibration and gives each its
  own codeblock id; tune each bank separately.
- **DTC disable/enable**: per fault code across every bank, with exact restoration of stock bytes.
- **EGR off** (race/off-road), optionally with the four EGR fault codes.
- Duplicate smoke limiter, activate launch control (experimental), SVBL and MAP/MAF switch,
  MAP-sensor linearisation from a datasheet's two points.
- **EEPROM editor** (95040 dump): immobiliser on/off, VIN, immobiliser ID, login code, mileage.

**Calculators and analysis**
- AFR / lambda from boost, power and torque estimate, end of injection (SOI − duration),
  turbo compressor fit (approximate envelopes).
- **Virtual dyno**: full-load torque and power estimated from the limiters, compared with the original.
- **Datalog analysis**: VCDS CSV and generic CSV, logged samples binned onto any map.

**ECU (K-line)**
- KKL / FTDI cable: identification, read and clear fault codes, live measuring blocks with CSV logging.
  A built-in simulator lets you try it without a car.
- Flash read/write and live tuning are **not** in 2.0. Use your flasher (MPPS, Galletto…) to read and write.

## Using it

1. Open your read (**File › Open file** or drop it on the window). The original is never overwritten unless you choose it.
2. Look at **Overview**: identity, banks, key maps, estimated power and the pre-flash check.
3. Open maps from the sidebar, edit them, or use a tool from **Tuning**.
4. **Check** (F9), then **Save as…**. Checksums are corrected automatically.

Keyboard: `Ctrl+O` open · `Ctrl+S` save · `Ctrl+Z`/`Ctrl+Y` undo/redo · `F9` pre-flash check ·
`Ctrl+H` hex · `Ctrl+I` firmware info.

## Run from source

```console
python -m pip install -r requirements.txt
python -m opencal [file.bin]
```

Tests (`QT_QPA_PLATFORM=offscreen` for the GUI test):

```console
python -m unittest discover -s tests -t . -v
```

Set `OPENCAL_PRIVATE_BINS` to a folder of your own 512 KB reads to run the real-file checks;
vehicle firmware is never committed.

Build the executable: `python -m pip install pyinstaller` then `python tools/build_exe.py`.
Pushing a `v*` tag makes GitHub Actions test, build and publish a pre-release.

## Versioning

`2.MINOR.PATCH`: the major stays 2 for this generation. **MINOR** goes up for feature updates,
**PATCH** for bug fixes. Every release lists its changes, known bugs and what is planned next in
[CHANGELOG.md](CHANGELOG.md). OpenCal 1.x (Tk interface) lives on the
[`old` branch](https://github.com/NiwiTheFox/opencal/tree/old).

## Contributors

- [NiwiTheFox](https://github.com/NiwiTheFox): project owner, testing on real cars
- Claude (Anthropic): OpenCal 2 code, design and tests

Contributions are welcome: bug reports with steps, screenshots and the software number
(do not post customer firmware), or pull requests with tests.

## License and credits

GPL-3.0-only. See [LICENSE](LICENSE) and [NOTICE](NOTICE). OpenCal includes attributed ports from
[ZedSuite](https://github.com/LeZed97/ZedSuite) (DTC records and descriptions, mappack conventions)
and the freeware VAG EDC15P Suite by Dilemma / MTX Electronics checksum algorithm, plus a
GPL C166 disassembler. Upstream sources and notices are kept in `third_party/`.

OpenCal is independent and not endorsed by Bosch, Volkswagen Group, ZedPerf or any commercial
tool vendor. There is no warranty, including no warranty of ECU compatibility. Changing emissions
equipment (EGR, etc.) is for off-road / competition use only and is illegal on public roads in many
countries.
