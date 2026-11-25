"""Assemble C166/C167 source with the bundled, hash-pinned AS (asw/p2bin)."""
from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "tools" / "c166-as"
PINNED = {"asw.exe": "95e7b654977971a479631db55720edeb75aa483dde441ffc30c24169809c124a",
          "p2bin.exe": "a874c5aabe1abd6b1d3530a49b6d7ad03a8bedca9a9356d94a0fc15743726256"}


class AsmError(Exception):
    pass


def _check_tools(engine: Path):
    for name, sha in PINNED.items():
        p = engine / name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            raise AsmError(f"Bundled assembler missing or modified: {name}")


def assemble(source: str, origin: int, cpu: str = "80c167", engine: Path = ENGINE) -> bytes:
    """Return the bytes for ``source`` placed at CPU address ``origin``.

    Lines starting at column one followed by ``:`` are labels; other lines are
    indented automatically (AS treats column-one words as labels).
    """
    _check_tools(engine)
    lines = []
    for line in source.splitlines():
        s = line.rstrip()
        if not s.strip():
            continue
        head = s.strip().split(";")[0]
        if ":" in head.split()[0] if head.split() else False:
            lines.append(s.strip())
        else:
            lines.append("        " + s.strip())
    text = f"        cpu {cpu}\n        org 0{origin:X}h\n" + "\n".join(lines) + "\n"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with tempfile.TemporaryDirectory(prefix="opencal-asm-") as d:
        d = Path(d)
        (d / "p.asm").write_text(text, encoding="utf-8")
        for args in ([str(engine / "asw.exe"), "p.asm", "-o", "p.p", "-q", "-gnuerrors", "-n", "-L"],
                     [str(engine / "p2bin.exe"), "p.p", "p.bin", "-q"]):
            r = subprocess.run(args, cwd=d, shell=False, capture_output=True, text=True, timeout=30, creationflags=flags)
            if r.returncode:
                raise AsmError((r.stdout + r.stderr)[-4000:])
        data = (d / "p.bin").read_bytes()
    # p2bin writes from the lowest address; for org > 0 it starts at origin
    return data
