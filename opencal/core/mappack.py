"""Map definitions in and out: TunerPro XDF and a plain JSON mappack."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from . import maps as M
from .ecufile import EcuFile

SCHEMA = "openedc.mappack/1"


# ------------------------------------------------------------------ JSON --

def export_json(f: EcuFile, path: str, only_identified: bool = False) -> int:
    out = []
    for m in f.maps:
        if only_identified and not m.identified:
            continue
        out.append(_map_to_dict(m))
    doc = {"schema": SCHEMA, "software": f.info.software, "part_number": f.info.part_number,
           "maps": out}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    return len(out)


def _axis_to_dict(ax: M.Axis | None):
    if ax is None:
        return None
    return {"address": ax.address, "count": ax.count, "id": ax.id, "factor": ax.factor,
            "offset": ax.offset, "name": ax.name, "unit": ax.unit, "signed": ax.signed}


def _map_to_dict(m: M.Map):
    return {"name": m.label(), "kind": m.kind, "category": m.category, "address": m.address,
            "rows": m.rows, "cols": m.cols, "factor": m.factor, "offset": m.offset,
            "unit": m.unit, "signed": m.signed, "x": _axis_to_dict(m.x), "y": _axis_to_dict(m.y),
            "description": m.description}


def import_json(f: EcuFile, path: str) -> tuple[int, int]:
    """Apply names/scaling from a mappack. Returns (added_or_named, skipped)."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    items = doc.get("maps", doc if isinstance(doc, list) else [])
    added = skipped = 0
    for it in items:
        try:
            addr = int(it["address"], 0) if isinstance(it["address"], str) else int(it["address"])
        except (KeyError, ValueError, TypeError):
            skipped += 1
            continue
        rows, cols = int(it.get("rows", 1)), int(it.get("cols", 1))
        if addr < 0 or addr + 2 * rows * cols > len(f.buf):
            skipped += 1
            continue
        m = f.map(f"{addr:05X}")
        if m is None or (m.rows, m.cols) != (rows, cols):
            m = _build_map(f, addr, rows, cols, it)
            if m is None:
                skipped += 1
                continue
            f.maps.append(m)
            f._by_key[m.key] = m
        m.name = it.get("name") or m.name
        m.category = it.get("category") or "Imported (JSON)"
        m.factor = float(it.get("factor", m.factor))
        m.offset = float(it.get("offset", m.offset))
        m.unit = it.get("unit", m.unit)
        m.kind = it.get("kind") or m.kind
        m.description = it.get("description", m.description)
        for ax, spec in ((m.x, it.get("x")), (m.y, it.get("y"))):
            if ax is not None and isinstance(spec, dict):
                ax.factor = float(spec.get("factor", ax.factor))
                ax.offset = float(spec.get("offset", ax.offset))
                ax.name = spec.get("name", ax.name)
                ax.unit = spec.get("unit", ax.unit)
        m.identified = True
        added += 1
    f.maps.sort(key=lambda m: m.address)
    return added, skipped


def _build_map(f, addr, rows, cols, it) -> M.Map | None:
    def ax(spec, n):
        if isinstance(spec, dict) and "address" in spec:
            return M.Axis(int(spec.get("id", 0)), int(spec["address"]), int(spec.get("count", n)))
        return M.Axis(0, addr, n)  # synthetic axis: index only
    if rows > 1:
        x = ax(it.get("x"), rows)
        y = ax(it.get("y"), cols)
        return M.Map(addr, x, y, bank=M.bank_of(addr))
    x = ax(it.get("y") or it.get("x"), cols)
    return M.Map(addr, x, None, bank=M.bank_of(addr))


# ------------------------------------------------------------------- XDF --

def _math(factor, offset):
    return f"X*{factor!r}+{offset!r}" if offset else f"X*{factor!r}"


def export_xdf(f: EcuFile, path: str, only_identified: bool = True) -> int:
    root = ET.Element("XDFFORMAT", version="1.60")
    hdr = ET.SubElement(root, "XDFHEADER")
    ET.SubElement(hdr, "flags").text = "0x1"
    ET.SubElement(hdr, "title").text = f"{f.info.part_number} {f.info.software} (OpenEDC)"
    ET.SubElement(hdr, "BASEOFFSET", offset="0", subtract="0")
    ET.SubElement(hdr, "DEFAULTS", datasizeinbits="16", sigdigits="2", outputtype="1",
                  signed="0", lsbfirst="1", float="0")
    ET.SubElement(hdr, "REGION", type="0xFFFFFFFF", startaddress="0x0", size=hex(len(f.buf)),
                  regionflags="0x0", name="Binary File", desc="")
    n = 0
    for m in f.maps:
        if only_identified and not m.identified:
            continue
        t = ET.SubElement(root, "XDFTABLE", uniqueid=f"0x{m.address:X}", flags="0x0")
        ET.SubElement(t, "title").text = m.label()
        ET.SubElement(t, "description").text = m.description
        for axname, ax, count in (("x", m.col_axis, m.cols), ("y", m.row_axis, m.rows)):
            a = ET.SubElement(t, "XDFAXIS", id=axname, uniqueid="0x0")
            if ax is not None:
                ET.SubElement(a, "EMBEDDEDDATA", mmedtypeflags="0x02" if ax.signed else "0x00",
                              mmedaddress=f"0x{ax.address:X}", mmedelementsizebits="16",
                              mmedmajorstridebits="0", mmedminorstridebits="0")
            ET.SubElement(a, "indexcount").text = str(count)
            ET.SubElement(a, "units").text = ax.unit if ax else ""
            ET.SubElement(a, "embedinfo", type="1")
            ET.SubElement(a, "MATH", equation=_math(ax.factor, ax.offset) if ax else "X")
        z = ET.SubElement(t, "XDFAXIS", id="z")
        ET.SubElement(z, "EMBEDDEDDATA", mmedtypeflags="0x02" if m.signed else "0x00",
                      mmedaddress=f"0x{m.address:X}", mmedelementsizebits="16",
                      mmedrowcount=str(m.rows), mmedcolcount=str(m.cols),
                      mmedmajorstridebits="0", mmedminorstridebits="0")
        ET.SubElement(z, "units").text = m.unit
        ET.SubElement(z, "decimalpl").text = "2"
        ET.SubElement(z, "MATH", equation=_math(m.factor, m.offset))
        n += 1
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return n


def _parse_eq(eq: str) -> tuple[float, float] | None:
    """Parse linear X*a+b / (X*a)+b / X/a style equations."""
    s = eq.replace(" ", "").replace("(", "").replace(")", "")
    try:
        factor, offset = 1.0, 0.0
        body = s
        if "+" in s[1:] or "-" in s[1:]:
            idx = max(s.rfind("+"), s.rfind("-"))
            body, off = s[:idx], s[idx:]
            offset = float(off)
        if body == "X":
            return factor, offset
        if body.startswith("X*"):
            factor = float(body[2:])
        elif body.startswith("X/"):
            factor = 1.0 / float(body[2:])
        elif body.endswith("*X"):
            factor = float(body[:-2])
        else:
            return None
        return factor, offset
    except ValueError:
        return None


def import_xdf(f: EcuFile, path: str) -> tuple[int, int]:
    tree = ET.parse(path)
    added = skipped = 0
    base = 0
    bo = tree.find(".//XDFHEADER/BASEOFFSET")
    if bo is not None:
        try:
            base = int(bo.get("offset", "0"), 0) * (-1 if bo.get("subtract") == "1" else 1)
        except ValueError:
            base = 0
    for t in tree.iter("XDFTABLE"):
        title = (t.findtext("title") or "").strip()
        z = next((a for a in t.findall("XDFAXIS") if a.get("id") == "z"), None)
        if z is None or z.find("EMBEDDEDDATA") is None:
            skipped += 1
            continue
        ed = z.find("EMBEDDEDDATA")
        bits = int(ed.get("mmedelementsizebits", "8"))
        if bits != 16:
            skipped += 1
            continue
        try:
            addr = int(ed.get("mmedaddress"), 0) + base
            rows = int(ed.get("mmedrowcount", "1"))
            cols = int(ed.get("mmedcolcount", "1"))
        except (TypeError, ValueError):
            skipped += 1
            continue
        if addr < 0 or addr + 2 * rows * cols > len(f.buf):
            skipped += 1
            continue
        mt = z.find("MATH")
        fo = _parse_eq(mt.get("equation", "X")) if mt is not None else (1.0, 0.0)
        if fo is None:
            fo = (1.0, 0.0)
        axes = {}
        for a in t.findall("XDFAXIS"):
            if a.get("id") in ("x", "y"):
                e = a.find("EMBEDDEDDATA")
                am = a.find("MATH")
                axes[a.get("id")] = {
                    "address": (int(e.get("mmedaddress"), 0) + base) if e is not None and e.get("mmedaddress") else None,
                    "count": int(a.findtext("indexcount") or 1),
                    "eq": _parse_eq(am.get("equation", "X")) if am is not None else (1.0, 0.0),
                    "unit": a.findtext("units") or "",
                }
        item = {"address": addr, "rows": rows, "cols": cols, "name": title or f"XDF {addr:05X}",
                "category": "Imported (XDF)", "factor": fo[0], "offset": fo[1],
                "unit": z.findtext("units") or "",
                "description": t.findtext("description") or ""}
        for key, src in (("y", "x"), ("x", "y")):   # XDF x = columns, ours y = columns
            ax = axes.get(src)
            if ax and ax["address"] is not None:
                eq = ax["eq"] or (1.0, 0.0)
                item[key] = {"address": ax["address"], "count": ax["count"], "factor": eq[0],
                             "offset": eq[1], "unit": ax["unit"]}
        tmp = f"{path}.json.tmp"
        try:
            _apply_items(f, [item])
            added += 1
        except Exception:
            skipped += 1
    f.maps.sort(key=lambda m: m.address)
    return added, skipped


def _apply_items(f, items):
    import tempfile
    import os
    fd, p = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"maps": items}, fh)
        import_json(f, p)
    finally:
        os.remove(p)
