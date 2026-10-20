# Architecture and dependency decision

Version 0.2 update: the combined app now uses GPL-3.0-only following reuse of
ZedSuite code/data under that license. The original dependency decision below
remains applicable; no new runtime dependencies were introduced.

| Stack | Strengths | Costs for this release |
|---|---|---|
| Rust + egui/eframe | Native Windows, fast scans, safe core, custom plots; MIT/Apache options | Rust toolchain absent; more implementation effort for complex editable tables and distribution |
| Python + PySide6 | Strong desktop tables, Qt graphics and Windows support | Not installed; large dependency; LGPL/GPL compliance and module-specific licensing need care |
| Python + Tk (chosen) | Installed, offline, no added dependencies, easy community edits | Basic plots, less polished tables, Python scan speed, future packaging work |

The reference's language was not the deciding factor. Tk makes the initial release
runnable and testable on this host now. Core behavior has no GUI dependency and can
be reused behind PySide6 later. Python and Tcl/Tk are open source; dependency
licenses must be retained if those runtimes are bundled in a future distribution.

Primary sources consulted:
- https://docs.python.org/3/library/tkinter.html
- https://doc.qt.io/qtforpython-6/
- https://github.com/emilk/egui/blob/main/LICENSE-MIT
- https://github.com/emilk/egui/blob/main/ARCHITECTURE.md

## Current boundaries

- `opencal/core.py`: immutable input, edits, diff/search, definition validation,
  map conversion, signature matching, candidate scanning, project serialization and export.
- `opencal/gui.py`: dialogs, paged hex, tables/plots, definition editor and profile UI.
- `opencal/edc15.py`: attributed conservative detection and classic DTC subset.
- `opencal/checksums.py`: attributed standard V4.1 / 2002 algorithm and fail-closed selection.
- `opencal/multimap.py`: original read-only banking evidence inspection.
- `opencal/cli.py`: repeatable read-only analysis and comparison.
- `tests/`: synthetic core invariants, optional private ECU fixtures and Tk workflows.
- `examples/`: original synthetic BIN and definitions only.

Core currently groups small subsystems in one module. Split into binary,
definitions, discovery, identification, projects and calibration modules as APIs
grow. Keep UI outside those modules; add asynchronous tasks for long scans.

## Extension boundaries

Checksum providers must declare family, exact input layout, software matches,
protected regions, algorithm provenance/license and independently checked vectors.
Unknown/ambiguous selection remains unverified. The standard V4.1 / 2002 provider
is tested on two supplied images and controlled mutations, including comparison
against upstream TypeScript. It reports region matches, not vehicle certification.
Never substitute a generic CRC or SHA-256 for an ECU algorithm.

Discovery providers should return address/shape/axes, type/endian, evidence,
confidence, provenance and software constraints. Candidate patterns may be manually
defined but must not become verified through a UI action alone.

SVRL editing should reuse bounded scalar-map conversion only after address,
software identity, allowable range and checksum coverage have been verified.
Speed limitation, RPM cut and hard-cut/launch control must remain distinct.

ECU multimap requires verified switching-code behavior and memory layout, separate
from named snapshots. No generic ECU patching interface is exposed in this release.
Require a matched binary fingerprint, region preconditions, rollback and bench vectors
before adding a switching provider. Never derive patches from proprietary EXE code.
For historical context, the original 0.1 application code and synthetic assets used
MIT. The 0.2 combined application uses GPL-3.0-only. No runtime is bundled, so
retain runtime licenses if building a frozen distribution later.


## C166 boundary (1.0.0)

`c166.py` decodes bytes without a GUI or reference-app runtime. `c166_tools.py` validates memory mapping, restricted source, bundled tool hashes, AS object coverage and patch previews; it also validates saved code metadata. `c166_ui.py` owns the separate Tk window. The shared Document remains the only byte-edit/history authority. Source/mapping/notes persist as optional validated project metadata; old project v1 remains readable.
