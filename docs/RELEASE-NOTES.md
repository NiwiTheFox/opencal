# OpenCal 0.8.0 — Live comparisons and side-by-side maps

Development preview. Extract the whole Windows ZIP and run OpenCal.exe. Python and Tcl/Tk are bundled.

## What changed

- Analysis & compare → Compare BIN opens separate hex and map-comparison windows. The selected comparison BIN is read-only; all editing affects the active project.
- Hex comparison shows both files, highlighted differences, synchronized file-wide scrolling, previous/next differences, offset navigation and active-byte editing. Unequal file lengths are visible; editing cannot resize the active BIN.
- Changed maps are grouped by codeblock and category. Opening a map shows the editable active table/graph beside the read-only reference table/graph. The reference pane has a lighter grey background and no edit bindings or commands.
- A second values tab lists physical active/reference/delta values, including changed axes. Enter, double-click or the Edit selected button edits active values; axis edits use the existing checked preview.
- Comparison editors share the main project's bytes and history. Map, axis, hex, DTC edits and undo/redo update every view without reloading the BIN. Open in main editor jumps to that map in the workbench.
- A selected map stays open if editing removes its final difference. Group expansion and list position are preserved; replacing or closing the project closes its comparison views and removes their listeners.
- Matching standard EDC15 banks can be compared with a single matching ORI bank after identity and axis-header checks. Codeblock metadata distinguishes bank identities. Incompatible or ambiguous map layouts are listed as unmatched; raw hex comparison remains available.
- English grouped DTC controls from 0.7 are retained.

## Validation

94 tests passed in the final local portable build, including its bundled runtime (no skips). GUI smoke passed. Tests cover aligned side-by-side tables, visible controls at small window sizes, callback errors, shared-document notifications, active/reference protection, changed axes, incompatible inputs, active edits, immediate main-editor updates, undo, window closing and listener cleanup. Native Windows inspection confirmed codeblock/category grouping, both maps visible side by side and the lighter read-only reference pane. The copied stock/V9 definitions matched all 213 tables and exposed 84 changed maps. Copied firmware remained unchanged on disk.

## Known issues and limits

- Map matching currently supports checked standard V4.1 EDC15 bank layouts and explicitly signed synthetic fixtures. Other layouts are shown as unmatched rather than interpreted at guessed offsets. Matching metadata does not independently verify map semantics.
- Hex comparison uses raw file offsets. Map comparison can relocate compatible banks, so their difference counts describe different comparisons.
- The values/delta tab shows at most 4,096 table cells plus the axes; counts cover the entire map. Existing table/row editing remains available in the side-by-side editor.
- Large files or many simultaneous comparison sessions can make full difference recalculation slower. The app remains an offline editor, without a live connection to the ECU.
- The reference pane supports inspection, units and graph selection. To edit that file, open a separate working project; this comparison never edits it.
- DTC enabling requires known enabled bytes from the loaded original or a checked matching stock reference. Classic standard V4.1 DTC layouts only. Mixed group buttons attempt to enable all matching records; individual control is available underneath.
- Map discovery outside validated EDC15 layouts remains incomplete. Unsupported checksums and ECU map-switching patches remain unsupported.
- Arbitrary rectangular table paste is not implemented. 3D plots use indexed spacing; nonmonotonic interpolation uses index spacing.
- Automatic EGR and the C166/C167 workspace are still planned. The supplied ORI and V9 both already contain a flat 850 mg/st candidate EGR request map, so their differences do not validate a new map-disabling strategy.
- Launch-control execution and modified calibrations have not been validated on a vehicle. Checksum matching does not validate execution.
- Windows portable builds are 64-bit and require the entire extracted folder. No clean Windows VM test has been performed.
