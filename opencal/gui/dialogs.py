"""Dialogs for tools, calculators, EEPROM, hex, ECU."""
from __future__ import annotations

import time

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from ..core import calcs as C
from ..core import kline as K
from ..core import logs as L
from ..core import patterns as P
from ..core import tuning as T
from ..core.ecufile import EcuFile, EcuFileError
from ..core.eeprom import Eeprom, EepromError

try:
    import pyqtgraph as pg
except Exception:  # pragma: no cover
    pg = None


def _bb(dlg, ok="OK", cancel=True):
    bb = QtWidgets.QDialogButtonBox()
    b = bb.addButton(ok, QtWidgets.QDialogButtonBox.AcceptRole)
    if cancel:
        bb.addButton(QtWidgets.QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    return bb


class TextReport(QtWidgets.QDialog):
    def __init__(self, title, html, parent=None, w=640, h=460):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(w, h)
        v = QtWidgets.QVBoxLayout(self)
        t = QtWidgets.QTextBrowser()
        t.setOpenExternalLinks(True)
        t.setHtml(html)
        v.addWidget(t)
        v.addWidget(_bb(self, "Close", cancel=False))


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------------------------------------ file info --

def info_html(f: EcuFile) -> str:
    rep = f.checksum()
    rows = [("File", f.name), ("Part number", f.info.part_number), ("Software", f.info.software),
            ("Bosch number", f.info.bosch_number), ("Info", f.info.description),
            ("ECU type", f.info.ecu_type),
            ("Checksum", rep.summary() if rep else "no known layout"),
            ("Maps", f"{len(f.maps)} tables, {sum(m.identified for m in f.maps)} named")]
    for cb in f.codeblocks:
        rows.append((f"Bank {cb.base >> 16:X}xxxx",
                     f"codeblock {cb.id} · {cb.gearbox or '?'}" if cb.populated else "empty"))
    for s in P.find_scalars(f.buf):
        rows.append((s.name, f"{s.value(f.buf):g} {s.unit}  @0x{s.address:05X}"))
    return "<table cellpadding=4>" + "".join(f"<tr><td style='color:#8a93a3'>{esc(a)}</td><td><b>{esc(b)}</b></td></tr>" for a, b in rows) + "</table>"


def checks_html(findings) -> str:
    color = {"ok": "#3ecf6e", "warning": "#f0b429", "error": "#ff5b5b"}
    return "".join(f"<p><span style='color:{color[x.level]}'>●</span> {esc(x.text)}</p>" for x in findings)


# --------------------------------------------------------- stage 1 plan --

class Stage1Dialog(QtWidgets.QDialog):
    def __init__(self, f: EcuFile, parent=None):
        super().__init__(parent)
        self.f = f
        self.setWindowTitle("Auto Stage 1")
        self.resize(620, 520)
        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel("Generate a conservative Stage 1 base map from this file's own calibration. "
                                     "Not a dyno tune: verify with logs."))
        form = QtWidgets.QFormLayout()
        self.gain = self._spin(15, 0, 35, " %")
        self.maxiq = self._spin(52, 30, 80, " mg/st")
        self.boost = self._spin(150, 0, 500, " mbar")
        self.cap = self._spin(2450, 1500, 3000, " mbar")
        self.lam = QtWidgets.QDoubleSpinBox()
        self.lam.setRange(1.0, 2.0)
        self.lam.setSingleStep(0.05)
        self.lam.setValue(1.20)
        self.bank = QtWidgets.QComboBox()
        for cb in f.populated_banks:
            self.bank.addItem(f"codeblock {cb.id} ({cb.base >> 16:X}xxxx)", cb.base)
        idx = self.bank.findData(f.active_bank)
        self.bank.setCurrentIndex(max(idx, 0))
        form.addRow("Extra fuel at full load", self.gain)
        form.addRow("Fuel ceiling", self.maxiq)
        form.addRow("Extra boost", self.boost)
        form.addRow("Boost cap (MAP sensor)", self.cap)
        form.addRow("Smoke limit λ ≥", self.lam)
        form.addRow("Bank", self.bank)
        v.addLayout(form)
        b = QtWidgets.QPushButton("Make plan")
        b.clicked.connect(self.make)
        v.addWidget(b)
        self.out = QtWidgets.QTextBrowser()
        v.addWidget(self.out, 1)
        self.apply_b = QtWidgets.QPushButton("Apply plan")
        self.apply_b.setEnabled(False)
        self.apply_b.clicked.connect(self.apply)
        v.addWidget(self.apply_b)
        self.plan = None

    def _spin(self, val, lo, hi, suf):
        s = QtWidgets.QSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setSuffix(suf)
        return s

    def make(self):
        p = T.Stage1Params(self.gain.value() / 100, self.maxiq.value(), self.boost.value(), self.cap.value(),
                           self.lam.value(), self.bank.currentData())
        self.plan = T.plan_stage1(self.f, p)
        html = f"<p><b>{len(self.plan.changes)} change(s)</b></p><ul>"
        for c in self.plan.changes:
            old = c.map.values(self.f.buf)
            new = c.new_raw * c.map.factor + c.map.offset
            html += f"<li>{esc(c.summary)} — peak {old.max():.1f} → {new.max():.1f} {esc(c.map.unit)}</li>"
        html += "</ul>" + "".join(f"<p style='color:#f0b429'>{esc(n)}</p>" for n in self.plan.notes)
        self.out.setHtml(html)
        self.apply_b.setEnabled(bool(self.plan.changes))

    def apply(self):
        try:
            T.apply_plan(self.f, self.plan)
        except EcuFileError as e:
            QtWidgets.QMessageBox.warning(self, "Auto Stage 1", str(e))
            return
        self.accept()


# ----------------------------------------------------------- codeblocks --

class CodeblockDialog(QtWidgets.QDialog):
    """Copy / clear banks, set ids, prepare multimap by coding."""

    def __init__(self, f: EcuFile, parent=None):
        super().__init__(parent)
        self.f = f
        self.setWindowTitle("Codeblocks and multimap")
        self.resize(640, 420)
        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel(
            "Each bank holds a full calibration (codeblock). The ECU runs the codeblock whose id matches its coding.\n"
            "Multimap by coding: fill the empty banks with copies, tune each, then pick the map by changing the "
            "coding (VCDS 01 › 07). Check on your car which coding selects which id before relying on it."))
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Bank", "State", "Codeblock id", "Gearbox"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        v.addWidget(self.table)
        row = QtWidgets.QHBoxLayout()
        for text, fn in (("Fill empty banks (multimap)", self.multimap), ("Copy bank…", self.copy),
                         ("Set id…", self.set_id), ("Empty bank…", self.clear), ("Repair bank", self.repair)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        v.addLayout(row)
        v.addWidget(_bb(self, "Close", cancel=False))
        self.refresh()

    def refresh(self):
        self.table.setRowCount(0)
        for cb in self.f.codeblocks:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, t in enumerate((f"0x{cb.start:05X}–0x{cb.end - 1:05X}", "calibration" if cb.populated else "empty",
                                   "" if cb.id is None else str(cb.id), cb.gearbox)):
                it = QtWidgets.QTableWidgetItem(t)
                it.setData(Qt.UserRole, cb.base)
                self.table.setItem(r, c, it)

    def _sel(self):
        it = self.table.currentItem()
        return it.data(Qt.UserRole) if it else None

    def multimap(self):
        used = {cb.id for cb in self.f.codeblocks if cb.id is not None}
        ids, nxt = {}, 1
        for cb in self.f.codeblocks:
            if not cb.populated:
                while nxt in used:
                    nxt += 1
                ids[cb.base] = nxt
                used.add(nxt)
        filled = T.prepare_multimap(self.f, ids)
        self.refresh()
        QtWidgets.QMessageBox.information(self, "Multimap",
                                          f"Filled {len(filled)} bank(s) with the current calibration. "
                                          "Tune each bank's maps; checksums are fixed on save.")

    def copy(self):
        dst = self._sel()
        if dst is None:
            return
        srcs = [cb for cb in self.f.populated_banks if cb.base != dst]
        if not srcs:
            return
        names = [f"codeblock {cb.id} ({cb.base >> 16:X}xxxx)" for cb in srcs]
        name, ok = QtWidgets.QInputDialog.getItem(self, "Copy bank", "Copy from", names, 0, False)
        if ok:
            src = srcs[names.index(name)].base
            dst_cb = next(cb for cb in self.f.codeblocks if cb.base == dst)
            keep = dst_cb.id
            T.copy_codeblock(self.f, src, dst, keep)
            self.refresh()

    def set_id(self):
        base = self._sel()
        if base is None:
            return
        n, ok = QtWidgets.QInputDialog.getInt(self, "Codeblock id", "id", 1, 0, 255)
        if ok:
            try:
                T.set_codeblock_id(self.f, base, n)
            except EcuFileError as e:
                QtWidgets.QMessageBox.warning(self, "Codeblock id", str(e))
            self.refresh()

    def clear(self):
        base = self._sel()
        if base is None or base == self.f.active_bank:
            return
        if QtWidgets.QMessageBox.question(self, "Empty bank", f"Empty bank {base >> 16:X}xxxx? (undoable)") == QtWidgets.QMessageBox.Yes:
            T.clear_codeblock(self.f, base)
            self.refresh()

    def repair(self):
        base = self._sel()
        if base is None:
            return
        fixed = T.repair_bank(self.f, base)
        QtWidgets.QMessageBox.information(self, "Repair bank", f"{len(fixed)} empty map(s) copied from the main bank.")


# --------------------------------------------------------------- EEPROM --

class EepromDialog(QtWidgets.QDialog):
    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.ee = Eeprom.load(path)
        self.setWindowTitle(f"EEPROM editor — {path}")
        form = QtWidgets.QFormLayout(self)
        self.immo = QtWidgets.QCheckBox("Immobiliser active")
        self.immo.setChecked(self.ee.immo_active)
        self.vin = QtWidgets.QLineEdit(self.ee.vin)
        self.vin.setMaxLength(17)
        self.immo_id = QtWidgets.QLineEdit(self.ee.immo_id)
        self.immo_id.setMaxLength(14)
        self.skc = QtWidgets.QSpinBox()
        self.skc.setRange(0, 65535)
        self.skc.setValue(self.ee.skc)
        form.addRow(self.immo)
        form.addRow("VIN", self.vin)
        form.addRow("Immobiliser ID (14 ch)", self.immo_id)
        form.addRow("Login / SKC code", self.skc)
        form.addRow("Mileage", QtWidgets.QLabel(f"{self.ee.mileage_km:,.0f} km"))
        form.addRow(QtWidgets.QLabel("Saving writes a copy you choose; the original dump is kept."))
        form.addRow(_bb(self, "Save as…"))

    def accept(self):
        try:
            self.ee.set_immo(self.immo.isChecked())
            if self.vin.text() != self.ee.vin:
                self.ee.set_vin(self.vin.text())
            if self.immo_id.text() != self.ee.immo_id:
                self.ee.set_immo_id(self.immo_id.text())
            self.ee.set_skc(self.skc.value())
        except EepromError as e:
            QtWidgets.QMessageBox.warning(self, "EEPROM", str(e))
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save EEPROM", self.ee.path.replace(".bin", "_mod.bin"),
                                                        "EEPROM (*.bin *.eep)")
        if path:
            self.ee.save(path)
            super().accept()


# ------------------------------------------------------------------ hex --

class HexView(QtWidgets.QDialog):
    def __init__(self, f: EcuFile, start: int = 0, parent=None):
        super().__init__(parent)
        self.f = f
        self.setWindowTitle("Hex viewer")
        self.resize(820, 600)
        v = QtWidgets.QVBoxLayout(self)
        h = QtWidgets.QHBoxLayout()
        self.addr = QtWidgets.QLineEdit(f"{start:05X}")
        go = QtWidgets.QPushButton("Go")
        go.clicked.connect(self.render)
        self.diff = QtWidgets.QCheckBox("highlight changes")
        self.diff.setChecked(True)
        self.diff.toggled.connect(self.render)
        h.addWidget(QtWidgets.QLabel("Address 0x"))
        h.addWidget(self.addr)
        h.addWidget(go)
        h.addWidget(self.diff)
        h.addStretch()
        v.addLayout(h)
        self.text = QtWidgets.QTextBrowser()
        self.text.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        v.addWidget(self.text)
        self.render()

    def render(self):
        try:
            a0 = int(self.addr.text(), 16) & ~0xF
        except ValueError:
            return
        buf, orig = self.f.buf, self.f.original
        lines = []
        for a in range(a0, min(a0 + 0x400, len(buf)), 16):
            hx = []
            for i in range(16):
                b = buf[a + i]
                s = f"{b:02X}"
                if self.diff.isChecked() and b != orig[a + i]:
                    s = f"<span style='background:#7a2a2a'>{s}</span>"
                hx.append(s)
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in buf[a:a + 16])
            lines.append(f"<span style='color:#8a93a3'>{a:05X}</span>  {' '.join(hx)}  {esc(asc)}")
        self.text.setHtml("<pre style='font-size:10pt'>" + "\n".join(lines) + "</pre>")


# -------------------------------------------------------- calculators ---

class CalcDialog(QtWidgets.QDialog):
    def __init__(self, f: EcuFile | None, parent=None):
        super().__init__(parent)
        self.f = f
        self.setWindowTitle("Calculators")
        self.resize(760, 560)
        tabs = QtWidgets.QTabWidget()
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(tabs)
        tabs.addTab(self._afr_tab(), "AFR from boost")
        tabs.addTab(self._power_tab(), "Power / torque")
        tabs.addTab(self._eoi_tab(), "EOI")
        tabs.addTab(self._turbo_tab(), "Turbo fit")

    # engine spec shared
    def _spec_form(self, form):
        self.disp = QtWidgets.QDoubleSpinBox(); self.disp.setRange(0.5, 6); self.disp.setDecimals(3); self.disp.setValue(1.896)
        self.cyl = QtWidgets.QSpinBox(); self.cyl.setRange(1, 12); self.cyl.setValue(4)
        self.ve = QtWidgets.QDoubleSpinBox(); self.ve.setRange(0.5, 1.2); self.ve.setValue(0.92)
        self.amb = QtWidgets.QDoubleSpinBox(); self.amb.setRange(-30, 50); self.amb.setValue(20)
        for lbl, w in (("Displacement (L)", self.disp), ("Cylinders", self.cyl), ("Volumetric eff.", self.ve), ("Ambient °C", self.amb)):
            form.addRow(lbl, w)

    def spec(self) -> C.EngineSpec:
        return C.EngineSpec(self.disp.value(), self.cyl.value(), self.ve.value(), ambient_c=self.amb.value())

    def _afr_tab(self):
        w = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(w)
        self._spec_form(form)
        self.boost = QtWidgets.QSpinBox(); self.boost.setRange(900, 3500); self.boost.setValue(2200); self.boost.setSuffix(" mbar abs")
        self.iq = QtWidgets.QDoubleSpinBox(); self.iq.setRange(1, 100); self.iq.setValue(45); self.iq.setSuffix(" mg/st")
        form.addRow("Boost", self.boost)
        form.addRow("Fuel", self.iq)
        out = QtWidgets.QLabel()
        form.addRow(out)

        def calc():
            e = self.spec()
            air = C.air_mg_per_stroke(self.boost.value(), e)
            t = C.charge_temp_c(self.boost.value(), e)
            out.setText(f"Charge {t:.0f} °C · air {air:.0f} mg/st · AFR {C.afr(air, self.iq.value()):.1f}:1 · "
                        f"λ {C.lam(air, self.iq.value()):.2f}\nFuel at λ 1.20: {C.iq_for_lambda(air, 1.2):.1f} mg · "
                        f"at λ 1.30: {C.iq_for_lambda(air, 1.3):.1f} mg")
        for s in (self.boost, self.iq, self.disp, self.cyl, self.ve, self.amb):
            s.valueChanged.connect(calc)
        calc()
        return w

    def _power_tab(self):
        w = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(w)
        iq = QtWidgets.QDoubleSpinBox(); iq.setRange(1, 100); iq.setValue(45)
        rpm = QtWidgets.QSpinBox(); rpm.setRange(500, 6000); rpm.setValue(4000)
        k = QtWidgets.QDoubleSpinBox(); k.setRange(2, 10); k.setValue(5.3); k.setSingleStep(0.1)
        out = QtWidgets.QLabel()
        form.addRow("Fuel (mg/st)", iq)
        form.addRow("Engine speed (rpm)", rpm)
        form.addRow("Nm per mg (1.9 PD ≈ 5.3)", k)
        form.addRow(out)

        def calc():
            t = iq.value() * k.value()
            out.setText(f"≈ {t:.0f} Nm · {C.power_hp(t, rpm.value()):.0f} hp ({C.power_hp(t, rpm.value()) * 0.7355:.0f} kW)")
        for s in (iq, rpm, k):
            s.valueChanged.connect(calc)
        calc()
        return w

    def _eoi_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addWidget(QtWidgets.QLabel("End of injection = start of injection − injection duration (PD TDI). "
                                     "Positive = BTDC. Read from the file; nothing is written."))
        h = QtWidgets.QHBoxLayout()
        soi = QtWidgets.QSpinBox(); soi.setRange(0, 20); soi.setValue(6); soi.setPrefix("SOI map ")
        dur = QtWidgets.QSpinBox(); dur.setRange(0, 10); dur.setValue(1); dur.setPrefix("duration map ")
        h.addWidget(soi); h.addWidget(dur); h.addStretch()
        v.addLayout(h)
        table = QtWidgets.QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["rpm", "IQ mg/st", "EOI °BTDC"])
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        v.addWidget(table)

        def calc():
            table.setRowCount(0)
            if self.f is None:
                return
            rows = T.eoi_table(self.f, None, soi.value(), dur.value()) or []
            for rpm, iq, e in rows:
                r = table.rowCount()
                table.insertRow(r)
                for c, val in enumerate((f"{rpm:.0f}", f"{iq:.1f}", f"{e:+.1f}")):
                    it = QtWidgets.QTableWidgetItem(val)
                    if c == 2 and e < -15:
                        it.setForeground(QtGui.QColor("#ff5b5b"))
                    table.setItem(r, c, it)
        soi.valueChanged.connect(calc)
        dur.valueChanged.connect(calc)
        calc()
        return w

    def _turbo_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addWidget(QtWidgets.QLabel("Approximate compressor envelopes. Each rpm gets the most boost the picked turbo can "
                                     "hold there, never above the boost target."))
        combo = QtWidgets.QComboBox()
        combo.addItems(list(C.TURBOS))
        v.addWidget(combo)
        table = QtWidgets.QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["rpm", "target mbar", "fits mbar"])
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        v.addWidget(table)

        def calc():
            table.setRowCount(0)
            if self.f is None:
                return
            bt = self.f.first("boost_target", self.f.active_bank)
            if bt is None:
                return
            rpms = bt.x.values(self.f.buf)
            target = bt.values(self.f.buf).max(axis=1)
            fit = C.fit_boost_curve(C.TURBOS[combo.currentText()], rpms, target, self.spec())
            for rpm, t, ft in zip(rpms, target, fit):
                r = table.rowCount()
                table.insertRow(r)
                for c, val in enumerate((f"{rpm:.0f}", f"{t:.0f}", "—" if ft is None else f"{ft:.0f}")):
                    it = QtWidgets.QTableWidgetItem(val)
                    if c == 2 and ft is not None and ft < t - 1:
                        it.setForeground(QtGui.QColor("#f0b429"))
                    table.setItem(r, c, it)
        combo.currentIndexChanged.connect(calc)
        calc()
        return w


# ------------------------------------------------------------------ dyno --

class DynoDialog(QtWidgets.QDialog):
    def __init__(self, f: EcuFile, parent=None):
        super().__init__(parent)
        self.f = f
        self.setWindowTitle("Virtual dyno (estimate)")
        self.resize(860, 560)
        v = QtWidgets.QVBoxLayout(self)
        h = QtWidgets.QHBoxLayout()
        self.bank = QtWidgets.QComboBox()
        for cb in f.populated_banks:
            self.bank.addItem(f"codeblock {cb.id}", cb.base)
        self.bank.setCurrentIndex(max(self.bank.findData(f.active_bank), 0))
        self.k = QtWidgets.QDoubleSpinBox(); self.k.setRange(2, 10); self.k.setValue(5.3); self.k.setPrefix("Nm/mg ")
        self.cmp = QtWidgets.QCheckBox("show original")
        self.cmp.setChecked(True)
        for w in (self.bank, self.k, self.cmp):
            h.addWidget(w)
            (w.currentIndexChanged if isinstance(w, QtWidgets.QComboBox) else
             w.valueChanged if isinstance(w, QtWidgets.QDoubleSpinBox) else w.toggled).connect(self.run)
        h.addStretch()
        v.addLayout(h)
        v.addWidget(QtWidgets.QLabel("Full load from the calibration: per rpm the lowest of driver wish, torque limiter "
                                     "and smoke limiter (at the boost target's airflow). An estimate, not a measurement."))
        if pg is not None:
            self.plot = pg.PlotWidget()
            self.plot.showGrid(x=True, y=True, alpha=0.25)
            self.plot.addLegend()
            v.addWidget(self.plot, 1)
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["rpm", "IQ", "boost", "Nm", "hp", "limited by"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.setMaximumHeight(200)
        v.addWidget(self.table)
        self.run()

    def run(self):
        e = C.EngineSpec(nm_per_mg=self.k.value())
        pts = C.virtual_dyno(self.f, self.bank.currentData(), e)
        self.table.setRowCount(0)
        for p in pts:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, val in enumerate((f"{p.rpm:.0f}", f"{p.iq:.1f}", f"{p.boost:.0f}", f"{p.torque:.0f}",
                                     f"{p.power:.0f}", p.limiter)):
                self.table.setItem(r, c, QtWidgets.QTableWidgetItem(val))
        if pg is None:
            return
        self.plot.clear()
        rp = [p.rpm for p in pts]
        self.plot.plot(rp, [p.torque for p in pts], pen=pg.mkPen("#4aa3ff", width=3), name="Torque Nm")
        self.plot.plot(rp, [p.power for p in pts], pen=pg.mkPen("#ff6b4a", width=3), name="Power hp")
        if self.cmp.isChecked():
            orig = EcuFile(self.f.original)
            po = C.virtual_dyno(orig, orig.active_bank, e)
            self.plot.plot([p.rpm for p in po], [p.torque for p in po], pen=pg.mkPen("#4aa3ff", width=1, style=Qt.DashLine), name="original Nm")
            self.plot.plot([p.rpm for p in po], [p.power for p in po], pen=pg.mkPen("#ff6b4a", width=1, style=Qt.DashLine), name="original hp")
        if pts:
            pk = max(pts, key=lambda p: p.power)
            pt = max(pts, key=lambda p: p.torque)
            self.setWindowTitle(f"Virtual dyno — ≈{pk.power:.0f} hp @ {pk.rpm:.0f}, {pt.torque:.0f} Nm @ {pt.rpm:.0f}")


# ---------------------------------------------------------- log overlay --

class LogDialog(QtWidgets.QDialog):
    overlay_ready = QtCore.Signal(object)

    def __init__(self, f: EcuFile, path: str, parent=None):
        super().__init__(parent)
        self.f = f
        self.log = L.load_csv(path)
        self.setWindowTitle(f"Log analysis — {path}")
        self.resize(760, 540)
        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel(f"{len(self.log)} samples. Channels found: " +
                                     ", ".join(f"{k} ← “{n}”" for k, n in self.log.names.items())))
        h = QtWidgets.QHBoxLayout()
        self.mapsel = QtWidgets.QComboBox()
        for m in f.maps:
            if m.identified and m.is3d:
                self.mapsel.addItem(m.label(), m.key)
        self.xch = QtWidgets.QComboBox(); self.ych = QtWidgets.QComboBox(); self.vch = QtWidgets.QComboBox()
        chans = list(self.log.columns)
        self.xch.addItems(chans); self.ych.addItems(chans); self.vch.addItems(["(none)"] + chans)
        if "rpm" in chans:
            self.xch.setCurrentText("rpm")
        if "iq" in chans:
            self.ych.setCurrentText("iq")
        for w, lbl in ((self.mapsel, "map"), (self.xch, "rows ←"), (self.ych, "cols ←"), (self.vch, "value")):
            h.addWidget(QtWidgets.QLabel(lbl))
            h.addWidget(w)
        b = QtWidgets.QPushButton("Overlay")
        b.clicked.connect(self.run)
        h.addWidget(b)
        v.addLayout(h)
        self.out = QtWidgets.QTableView()
        v.addWidget(self.out, 1)
        if pg is not None and "rpm" in self.log.columns:
            p = pg.PlotWidget()
            p.addLegend()
            t = np.arange(len(self.log))
            for i, (k, arr) in enumerate(self.log.columns.items()):
                p.plot(t, arr, pen=pg.mkPen(pg.intColor(i), width=1.5), name=k)
            p.setMaximumHeight(200)
            v.addWidget(p)

    def run(self):
        m = self.f.map(self.mapsel.currentData())
        if m is None:
            return
        vch = None if self.vch.currentText() == "(none)" else self.vch.currentText()
        ov = L.overlay(self.log, m.x.values(self.f.buf), m.y.values(self.f.buf), self.xch.currentText(),
                       self.ych.currentText(), vch)
        model = QtGui.QStandardItemModel(m.rows, m.cols)
        vals = m.values(self.f.buf)
        mx = max(int(ov.counts.max()), 1)
        for r in range(m.rows):
            for c in range(m.cols):
                n = int(ov.counts[r, c])
                txt = f"{vals[r, c]:.1f}" + (f"\n{ov.mean[r, c]:.1f}" if vch and n else "")
                it = QtGui.QStandardItem(txt)
                g = int(255 - 180 * n / mx)
                it.setBackground(QtGui.QColor(g, g, 255) if n else QtGui.QColor("#22262e"))
                it.setForeground(QtGui.QColor("#000" if n else "#8a93a3"))
                model.setItem(r, c, it)
        self.out.setModel(model)
        self.overlay_ready.emit((m.key, ov))


# ------------------------------------------------------------------ ECU --

class EcuDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ECU (K-line diagnostics)")
        self.resize(720, 520)
        self.session: K.Session | None = None
        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel(
            "KKL / FTDI cable, ignition on. Identification, fault codes and live measuring blocks over KWP2000.\n"
            "Flash read/write and live tuning are not in this version: they need a bootloader path that can't be "
            "tested safely here. Use your flasher (MPPS, Galletto) for reading and writing."))
        h = QtWidgets.QHBoxLayout()
        self.port = QtWidgets.QComboBox()
        self.port.addItems(K.list_ports() + ["Simulator"])
        self.port.setEditable(True)
        h.addWidget(QtWidgets.QLabel("Port"))
        h.addWidget(self.port)
        for text, fn in (("Connect", self.connect_ecu), ("Read faults", self.read_dtc), ("Clear faults", self.clear_dtc),
                         ("Disconnect", self.disconnect_ecu)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(fn)
            h.addWidget(b)
        v.addLayout(h)
        h2 = QtWidgets.QHBoxLayout()
        self.group = QtWidgets.QSpinBox(); self.group.setRange(1, 255); self.group.setValue(1); self.group.setPrefix("group ")
        self.live = QtWidgets.QPushButton("Live data")
        self.live.setCheckable(True)
        self.live.toggled.connect(self.toggle_live)
        self.rec = QtWidgets.QPushButton("Save log…")
        self.rec.clicked.connect(self.save_log)
        for w in (self.group, self.live, self.rec):
            h2.addWidget(w)
        h2.addStretch()
        v.addLayout(h2)
        self.out = QtWidgets.QTextBrowser()
        v.addWidget(self.out, 1)
        self.values = QtWidgets.QLabel()
        self.values.setStyleSheet("font-size:16pt")
        v.addWidget(self.values)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.rows: list[list[str]] = []

    def say(self, s):
        self.out.append(esc(s))

    def connect_ecu(self):
        try:
            p = self.port.currentText()
            tr = K.SimulatedEcu() if p == "Simulator" else K.SerialTransport(p)
            self.session = K.Session(tr)
            self.session.connect()
            self.say("Connected. ECU: " + self.session.identify())
        except Exception as e:
            self.session = None
            self.say(f"Failed: {e}")

    def read_dtc(self):
        if not self.session:
            return self.say("Not connected.")
        try:
            d = self.session.read_dtcs()
            self.say(f"{len(d)} fault(s): " + ", ".join(f"{c} (status 0x{s:02X})" for c, s in d) if d else "No faults stored.")
        except Exception as e:
            self.say(f"Failed: {e}")

    def clear_dtc(self):
        if not self.session:
            return self.say("Not connected.")
        try:
            self.session.clear_dtcs()
            self.say("Faults cleared.")
        except Exception as e:
            self.say(f"Failed: {e}")

    def toggle_live(self, on):
        if on and self.session:
            self.rows = []
            self.timer.start(250)
        else:
            self.timer.stop()
            self.live.setChecked(False)

    def poll(self):
        try:
            vals = self.session.read_group(self.group.value())
        except Exception as e:
            self.say(f"Live data stopped: {e}")
            self.toggle_live(False)
            return
        self.values.setText("   ".join(f"{v.value:g} {v.unit}" for v in vals))
        self.rows.append([f"{time.time():.2f}"] + [f"{v.value:g}" for v in vals])

    def save_log(self):
        if not self.rows:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save log", "log.csv", "CSV (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("time,Engine speed /min,Injection quantity mg/str,Boost pressure mbar,Temperature °C\n")
                for r in self.rows:
                    fh.write(",".join(r) + "\n")

    def disconnect_ecu(self):
        self.toggle_live(False)
        if self.session:
            self.session.close()
            self.session = None
            self.say("Disconnected.")

    def closeEvent(self, e):
        self.disconnect_ecu()
        super().closeEvent(e)


# ------------------------------------------------------------- MAP sensor --

class MapSensorDialog(QtWidgets.QDialog):
    PRESETS = {
        "Stock 2.5 bar (as found)": None,
        "Custom (from datasheet)": "custom",
    }

    def __init__(self, f: EcuFile, parent=None):
        super().__init__(parent)
        self.f = f
        self.setWindowTitle("MAP sensor linearization")
        form = QtWidgets.QFormLayout(self)
        m = f.first("map_lin")
        cur = m.values(f.buf).ravel() if m is not None else []
        form.addRow(QtWidgets.QLabel("Enter two points of the new sensor's transfer line (from its datasheet). "
                                     f"Current curve: {', '.join(f'{v:.0f}' for v in cur)} mbar."))
        self.v1 = QtWidgets.QDoubleSpinBox(); self.v1.setRange(0, 5); self.v1.setValue(0.4); self.v1.setSuffix(" V")
        self.p1 = QtWidgets.QSpinBox(); self.p1.setRange(0, 5000); self.p1.setValue(200); self.p1.setSuffix(" mbar")
        self.v2 = QtWidgets.QDoubleSpinBox(); self.v2.setRange(0, 5); self.v2.setValue(4.65); self.v2.setSuffix(" V")
        self.p2 = QtWidgets.QSpinBox(); self.p2.setRange(0, 5000); self.p2.setValue(3000); self.p2.setSuffix(" mbar")
        form.addRow("Point 1", self._row(self.v1, self.p1))
        form.addRow("Point 2", self._row(self.v2, self.p2))
        form.addRow(QtWidgets.QLabel("Only valid with that sensor fitted."))
        form.addRow(_bb(self, "Apply"))

    def _row(self, a, b):
        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(a)
        h.addWidget(b)
        return w

    def accept(self):
        try:
            T.map_sensor_linearization(self.f, self.v1.value(), self.p1.value(), self.v2.value(), self.p2.value())
        except EcuFileError as e:
            QtWidgets.QMessageBox.warning(self, "MAP sensor", str(e))
            return
        super().accept()
