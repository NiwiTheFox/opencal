"""Only user-authorised working copies; never analyze original J: firmware."""
from pathlib import Path
WORK=Path(__file__).resolve().parents[2]/'to use'
STOCK=WORK/'stock-038906019FJ'/'codex 38906019FJ-SG  1376 ori.bin'
V9=WORK/'v9-038906019FJ'/'codex V9 MY CAR 96 DTC Disabled.bin'
