# 0.9.1 source audit

Inspected the supplied ZedSuite master and both VAGEDCSuite source archives. Corresponding GPL sources, original notices and SHA256 manifests are retained under third_party. The audit adds bounded layout detection, compact TDI41v2 checksums, complete shared fault-path DTC operations and early/compact map classification. All operations preserve original files and use the shared document/Undo model.

The standard and compact arithmetic routines matched 128 synthetic vectors each against independently compiled C# routines from the supplied source. Those 256 vectors are public test fixtures, generated from artificial data. No user firmware or reference exports are published. The existing independent TypeScript golden vector remains covered.

Regression defects fixed: partial checksum calculation rounds could read beyond their selected range; DTC evidence was counted globally rather than per bank; overlapping classic DTC candidates could pass; smoke selectors did not validate their index words; and map-tree rebuilds lost keyboard focus. Selector validation retains source-supported repeated and 0x40 index values. Existing checked stock-map addresses remain preserved.

Fresh copies of 180 authorised files (100 unique images) were made before analysis. Original standard-layout corpus checks exercised 11,709 candidate maps and 31,306 diagnostic records. Expanded support is reported in SUPPORT.md. Unsupported early checksums and unknown diagnostic layouts remain explicit. No tune quality, emissions behaviour or ECU execution is established by these checks.

The supplied Ghidra source archive was inventoried. It contains no bundled C166 language definition; the separately researched MIT C166 module can serve as an independent reference. OpenCal will not require Ghidra/Java to be installed.
