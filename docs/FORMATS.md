# Open formats v1

All addresses are byte offsets from the start of the file. JSON addresses accept
integers or explicit `0x` strings; floats are rejected. No automatic memory-base
translation. Ranges use exclusive ends. Map data is row-major, contiguous.

## Definitions

Root: `schema: "opencal.definitions"`, `version: 1`, `maps: []`, `signatures: []`.
See the complete original example in `examples/synthetic.definitions.json`.

Each map requires unique `id`, `name`, `address`, integer `rows`/`columns` (1–1024),
`type` (u8/i8/u16/i16/u32/i32/f32), `endian` (little/big), nonzero finite `factor`,
finite `offset`, `unit`, `category`, `verification` (synthetic/candidate/verified),
`source` and `license`. Optional `minimum`/`maximum` bound physical values.
Optional `description`, `ecu_family`, `software_ids`, `definition_version`,
`confidence` and attribution metadata can be preserved. These metadata fields do
not enforce software compatibility yet.

`physical = raw * factor + offset`. Integer edits round to the nearest representable
raw integer (Python ties-to-even); storage overflow is rejected. Unrelated bytes
are unchanged. Optional `x_axis`/`y_axis` have finite explicit `values` matching
columns/rows, with optional `name`/`unit`. Since 0.6, editable ROM axes also carry
`address`, `type`, `endian`, `factor`, and `offset`. Their storage is bounds-checked
and headers decode the current bytes, including after hex edits and undo/redo.
Axes without this storage description remain display labels; the editor does not
guess an encoding. The 3D graph uses sample indices. No XDF import yet.

Version 0.2 additionally accepts the public ZedSuite/WinOLS JSON export shape,
as a `maps`/`Maps` list or a bare array, with dotted or nested fields. The adapter
requires contiguous storage, integer dimensions, supported DataOrg and bounded
ROM axes. Unknown/unsupported maps are skipped with explicit reasons. It does not
infer a license or certify software compatibility. Display mirror flags are
preserved as metadata; OpenCal uses raw row-major order rather than reproducing
WinOLS display preferences. It does not translate CPU addresses to file offsets:
out-of-bounds definitions are rejected. The original source JSON is retained in
each imported map for auditability. There is no proprietary WinOLS code involved.

Signatures require `family`, `name`, `address`, nonempty `hex`, `source`, `license`.
Exact bytes at the address produce an evidence-bearing match, not calibrated ECU
support. Short signatures can collide; contributors should use strong identifying
regions and independent reference samples. No signature database is shipped.

## Projects

`.ocproj` is JSON with schema `opencal.project`, version 1. Base64 original and
modified bytes have equal lengths and separate SHA-256 digests. Source path is
informational and protected against writes. Definitions, event history, undo/redo
patches and base64 calibration profiles are embedded. No executable objects,
pickle, remote fetch or code plugins. Corrupt digests and wrong profile sizes fail
loading. Original data is embedded, so reopening does not depend on a source path.
SHA-256 is an integrity check, not authentication against intentional tampering.

## Export/audit

Exports create a new BIN and `.audit.json` with schema `opencal.audit`, version 1,
hashes, changed ranges, history, identity evidence and computed ECU checksum status
(matched/mismatch/unverified). Matching includes the selected algorithm and
per-region evidence, and does not certify the whole ECU image. Existing files are not overwritten. A source BIN is never saved
in place. Project saves use a same-directory temporary file plus atomic replace.
Projects may be overwritten after the normal save dialog; keep external backups.
BIN and sidecar creation cannot be one filesystem transaction; a process/power
failure could leave an incomplete pair. Check hashes after unexpected interruption.
