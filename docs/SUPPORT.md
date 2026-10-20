# EDC15 coverage

OpenCal detects calibration layouts, not a guaranteed P/P+/P++ marketing or hardware classification. No claim of complete family support is made. This release expands support across the app rather than restricting the whole application to one part number.

| Feature | Standard V4.1 | Compact V4.1 | Early 32 KiB blocks |
|---|---|---|---|
| Identity and bounded codeblocks | Yes | Yes | Structural candidate |
| Map/axis editing, hex, projects, comparisons | Yes | Yes | Yes |
| Automatic map names | Bounded source patterns and sequences | Bounded source patterns and early shape/value classifier | Partial shape/value classifier |
| Checksum verification | TDI41 2002 | TDI41v2 | Unverified |
| Checksum correction | Matching valid original required | Matching valid original required | Unavailable |
| DTC editing | Classic records | Shared fault paths | Unavailable |
| Exact DTC enable/restore | Known enabled original or checked stock reference | Entire original shared path, including unused classes | Unavailable |
| ORI mappack relocation | Checked standard banks | Not yet | Not yet |
| Launch-control solution | Checked standard layouts | Not yet | Not yet |
| EGR solution | FJ exact profile plus guarded structural request-map layouts | Not yet | Not yet |

Map names remain candidates. Different injection systems can share structural layouts; matching a header does not establish the meaning of every map. Unknown layouts can still use hex editing and explicit imported definitions. Shared-path DTC toggles affect all codes on that path; the UI labels this explicitly. Individual error classes cannot be matched safely to triplets, so OpenCal restores the entire known original path.

The available 100-image corpus contains 90 standard, six compact and one early layout; three images are outside these layouts. Checksums are matched in 78, mismatched in 18 and unverified in four images. DTC tables are supported in 96. These are local byte-level observations, not exhaustive hardware or vehicle validation. EDC15C/M/V/VM variants without the supported structures need further implementation and independent fixtures. A size or part number alone does not enable an algorithm.
