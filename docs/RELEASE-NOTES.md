# OpenCal 0.5

## 0.5 Solutions

The Solutions tab inspects supported standard EDC15 launch-control structures. Preview enable shows the exact 30-byte speed-axis changes per matching bank. Apply changes only the project in memory, with one-step undo across all banks. Restore original writes the exact loaded original axis; it does not guess a factory state. Generated launch-control map definitions follow the current bytes through undo/redo. Output bytes match the supplied GPL TypeScript source for stock and V9 fixtures. The source accepts two active header encodings; OpenCal writes canonical little-endian. All structures are bank-bounded and RPM-checked. No vehicle execution testing has occurred. This is not ECU multimap switching.

51 unit/integration/widget tests pass. Exact external TypeScript oracle hashes are in the private development report; stock and all three V9 banks match. Native 0.4 layout/scalar navigation inspected; launcher starts a Python-owned window (the launcher itself exits).
