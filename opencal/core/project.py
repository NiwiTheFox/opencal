"""Projects: a folder with every saved version of a file plus notes.

    <projects>/<name>/
        project.json      name, created, notes, versions[]
        v000.bin          the original read (never changed)
        v001.bin ...      saved versions
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil

DEFAULT_ROOT = os.path.join(os.path.expanduser("~"), "Documents", "OpenEDC", "projects")


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _slug(s: str) -> str:
    s = re.sub(r"[^\w\- .]+", "_", s).strip()
    return s[:80] or "project"


class Project:
    def __init__(self, folder: str):
        self.folder = folder
        with open(os.path.join(folder, "project.json"), encoding="utf-8") as fh:
            self.meta = json.load(fh)

    # --------------------------------------------------------- creation --
    @classmethod
    def create(cls, bin_path: str, root: str = DEFAULT_ROOT, name: str | None = None) -> "Project":
        name = name or os.path.splitext(os.path.basename(bin_path))[0]
        os.makedirs(root, exist_ok=True)
        folder = os.path.join(root, _slug(name))
        n = 2
        while os.path.exists(folder):
            folder = os.path.join(root, f"{_slug(name)} ({n})")
            n += 1
        os.makedirs(folder)
        shutil.copyfile(bin_path, os.path.join(folder, "v000.bin"))
        meta = {"name": name, "created": _now(), "source": os.path.abspath(bin_path), "notes": [],
                "versions": [{"file": "v000.bin", "label": "Original read", "time": _now()}]}
        with open(os.path.join(folder, "project.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=1)
        return cls(folder)

    @staticmethod
    def list(root: str = DEFAULT_ROOT) -> list["Project"]:
        out = []
        if not os.path.isdir(root):
            return out
        for d in os.listdir(root):
            p = os.path.join(root, d)
            if os.path.isfile(os.path.join(p, "project.json")):
                try:
                    out.append(Project(p))
                except (OSError, ValueError):
                    pass
        return sorted(out, key=lambda p: p.meta.get("created", ""), reverse=True)

    # ----------------------------------------------------------- access --
    @property
    def name(self) -> str:
        return self.meta["name"]

    @property
    def versions(self) -> list[dict]:
        return self.meta["versions"]

    def path_of(self, index: int) -> str:
        return os.path.join(self.folder, self.versions[index]["file"])

    @property
    def latest_path(self) -> str:
        return self.path_of(len(self.versions) - 1)

    @property
    def original_path(self) -> str:
        return self.path_of(0)

    def _save(self):
        tmp = os.path.join(self.folder, "project.json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.meta, fh, indent=1)
        os.replace(tmp, os.path.join(self.folder, "project.json"))

    def add_version(self, data: bytes, label: str, changes: list[str] | None = None,
                    checksum: str = "") -> int:
        idx = len(self.versions)
        fn = f"v{idx:03d}.bin"
        with open(os.path.join(self.folder, fn), "wb") as fh:
            fh.write(data)
        self.versions.append({"file": fn, "label": label or f"Version {idx}", "time": _now(),
                              "changes": changes or [], "checksum": checksum})
        self._save()
        return idx

    def add_note(self, text: str) -> None:
        self.meta["notes"].append({"time": _now(), "text": text})
        self._save()

    def rename(self, name: str) -> None:
        self.meta["name"] = name
        self._save()

    def backup(self, dest_zip: str) -> str:
        base = os.path.splitext(dest_zip)[0]
        return shutil.make_archive(base, "zip", self.folder)
