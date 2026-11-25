"""Datalogs (VCDS CSV and generic CSV) and overlaying them on maps."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

import numpy as np

# Column guesses: (channel, header keywords, unit keywords)
CHANNELS = {
    "rpm": (("engine speed", "rpm", "drehzahl"), ("/min", "rpm")),
    "iq": (("injected quantity", "injection quantity", "einspritzmenge", "iq"), ("mg/h", "mg/str", "mg/st")),
    "maf": (("air mass", "mass air", "luftmasse", "maf"), ("mg/h", "mg/str", "mg/st")),
    "boost": (("boost", "charge pressure", "ladedruck", "intake manifold"), ("mbar",)),
    "boost_spec": (("specified", "soll", "target"), ("mbar",)),
    "pedal": (("accelerator", "pedal", "throttle"), ("%",)),
    "soi": (("start of injection", "timing", "spritzbeginn"), ("°", "kw", "btdc")),
    "n75": (("duty", "n75", "tastverh"), ("%",)),
}


@dataclass
class Log:
    columns: dict[str, np.ndarray] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    source: str = ""

    def __len__(self):
        return min((len(v) for v in self.columns.values()), default=0)


def _num(s: str) -> float:
    s = s.strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def load_csv(path: str) -> Log:
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    return parse_csv(text, path)


def parse_csv(text: str, source: str = "") -> Log:
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        counts = {d: text[:4096].count(d) for d in ",;\t"}
        delim = max(counts, key=counts.get)
        dialect = type("D", (csv.excel,), {"delimiter": delim})
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if any(c.strip() for c in r)]
    # header block: the last rows before numeric data begins
    first_num = next((i for i, r in enumerate(rows) if sum(1 for c in r if _is_num(c)) >= max(2, len(r) // 2)), None)
    if first_num is None:
        return Log(source=source)
    hdr = rows[max(0, first_num - 3):first_num]
    ncol = max(len(r) for r in rows[first_num:first_num + 5])
    labels = []
    for c in range(ncol):
        parts = [h[c].strip() for h in hdr if c < len(h) and h[c].strip()]
        labels.append(" ".join(parts).lower())
    data = np.array([[_num(r[c]) if c < len(r) else np.nan for c in range(ncol)] for r in rows[first_num:]])
    log = Log(source=source)
    used = set()
    for ch, (keys, units) in CHANNELS.items():
        best = None
        for c, lab in enumerate(labels):
            if c in used:
                continue
            score = sum(2 for k in keys if k in lab) + sum(1 for u in units if u in lab)
            if ch == "boost" and any(k in lab for k in CHANNELS["boost_spec"][0]):
                score -= 3
            if score >= 2 and (best is None or score > best[0]):
                best = (score, c)
        if best:
            used.add(best[1])
            log.columns[ch] = data[:, best[1]]
            log.names[ch] = labels[best[1]]
    return log


def _is_num(s: str) -> bool:
    return not np.isnan(_num(s)) if s.strip() else False


@dataclass
class Overlay:
    counts: np.ndarray
    mean: np.ndarray            # mean of the logged value per cell (nan = none)


def overlay(log: Log, xvals, yvals, xch: str, ych: str, vch: str | None = None) -> Overlay:
    """Bin samples to the nearest map cell (rows x, cols y)."""
    xv, yv = np.asarray(xvals, float), np.asarray(yvals, float)
    counts = np.zeros((len(xv), len(yv)), int)
    sums = np.zeros_like(counts, float)
    if xch not in log.columns or ych not in log.columns:
        return Overlay(counts, np.full(counts.shape, np.nan))
    xs, ys = log.columns[xch], log.columns[ych]
    vs = log.columns.get(vch) if vch else None
    for k in range(len(xs)):
        if np.isnan(xs[k]) or np.isnan(ys[k]):
            continue
        i = int(np.argmin(np.abs(xv - xs[k])))
        j = int(np.argmin(np.abs(yv - ys[k])))
        counts[i, j] += 1
        if vs is not None and not np.isnan(vs[k]):
            sums[i, j] += vs[k]
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)
    return Overlay(counts, mean)
