"""Map editor: colored table, axis rows, edit tools, 2D/3D graph."""
from __future__ import annotations

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from ..core import maps as M
from ..core import units as U
from ..core.ecufile import EcuFile
from . import theme

try:
    import pyqtgraph as pg
    pg.setConfigOptions(antialias=True, background="#161a20", foreground="#8b94a3")
except Exception:  # pragma: no cover
    pg = None

try:
    import pyqtgraph.opengl as gl
    HAVE_GL = True
except Exception:  # pragma: no cover
    gl = None
    HAVE_GL = False


def heat(t: float) -> QtGui.QColor:
    """Blue -> green -> red, t in 0..1."""
    t = 0.0 if np.isnan(t) else min(max(t, 0.0), 1.0)
    stops = [(0.0, (58, 110, 214)), (0.3, (42, 160, 170)), (0.5, (78, 186, 108)),
             (0.72, (226, 186, 70)), (1.0, (226, 82, 72))]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if t <= b:
            k = (t - a) / (b - a)
            return QtGui.QColor(*[int(ca[i] + (cb[i] - ca[i]) * k) for i in range(3)])
    return QtGui.QColor(*stops[-1][1])


class MapModel(QtCore.QAbstractTableModel):
    """Row 0..R-1 = data rows. Headers are the axis breakpoints."""

    edited = QtCore.Signal()

    def __init__(self, f: EcuFile, m: M.Map, decimals: int = 2):
        super().__init__()
        self.f, self.m = f, m
        self.decimals = decimals
        self.compare: np.ndarray | None = None   # original values for Δ
        self.show_delta = False
        self.overlay = None                      # logs.Overlay
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        self.vc = U.conv(self.m.unit)
        self.xc = U.conv(self.m.row_axis.unit) if self.m.row_axis else None
        self.yc = U.conv(self.m.col_axis.unit)
        self.vals = self.vc.to_shown(self.m.values(self.f.buf))
        self.orig = self.vc.to_shown(self.m.values(self.f.original))
        rng = (float(np.nanmin(self.vals)), float(np.nanmax(self.vals)))
        self.lo, self.hi = rng if rng[1] > rng[0] else (rng[0] - 1, rng[0] + 1)
        self.xv = self.xc.to_shown(self.m.row_axis.values(self.f.buf)) if self.m.row_axis else None
        self.yv = self.yc.to_shown(self.m.col_axis.values(self.f.buf))
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return self.m.rows

    def columnCount(self, parent=QtCore.QModelIndex()):
        return self.m.cols

    def fmt(self, v):
        if abs(v - round(v)) < 1e-9 and abs(v) >= 100:
            return f"{v:.0f}"
        return f"{v:.{self.decimals}f}".rstrip("0").rstrip(".") if self.decimals else f"{v:.0f}"

    def data(self, idx, role=Qt.DisplayRole):
        if not idx.isValid():
            return None
        v = float(self.vals[idx.row(), idx.column()])
        o = float(self.orig[idx.row(), idx.column()])
        if role in (Qt.DisplayRole, Qt.EditRole):
            if self.show_delta and role == Qt.DisplayRole:
                return f"{(v - o) / o * 100:+.1f}%" if o else ("0" if v == o else "new")
            return self.fmt(v)
        if role == Qt.BackgroundRole:
            return QtGui.QBrush(heat((v - self.lo) / (self.hi - self.lo)))
        if role == Qt.ForegroundRole:
            return QtGui.QBrush(QtGui.QColor("#0b0d12"))
        if role == Qt.FontRole:
            f = QtGui.QFont()
            if abs(v - o) > 1e-9:
                f.setBold(True)
                f.setUnderline(True)
            return f
        if role == Qt.ToolTipRole:
            tip = f"value {self.fmt(v)} {self.m.unit}\noriginal {self.fmt(o)}"
            if self.overlay is not None:
                c = int(self.overlay.counts[idx.row(), idx.column()])
                mval = self.overlay.mean[idx.row(), idx.column()]
                tip += f"\nlog samples {c}" + (f", logged mean {mval:.1f}" if not np.isnan(mval) else "")
            return tip
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        return None

    def headerData(self, s, orient, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orient == Qt.Horizontal:
            return self.fmt(float(self.yv[s]))
        if self.xv is None:
            return ""
        return self.fmt(float(self.xv[s]))

    def flags(self, idx):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable

    def setData(self, idx, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False
        try:
            v = float(str(value).replace(",", "."))
        except ValueError:
            return False
        new = self.vals.copy()
        new[idx.row(), idx.column()] = v
        self.f.write_map(self.m, self.vc.to_native(new), f"{self.m.label()}: cell ({idx.row()},{idx.column()}) = {v:g} {self.vc.shown}")
        return True


class AxisDialog(QtWidgets.QDialog):
    def __init__(self, f: EcuFile, m: M.Map, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit axes")
        lay = QtWidgets.QFormLayout(self)
        self.f, self.m = f, m
        self.edits = []
        for ax, label in ((m.row_axis, "Rows"), (m.col_axis, "Columns")):
            if ax is None:
                continue
            c = U.conv(ax.unit)
            le = QtWidgets.QLineEdit(" ".join(f"{v:g}" for v in c.to_shown(ax.values(f.buf))))
            shared = sum(1 for o in f.maps if (o.x.address == ax.address) or (o.y and o.y.address == ax.address))
            lay.addRow(f"{label}: {ax.name or 'axis'} [{c.shown}] (shared by {shared} maps)", le)
            self.edits.append((ax, le))
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.apply)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def apply(self):
        with self.f.begin() as tx:
            for ax, le in self.edits:
                try:
                    vals = [float(x) for x in le.text().replace(",", ".").split()]
                except ValueError:
                    QtWidgets.QMessageBox.warning(self, "Axes", "Numbers separated by spaces.")
                    return
                if len(vals) != ax.count:
                    QtWidgets.QMessageBox.warning(self, "Axes", f"{ax.count} values needed.")
                    return
                if not (np.all(np.diff(vals) >= 0) or np.all(np.diff(vals) <= 0)):
                    QtWidgets.QMessageBox.warning(self, "Axes", "Breakpoints must be in order.")
                    return
                raw = ax.to_raw(U.conv(ax.unit).to_native(np.asarray(vals, float)))
                tx.write(ax.address, (raw & 0xFFFF).astype("<u2").tobytes(), "axis edited")
        self.accept()


class MapEditor(QtWidgets.QWidget):
    status = QtCore.Signal(str)

    def __init__(self, f: EcuFile, m: M.Map, parent=None):
        super().__init__(parent)
        self.f, self.m = f, m
        self.clip: np.ndarray | None = None
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)

        # header: name + chips
        hdr = QtWidgets.QHBoxLayout()
        title = theme.label(m.label(), "h2")
        hdr.addWidget(title)
        for chip in self.chips():
            hdr.addWidget(theme.label(chip, "chip"))
        hdr.addStretch()
        self.delta = QtWidgets.QCheckBox("Show change %")
        self.delta.toggled.connect(self.toggle_delta)
        hdr.addWidget(self.delta)
        v.addLayout(hdr)
        if m.description:
            d = theme.label(m.description, "muted")
            d.setWordWrap(True)
            v.addWidget(d)

        # toolbar: value operation | table tools | view
        bar = QtWidgets.QFrame(objectName="Card")
        tb = QtWidgets.QHBoxLayout(bar)
        tb.setContentsMargins(8, 6, 8, 6)
        tb.setSpacing(6)
        self.op = QtWidgets.QComboBox()
        self.op.addItems(["Set value", "+ amount", "- amount", "× percent", "Set % of original"])
        self.amount = QtWidgets.QDoubleSpinBox()
        self.amount.setRange(-1e6, 1e6)
        self.amount.setDecimals(3)
        self.amount.setMinimumWidth(90)
        apply_b = QtWidgets.QPushButton("Apply to selection")
        theme.role(apply_b, "primary")
        apply_b.clicked.connect(self.apply_op)
        for w_ in (self.op, self.amount, apply_b):
            tb.addWidget(w_)
        tb.addSpacing(10)
        for text, tip, fn in (("Interpolate", "Linear between the selection's ends", self.interpolate),
                              ("Smooth", "Average each cell with its neighbours", self.smooth),
                              ("Copy", "Ctrl+C", self.copy), ("Paste", "Ctrl+V", self.paste),
                              ("Restore", "Back to the original values", self.restore),
                              ("Axes…", "Edit breakpoints (shared axes update everywhere)", self.edit_axes)):
            b_ = QtWidgets.QPushButton(text)
            b_.setToolTip(tip)
            theme.role(b_, "ghost")
            b_.clicked.connect(fn)
            tb.addWidget(b_)
        tb.addStretch()
        self.view3d = QtWidgets.QToolButton()
        self.view3d.setText("3D surface")
        self.view3d.setCheckable(True)
        self.view3d.setEnabled(m.is3d and HAVE_GL)
        self.view3d.toggled.connect(self.update_graph)
        tb.addWidget(self.view3d)
        v.addWidget(bar)
        hint = theme.label("Double-click or type to edit · +/− step · PgUp/PgDn ×10 · select cells, then Apply", "muted")
        v.addWidget(hint)

        split = QtWidgets.QSplitter(Qt.Vertical)
        self.table = QtWidgets.QTableView()
        self.model = MapModel(f, m)
        self.table.setModel(self.model)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.AnyKeyPressed
                                   | QtWidgets.QAbstractItemView.EditKeyPressed)
        self.table.installEventFilter(self)
        self.table.setFont(theme.mono(9))
        self.table.setShowGrid(True)
        self.table.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        split.addWidget(self.table)

        self.graph_box = QtWidgets.QStackedWidget()
        if pg is not None:
            self.plot = pg.PlotWidget()
            self.plot.showGrid(x=True, y=True, alpha=0.25)
            self.graph_box.addWidget(self.plot)
        if HAVE_GL and m.is3d:
            self.gl = gl.GLViewWidget()
            self.gl.setBackgroundColor("#161a20")
            self.gl.setCameraPosition(distance=40, elevation=28, azimuth=-60)
            self.graph_box.addWidget(self.gl)
        split.addWidget(self.graph_box)
        split.setSizes([500, 260])
        v.addWidget(split, 1)

        self._listener = lambda _f: self.reload()
        f.listeners.append(self._listener)
        self.update_graph()

    def closeEvent(self, e):
        self.detach()
        super().closeEvent(e)

    def detach(self):
        if self._listener in self.f.listeners:
            self.f.listeners.remove(self._listener)

    def chips(self) -> list[str]:
        m = self.m
        out = [f"0x{m.address:05X}", f"{m.rows} × {m.cols}"]
        if m.codeblock is not None:
            out.append(f"codeblock {m.codeblock}")
        if m.row_axis is not None:
            out.append(f"rows: {m.row_axis.name or 'axis'} {U.conv(m.row_axis.unit).shown}".strip())
        out.append(f"cols: {m.col_axis.name or 'axis'} {U.conv(m.col_axis.unit).shown}".strip())
        out.append(U.conv(m.unit).shown or "raw")
        return out

    def describe(self) -> str:
        m = self.m
        parts = [f"0x{m.address:05X}", f"{m.rows}×{m.cols}"]
        if m.codeblock is not None:
            parts.append(f"codeblock {m.codeblock}")
        if m.row_axis is not None:
            parts.append(f"rows: {m.row_axis.name or 'axis'} {m.row_axis.unit}")
        parts.append(f"cols: {m.col_axis.name or 'axis'} {m.col_axis.unit}")
        parts.append(f"value: {m.unit or 'raw'}")
        s = " · ".join(parts)
        if m.description:
            s += "\n" + m.description
        return s

    # ---------------------------------------------------------- refresh --
    def reload(self):
        self.model.refresh()
        self.update_graph()

    def toggle_delta(self, on):
        self.model.show_delta = on
        self.model.refresh()

    def update_graph(self):
        if pg is None:
            return
        vals = self.model.vals
        if self.view3d.isChecked() and HAVE_GL and self.m.is3d:
            self.graph_box.setCurrentWidget(self.gl)
            for it in list(self.gl.items):
                self.gl.removeItem(it)
            z = vals.astype(float)
            span = float(z.max() - z.min()) or 1.0
            zn = (z - z.min()) / span * 10
            xs = np.linspace(0, 20, z.shape[0])
            ys = np.linspace(0, 20, z.shape[1])
            colors = np.array([[heat(t).redF(), heat(t).greenF(), heat(t).blueF(), 1.0]
                               for t in ((z - z.min()) / span).ravel()]).reshape(z.shape + (4,))
            surf = gl.GLSurfacePlotItem(x=xs, y=ys, z=zn, colors=colors, shader=None, smooth=False,
                                        drawEdges=True, edgeColor=(0.1, 0.1, 0.1, 1))
            surf.translate(-10, -10, -5)
            self.gl.addItem(surf)
            g = gl.GLGridItem()
            g.setSize(24, 24)
            g.translate(0, 0, -5)
            self.gl.addItem(g)
            return
        self.graph_box.setCurrentWidget(self.plot)
        self.plot.clear()
        self.plot.addLegend(offset=(-10, 10))
        xs = self.model.yv
        n = vals.shape[0]
        for i in range(n):
            c = heat(i / max(n - 1, 1))
            name = self.model.fmt(float(self.model.xv[i])) if self.model.xv is not None else None
            self.plot.plot(xs, vals[i], pen=pg.mkPen(c, width=2), symbol="o", symbolSize=4,
                           symbolBrush=c, symbolPen=None, name=name if n <= 16 else None)
            if not np.array_equal(vals[i], self.model.orig[i]):
                self.plot.plot(xs, self.model.orig[i], pen=pg.mkPen(c, width=1, style=Qt.DashLine))
        self.plot.setLabel("bottom", f"{self.m.col_axis.name} {self.model.yc.shown}")
        self.plot.setLabel("left", self.model.vc.shown or "value")

    # -------------------------------------------------------- selection --
    def selected(self) -> list[tuple[int, int]]:
        idx = self.table.selectionModel().selectedIndexes()
        return [(i.row(), i.column()) for i in idx]

    def _apply(self, fn, note):
        cells = self.selected()
        if not cells:
            self.table.selectAll()
            cells = self.selected()
        vals = self.model.vals.copy()
        new = fn(vals, cells)
        if new is not None:
            self.f.write_map(self.m, self.model.vc.to_native(new), f"{self.m.label()}: {note} ({len(cells)} cells)")
            self.status.emit(f"{note}: {len(cells)} cells")

    def apply_op(self):
        op, a = self.op.currentText(), self.amount.value()
        orig = self.model.orig

        def fn(v, cells):
            for r, c in cells:
                if op == "Set value":
                    v[r, c] = a
                elif op == "+ amount":
                    v[r, c] += a
                elif op == "- amount":
                    v[r, c] -= a
                elif op == "× percent":
                    v[r, c] *= 1 + a / 100
                else:
                    v[r, c] = orig[r, c] * a / 100
            return v
        self._apply(fn, f"{op} {a:g}")

    def interpolate(self):
        def fn(v, cells):
            rows = sorted({r for r, _ in cells})
            cols = sorted({c for _, c in cells})
            r0, r1, c0, c1 = rows[0], rows[-1], cols[0], cols[-1]
            if c1 > c0:
                for r in range(r0, r1 + 1):
                    v[r, c0:c1 + 1] = np.linspace(v[r, c0], v[r, c1], c1 - c0 + 1)
            elif r1 > r0:
                v[r0:r1 + 1, c0] = np.linspace(v[r0, c0], v[r1, c0], r1 - r0 + 1)
            return v
        self._apply(fn, "interpolated")

    def smooth(self):
        def fn(v, cells):
            src = v.copy()
            for r, c in cells:
                r0, r1 = max(r - 1, 0), min(r + 2, v.shape[0])
                c0, c1 = max(c - 1, 0), min(c + 2, v.shape[1])
                v[r, c] = src[r0:r1, c0:c1].mean()
            return v
        self._apply(fn, "smoothed")

    def copy(self):
        cells = self.selected() or [(r, c) for r in range(self.m.rows) for c in range(self.m.cols)]
        rows = sorted({r for r, _ in cells})
        cols = sorted({c for _, c in cells})
        block = self.model.vals[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
        self.clip = block.copy()
        QtWidgets.QApplication.clipboard().setText(
            "\n".join("\t".join(self.model.fmt(float(x)) for x in row) for row in block))
        self.status.emit(f"copied {block.shape[0]}×{block.shape[1]}")

    def paste(self):
        text = QtWidgets.QApplication.clipboard().text()
        try:
            block = np.array([[float(x.replace(",", ".")) for x in line.split("\t") if x.strip()]
                              for line in text.strip().splitlines()])
        except ValueError:
            self.status.emit("clipboard holds no numbers")
            return
        cells = self.selected()
        r0 = min((r for r, _ in cells), default=0)
        c0 = min((c for _, c in cells), default=0)
        v = self.model.vals.copy()
        h = min(block.shape[0], v.shape[0] - r0)
        w = min(block.shape[1] if block.ndim == 2 else 0, v.shape[1] - c0)
        if h <= 0 or w <= 0:
            return
        v[r0:r0 + h, c0:c0 + w] = block[:h, :w]
        self.f.write_map(self.m, self.model.vc.to_native(v), f"{self.m.label()}: pasted {h}×{w}")

    def restore(self):
        self.f.restore_map(self.m)

    def edit_axes(self):
        if AxisDialog(self.f, self.m, self).exec():
            self.reload()

    def eventFilter(self, obj, ev):
        if obj is self.table and ev.type() == QtCore.QEvent.KeyPress:
            k = ev.key()
            step = {Qt.Key_Plus: 1, Qt.Key_Minus: -1, Qt.Key_PageUp: 10, Qt.Key_PageDown: -10}.get(k)
            if step is not None and ev.modifiers() in (Qt.NoModifier, Qt.KeypadModifier):
                unit = (abs(self.m.factor) or 1) / self.model.vc.f
                self._apply(lambda v, cells: _bump(v, cells, step * unit), f"{'+' if step > 0 else ''}{step} step")
                return True
            if ev.matches(QtGui.QKeySequence.Copy):
                self.copy()
                return True
            if ev.matches(QtGui.QKeySequence.Paste):
                self.paste()
                return True
        return super().eventFilter(obj, ev)

    def set_overlay(self, ov):
        self.model.overlay = ov
        self.model.refresh()


def _bump(v, cells, d):
    for r, c in cells:
        v[r, c] += d
    return v
