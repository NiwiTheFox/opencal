"""Build the self-contained Windows executable with PyInstaller.

    python tools/build_exe.py

Produces dist/OpenCal-<version>-win64.exe (single file, Python, Qt, numpy,
pyqtgraph, pyserial and data bundled) and dist/OpenCal-<version>-win64.zip
(portable folder build, starts faster).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from opencal import __version__  # noqa: E402

EXCLUDES = ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
            "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
            "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtDataVisualization",
            "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSensors", "PySide6.QtLocation",
            "PySide6.QtPositioning", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
            "tkinter", "matplotlib", "scipy", "pandas", "IPython", "PyQt5", "PyQt6"]


def make_icon(path: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from opencal.gui import theme
    theme.save_ico(str(path))
    del app


def version_file(path: Path) -> None:
    parts = (__version__.split(".") + ["0"] * 4)[:4]
    nums = ", ".join(str(int(p)) for p in parts)
    path.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({nums}), prodvers=({nums})),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'OpenCal contributors'),
    StringStruct('FileDescription', 'OpenCal - free EDC15P/V calibration editor'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('InternalName', 'OpenCal'),
    StringStruct('LegalCopyright', 'GPL-3.0-only, OpenCal contributors'),
    StringStruct('OriginalFilename', 'OpenCal.exe'),
    StringStruct('ProductName', 'OpenCal'),
    StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""", encoding="utf-8")


def run(onefile: bool, build: Path, icon: Path, ver: Path) -> Path:
    sep = ";" if os.name == "nt" else ":"
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
            "--name", "OpenCal", "--icon", str(icon), "--version-file", str(ver),
            "--distpath", str(build / ("one" if onefile else "dir")), "--workpath", str(build / "work"),
            "--specpath", str(build),
            "--add-data", f"{ROOT / 'opencal' / 'legacy' / 'data'}{sep}opencal/legacy/data",
            "--add-data", f"{ROOT / 'LICENSE'}{sep}.", "--add-data", f"{ROOT / 'NOTICE'}{sep}.",
            "--collect-submodules", "pyqtgraph", "--hidden-import", "OpenGL.platform.win32",
            "--hidden-import", "serial.tools.list_ports"]
    for x in EXCLUDES:
        args += ["--exclude-module", x]
    args.append("--onefile" if onefile else "--onedir")
    args.append(str(ROOT / "tools" / "entry.py"))
    subprocess.check_call(args, cwd=ROOT)
    return build / ("one" if onefile else "dir")


def main() -> None:
    build = ROOT / "build"
    dist = ROOT / "dist"
    build.mkdir(exist_ok=True)
    dist.mkdir(exist_ok=True)
    icon = build / "opencal.ico"
    ver = build / "version.txt"
    make_icon(icon)
    version_file(ver)
    one = run(True, build, icon, ver)
    exe = dist / f"OpenCal-{__version__}-win64.exe"
    shutil.copyfile(one / "OpenCal.exe", exe)
    folder = run(False, build, icon, ver) / "OpenCal"
    for extra in ("README.md", "CHANGELOG.md", "LICENSE", "NOTICE"):
        shutil.copyfile(ROOT / extra, folder / extra)
    z = shutil.make_archive(str(dist / f"OpenCal-{__version__}-win64"), "zip", folder.parent, "OpenCal")
    print(exe, exe.stat().st_size // 1024 // 1024, "MB")
    print(z)


if __name__ == "__main__":
    main()
