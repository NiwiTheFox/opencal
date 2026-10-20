# OpenCal 0.9.1 — EDC15 coverage and correctness audit

Development preview. Extract the complete Windows ZIP and run OpenCal.exe. Python and Tcl/Tk are bundled.

## Changes

- Recognise standard, compact and early EDC15 layouts with bounded codeblocks and candidate identification; no invented P/P+/P++ completeness claim.
- Add compact-layout maps/axis editing and grouping, early/compact shape/value classification, TDI41v2 checksum verification/correction, and shared fault-path DTC disable/exact restore.
- Expand EGR request-map previews beyond the FJ-only profile when bounded axis shapes, values, identities, diagnostics and all-bank topology agree.
- Reject incomplete/overlapping classic DTC tables, invalid smoke selectors and partial checksum rounds; preserve map-browser keyboard focus and scroll.
- Retain existing map comparisons, project persistence, all-bank controls and reversible editing. Mouse disclosure behaviour is unchanged.

## Validation

256 synthetic arithmetic vectors match independently compiled supplied VAGEDCSuite C# routines, alongside the existing TypeScript golden vectors. Added regressions cover complete compact layouts, shared fault-path effects, exact restoration, malformed padding, early map classification, structural EGR relocation and preservation/Undo. Local corpus: 180 copied files, 100 unique; 97 recognised map layouts, 96 supported checksum/DTC layouts. See AUDIT-0.9.1.md and SUPPORT.md.

## Known limitations

Support is feature/layout-specific, not complete for all EDC15P/P+/P++ software. Early checksums/DTCs, compact ORI relocation, compact launch-control and compact EGR automation remain unsupported. Correction requires a valid matching original checksum baseline. Detection names are candidates; vehicle execution is unverified. Matching checksums do not make a tune ready to flash. Windows x64 requires the whole extracted folder and has not been checked in a clean VM. C166 tools arrive in 1.0.0.
