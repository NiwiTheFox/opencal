# Reference source review — 19 October 2026

The original public [Blackfrosch/VAGEDCSuite](https://github.com/Blackfrosch/VAGEDCSuite)
snapshot at `31fd822a333ed8424439e89800f210639c57c7bb` and the maintained
[skaldamramra/VAGEDCSuite](https://github.com/skaldamramra/VAGEDCSuite) fork at
`9689a8527f55659fa0e51cede724f4c9fb57ace4` were downloaded for read-only research.
Neither snapshot establishes parity with the supplied VAG EDC+ Suite v0.2.58 EXE.

Findings checked in source:

- `EDC15PFileParser.cs`, `CheckCodeBlock`: codeblock IDs are read through firmware
  metadata pointers. They are not simply the ordinal of a flash bank. OpenCal's
  bounded reader is adapted from the already-retained GPL ZedSuite `layout.rs`.
- `LaunchControlService.cs` constructs speed-axis words before calling the binary
  writer. `Tools.cs`, `savedatatobinary`, swaps endian order for EDC15. Comparing
  the intermediate array alone would therefore misrepresent the bytes on disk.
- The old parser includes map naming, axis layouts, selectors, checksum code and
  launch-control table recognition. These are useful candidates for further
  independent comparisons on copied files.
- No generic ECU multimap-switching implementation was located by the targeted
  search of these snapshots. That is not evidence that switching cannot exist in
  another fork or firmware.

The maintained fork includes GPL version 3 license text. The older snapshot has
no root license grant identified during this review; no code from it was added
to OpenCal. No proprietary UI libraries, paid-module code or firmware was copied.
The checked-out source repositories remain development references outside the
public OpenCal package.
