"""OpenCal main window."""
from __future__ import annotations

import os
import traceback

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from .. import APP_NAME, __version__
from ..core import dtc as D
from ..core import mappack as MP
from ..core import patterns as P
from ..core import tuning as T
from ..core import units as U
from ..core import checksum as CK
from ..core.ecufile import ChecksumLayoutUnknown, EcuFile, EcuFileError
from ..core.project import DEFAULT_ROOT, Project
from . import dialogs as dlg
from . import theme
from .mapeditor import MapEditor

CATEGORY_ORDER = ["Torque", "Limiters", "Boost", "Injection", "EGR", "Air", "Misc",
                  "Imported (JSON)", "Imported (XDF)", "Detected maps", "Unidentified"]

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QtCore.QSettings("OpenCal", "OpenCal")
        U.load(self.settings)
        self.f: EcuFile | None = None
        self.project: Project | None = None
        self.resize(1400, 860)
        self._build()
        self._update_title()
        self.show_welcome()

    # ----------------------------------------------------------- layout --
    def _build(self):
        root = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(root)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        rv.addWidget(self._header())
        split = QtWidgets.QSplitter()
        split.setChildrenCollapsible(False)
        side = QtWidgets.QFrame(objectName="Sidebar")
        lv = QtWidgets.QVBoxLayout(side)
        lv.setContentsMargins(10, 10, 6, 10)
        lv.setSpacing(8)
        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText("Search maps  ·  name or address")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self.fill_tree)
        lv.addWidget(self.filter)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setIndentation(14)
        self.tree.setIconSize(QtCore.QSize(16, 16))
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.tree.itemDoubleClicked.connect(self.open_item)
        self.tree.itemActivated.connect(self.open_item)
        lv.addWidget(self.tree, 1)
        self.side_hint = theme.label("Double-click a map to open it. Unnamed tables: search by address.", "muted")
        self.side_hint.setWordWrap(True)
        lv.addWidget(self.side_hint)
        split.addWidget(side)
        self.center = QtWidgets.QStackedWidget()
        self.start = StartPage(self)
        self.center.addWidget(self.start)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.center.addWidget(self.tabs)
        split.addWidget(self.center)
        split.setSizes([330, 1070])
        rv.addWidget(split, 1)
        self.setCentralWidget(root)
        self.status = self.statusBar()
        self._menus()
        self.setAcceptDrops(True)

    def _header(self):
        h = QtWidgets.QFrame(objectName="Header")
        h.setFixedHeight(56)
        lay = QtWidgets.QHBoxLayout(h)
        lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(10)
        logo = QtWidgets.QLabel()
        logo.setPixmap(theme.app_icon().pixmap(30, 30))
        lay.addWidget(logo)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(0)
        self.h_name = theme.label(APP_NAME, "h2")
        self.h_sub = theme.label(f"v{__version__} · open an ECU file to start", "muted")
        col.addWidget(self.h_name)
        col.addWidget(self.h_sub)
        lay.addLayout(col)
        lay.addSpacing(16)
        self.bank_box = QtWidgets.QWidget()
        self.bank_lay = QtWidgets.QHBoxLayout(self.bank_box)
        self.bank_lay.setContentsMargins(0, 0, 0, 0)
        self.bank_lay.setSpacing(2)
        self.bank_group = QtWidgets.QButtonGroup(self)
        self.bank_group.setExclusive(True)
        self.bank_group.idClicked.connect(lambda _id: self.fill_tree())
        self.bank_box.hide()
        lay.addWidget(self.bank_box)
        lay.addStretch(1)
        self.h_chk = theme.label("", "pill-ok")
        self.h_chk.hide()
        lay.addWidget(self.h_chk)
        self.h_buttons = []
        for text, tip, fn, prim in (("Undo", "Undo (Ctrl+Z)", self.undo, False), ("Redo", "Redo (Ctrl+Y)", self.redo, False),
                                    ("Check", "Safe to flash? (F9)", self.preflash, False),
                                    ("Save", "Save (Ctrl+S) · checksums are fixed automatically", self.save, True)):
            b = QtWidgets.QPushButton(text)
            b.setToolTip(tip)
            theme.role(b, "primary" if prim else "ghost")
            b.clicked.connect(lambda _=False, fn=fn: self._guard(fn))
            b.setEnabled(False)
            lay.addWidget(b)
            self.h_buttons.append(b)
        return h

    def _act(self, menu, text, fn, shortcut=None, needs_file=True):
        a = menu.addAction(text)
        a.triggered.connect(lambda *_: self._guard(fn))
        if shortcut:
            a.setShortcut(QtGui.QKeySequence(shortcut))
        a.setProperty("needs_file", needs_file)
        self._actions.append(a)
        return a

    def _menus(self):
        self._actions = []
        mb = self.menuBar()
        m = mb.addMenu("&File")
        self._act(m, "Open file…", self.open_dialog, "Ctrl+O", False)
        self.recent_menu = m.addMenu("Recent files")
        self._act(m, "Save", self.save, "Ctrl+S")
        self._act(m, "Save as…", self.save_as, "Ctrl+Shift+S")
        m.addSeparator()
        self._act(m, "Import mappack (XDF / JSON / ZedSuite / WinOLS)…", self.import_mappack)
        self._act(m, "Export mappack (JSON)…", self.export_json)
        self._act(m, "Export mappack (TunerPro XDF)…", self.export_xdf)
        m.addSeparator()
        self._act(m, "Exit", self.close, "Ctrl+Q", False)

        m = mb.addMenu("&Edit")
        self._act(m, "Undo", self.undo, "Ctrl+Z")
        self._act(m, "Redo", self.redo, "Ctrl+Y")
        self._act(m, "Change history", self.history)

        m = mb.addMenu("&Project")
        self._act(m, "New project from open file", self.new_project)
        self._act(m, "Open project…", self.open_project, needs_file=False)
        self._act(m, "Save version…", self.save_version, "Ctrl+Alt+S")
        self._act(m, "Versions…", self.versions)
        self._act(m, "Project notes…", self.notes)
        self._act(m, "Create backup (ZIP)…", self.backup)
        self._act(m, "Open project folder", self.open_project_folder)

        m = mb.addMenu("&Actions")
        self._act(m, "Firmware info", self.show_info, "Ctrl+I")
        self._act(m, "Verify checksums", self.verify_checksums)
        self._act(m, "Fix checksums", self.fix_checksums)
        self._act(m, "Checksum layout…", self.checksum_layout)
        self._act(m, "Safe to flash? (pre-flash check)", self.preflash, "F9")
        m.addSeparator()
        self._act(m, "Changed maps", self.changed)
        self._act(m, "Compare with file…", self.compare_file)
        self._act(m, "Hex viewer", self.hex_view, "Ctrl+H")
        self._act(m, "C166 disassembly…", self.disasm)
        m.addSeparator()
        self._act(m, "Edit EEPROM dump…", self.eeprom, needs_file=False)

        m = mb.addMenu("&Tuning")
        self._act(m, "Auto Stage 1…", self.stage1)
        self._act(m, "Codeblocks and multimap…", self.codeblocks)
        self._act(m, "DTC disable / enable…", self.dtc)
        self._act(m, "EGR off (race use)…", self.egr_off)
        self._act(m, "Duplicate smoke limiter", self.dup_smoke)
        self._act(m, "Launch control (activate)…", self.launch)
        m.addSeparator()
        self._act(m, "SVBL boost limit…", self.svbl)
        self._act(m, "MAP / MAF switch…", self.mapmaf)
        self._act(m, "MAP sensor linearization…", self.map_sensor)

        m = mb.addMenu("&Calculators")
        self._act(m, "AFR, power, EOI, turbo fit…", self.calcs, needs_file=False)
        self._act(m, "Virtual dyno", self.dyno)
        self._act(m, "Datalog analysis (VCDS CSV)…", self.log_analysis)

        m = mb.addMenu("E&CU")
        self._act(m, "K-line diagnostics, faults and live data…", self.ecu, needs_file=False)

        m = mb.addMenu("&Options")
        self._act(m, "Units (bar, kW, Nm, °F…)…", self.units_dialog, needs_file=False)
        a = m.addAction("Always fix checksums on save")
        a.setCheckable(True)
        a.setChecked(self.settings.value("fix_checksums", True, type=bool))
        a.toggled.connect(lambda on: self.settings.setValue("fix_checksums", on))

        m = mb.addMenu("&Help")
        self._act(m, "About", self.about, needs_file=False)
        self._refresh_recent()
        self._enable_actions()

    def _enable_actions(self):
        for a in self._actions:
            if a.property("needs_file"):
                a.setEnabled(self.f is not None)

    def _guard(self, fn):
        try:
            fn()
        except EcuFileError as e:
            QtWidgets.QMessageBox.warning(self, APP_NAME, str(e))
        except Exception as e:  # keep the app alive, show the error
            QtWidgets.QMessageBox.critical(self, APP_NAME, f"{e}\n\n{traceback.format_exc(limit=4)}")

    # ---------------------------------------------------------- welcome --
    def show_welcome(self):
        self.start.refresh()
        self.center.setCurrentWidget(self.start)

    # --------------------------------------------------------- file I/O --
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            self._guard(lambda: self.load(u.toLocalFile()))
            break

    def open_dialog(self):
        if not self._confirm_discard():
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open ECU file", self.settings.value("lastdir", ""),
                                                        "ECU files (*.bin *.ori *.mod *.e2p *.eep);;ECU firmware (*.bin *.ori *.mod);;EEPROM (*.e2p *.eep *.bin);;All files (*)")
        if path:
            self.load(path)

    def load(self, path, project: Project | None = None):
        if os.path.getsize(path) <= 4096 or path.lower().endswith((".e2p", ".eep")):
            dlg.EepromDialog(path, self).exec()
            return
        f = EcuFile.load(path)
        if project is not None:
            f.original = open(project.original_path, "rb").read()
            f.checksum_layout = CK.strict_layout(f.original) or f.checksum_layout
            f.path = None
        self.f, self.project = f, project
        f.listeners.append(lambda _f: self._on_change())
        self.settings.setValue("lastdir", os.path.dirname(path))
        if project is None:
            rec = [path] + [p for p in (self.settings.value("recent", []) or []) if p != path]
            self.settings.setValue("recent", rec[:12])
            self._refresh_recent()
        while self.tabs.count():
            self.close_tab(0)
        self._fill_banks()
        self.fill_tree()
        self.tabs.addTab(OverviewPage(self), "Overview")
        self.tabs.tabBar().setTabButton(0, QtWidgets.QTabBar.RightSide, None)
        self.center.setCurrentWidget(self.tabs)
        for b in self.h_buttons:
            b.setEnabled(True)
        self._enable_actions()
        self._on_change()

    def _refresh_recent(self):
        self.recent_menu.clear()
        for p in (self.settings.value("recent", []) or []):
            a = self.recent_menu.addAction(p)
            a.triggered.connect(lambda _=False, p=p: self._guard(lambda: self.load(p) if self._confirm_discard() else None))

    def _confirm_discard(self) -> bool:
        if self.f is None or not self.f.history:
            return True
        r = QtWidgets.QMessageBox.question(self, APP_NAME, "Discard unsaved changes?")
        return r == QtWidgets.QMessageBox.Yes

    def closeEvent(self, e):
        if self._confirm_discard():
            e.accept()
        else:
            e.ignore()

    def save(self):
        if self.project is not None:
            return self.save_version()
        if not self.f.path:
            return self.save_as()
        self._do_save(self.f.path)

    def save_as(self):
        base = self.f.path or os.path.join(self.settings.value("lastdir", ""), self.f.name)
        stem, ext = os.path.splitext(base)
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save as", f"{stem}_mod{ext or '.bin'}",
                                                        "ECU firmware (*.bin);;All files (*)")
        if path:
            self._do_save(path)

    def choose_checksum_layout(self) -> bool:
        """Ask which checksum algorithm to use when the loaded file did not verify."""
        reps = CK.candidates(self.f.original)
        items = [f"{r.layout}: {r.n_ok} of {r.n_total} blocks verified in the file as opened" for r in reps]
        items.append("Save without correcting checksums")
        item, ok = QtWidgets.QInputDialog.getItem(
            self, "Checksum layout uncertain",
            "This file's checksums were already wrong when it was opened, so OpenCal cannot tell which\n"
            "algorithm the ECU uses. Pick the layout of a known-good file of the same software\n"
            "(another read of the same software number that verified).", items, 0, False)
        if not ok:
            return False
        if item.startswith("Save without"):
            self._skip_fix_once = True
            return True
        self.f.set_checksum_layout(item.split(":")[0])
        self._on_change()
        return True

    def _fix_or_ask(self):
        if self.f.checksum_uncertain and not getattr(self, "_skip_fix_once", False):
            if not self.choose_checksum_layout():
                raise EcuFileError("Cancelled: checksum layout not chosen.")
        if self.f.checksum_layout is None:
            self._skip_fix_once = False
            return self.f.checksum()
        return self.f.fix_checksums()

    def checksum_layout(self):
        if self.choose_checksum_layout():
            self.status.showMessage(f"Checksum layout: {self.f.checksum_layout or 'not corrected'}", 6000)

    def _do_save(self, path):
        always = self.settings.value("fix_checksums", True, type=bool)
        if getattr(self, "_skip_fix_once", False):
            always = False
        try:
            rep = self.f.save(path, fix_checksums=always)
        except ChecksumLayoutUnknown:
            if not self.choose_checksum_layout():
                return
            return self._do_save(path)
        finally:
            pass
        self._skip_fix_once = False
        self.f.history.clear()
        self.status.showMessage(f"Saved {path}" + (f" · {rep.summary()}" if rep else ""), 8000)
        self._update_title()

    # ------------------------------------------------------------- tree --
    def _fill_banks(self):
        for b in self.bank_group.buttons():
            self.bank_group.removeButton(b)
            b.deleteLater()
        banks = self.f.populated_banks
        if len(banks) < 2:
            self.bank_box.hide()
            return
        self.bank_box.show()
        entries = [("All banks", -1)] + [(cb.label(), cb.base) for cb in banks]
        for text, base in entries:
            b = QtWidgets.QToolButton()
            b.setText(text)
            b.setCheckable(True)
            b.setToolTip("Show maps of every bank" if base < 0 else f"Codeblock bank 0x{base:05X}")
            self.bank_group.addButton(b, base)
            self.bank_lay.addWidget(b)
            if base == self.f.active_bank:
                b.setChecked(True)

    def current_bank(self):
        bid = self.bank_group.checkedId()
        return None if bid < 0 else bid

    def fill_tree(self):
        self.tree.clear()
        if self.f is None:
            return
        q = self.filter.text().strip().lower()
        bank = self.current_bank()
        cats: dict[str, QtWidgets.QTreeWidgetItem] = {}

        def cat(name):
            if name not in cats:
                it = QtWidgets.QTreeWidgetItem([name, ""])
                f = it.font(0)
                f.setBold(True)
                it.setFont(0, f)
                it.setIcon(0, theme.glyph_icon(name))
                it.setFlags(it.flags() & ~Qt.ItemIsSelectable)
                cats[name] = it
            return cats[name]

        changed = {m.key for m, _ in self.f.changed_maps()}
        for m in self.f.maps:
            if bank is not None and m.bank != bank:
                continue
            if not m.is3d and not m.identified and m.category == "Unidentified":
                continue
            label = m.label() + (f"  · CB {m.codeblock}" if m.codeblock is not None else f"  · bank {m.bank >> 16:X}")
            if q and q not in label.lower() and q not in m.key.lower():
                continue
            it = QtWidgets.QTreeWidgetItem([label, f"{m.address:05X}"])
            it.setForeground(1, QtGui.QBrush(QtGui.QColor("#5f6876")))
            it.setFont(1, theme.mono(8))
            it.setData(0, Qt.UserRole, m.key)
            it.setToolTip(0, f"{m.rows}×{m.cols} · codeblock {m.codeblock}\n{m.description}")
            if m.key in changed:
                it.setForeground(0, QtGui.QBrush(QtGui.QColor("#f0b429")))
                ch = QtWidgets.QTreeWidgetItem([label, f"{m.address:05X}"])
                ch.setData(0, Qt.UserRole, m.key)
                ch.setForeground(0, QtGui.QBrush(QtGui.QColor("#f0b429")))
                cat("Changed").addChild(ch)
            cat(m.category).addChild(it)
        for s in P.find_scalars(self.f.buf):
            it = QtWidgets.QTreeWidgetItem([f"{s.name}", f"{s.value(self.f.buf):g} {s.unit}"])
            it.setData(0, Qt.UserRole, f"scalar:{s.kind}")
            cat("Values").addChild(it)
        order = ["Changed"] + CATEGORY_ORDER + ["Values"]
        for name in sorted(cats, key=lambda n: order.index(n) if n in order else 50):
            if name == "Unidentified" and not q:
                continue
            it = cats[name]
            it.setText(0, name)
            it.setText(1, str(it.childCount()))
            it.setForeground(1, QtGui.QBrush(QtGui.QColor(theme.MUTED)))
            self.tree.addTopLevelItem(it)
            it.setExpanded(name not in ("Detected maps",) or bool(q))

    def open_item(self, item, _col=0):
        key = item.data(0, Qt.UserRole)
        if not key:
            return
        if key.startswith("scalar:"):
            return self._edit_scalar(key[7:])
        self.open_map(key)

    def open_map(self, key):
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, MapEditor) and w.m.key == key:
                self.tabs.setCurrentIndex(i)
                return w
        m = self.f.map(key)
        if m is None:
            return None
        ed = MapEditor(self.f, m)
        ed.status.connect(lambda s: self.status.showMessage(s, 5000))
        self.tabs.addTab(ed, m.label())
        self.tabs.setCurrentWidget(ed)
        return ed

    def close_tab(self, i):
        w = self.tabs.widget(i)
        if isinstance(w, OverviewPage) and self.f is not None and self.tabs.count() > 1:
            return
        if isinstance(w, MapEditor):
            w.detach()
        self.tabs.removeTab(i)
        w.deleteLater()

    def _info_widget(self):
        w = QtWidgets.QTextBrowser()
        w.setHtml(dlg.info_html(self.f))
        return w

    # ---------------------------------------------------------- refresh --
    def _on_change(self):
        rep = self.f.checksum() if self.f else None
        self.h_chk.show()
        if rep is None:
            self.h_chk.setText("checksum: unknown layout")
            theme.role(self.h_chk, "pill-bad")
        elif rep.all_ok:
            self.h_chk.setText(f"✓  checksums OK · {rep.n_total} blocks")
            theme.role(self.h_chk, "pill-ok")
        else:
            self.h_chk.setText(f"●  checksums {rep.n_ok}/{rep.n_total} · fixed on save")
            theme.role(self.h_chk, "pill-warn")
        self._update_title()
        QtCore.QTimer.singleShot(0, self._refresh_tree_soft)

    def _refresh_tree_soft(self):
        # keep expansion when edits change the Changed group
        expanded = {self.tree.topLevelItem(i).text(0).split(" (")[0] for i in range(self.tree.topLevelItemCount())
                    if self.tree.topLevelItem(i).isExpanded()}
        self.fill_tree()
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.text(0).split(" (")[0] in expanded:
                it.setExpanded(True)

    def _update_title(self):
        if self.f is None:
            self.setWindowTitle(f"{APP_NAME} {__version__}")
            return
        name = self.project.name if self.project else self.f.name
        star = " •" if self.f.history else ""
        self.h_name.setText(name + star)
        cbs = ", ".join(str(c.id) for c in self.f.populated_banks)
        self.h_sub.setText(f"{self.f.info.part_number}  ·  {self.f.info.software}  ·  {self.f.info.bosch_number}  ·  "
                           f"{self.f.info.description}  ·  codeblock {cbs}"
                           + (f"  ·  project v{len(self.project.versions) - 1}" if self.project else ""))
        self.setWindowTitle(f"{name}{star} — {self.f.info.part_number} {self.f.info.software} — {APP_NAME} {__version__}")

    # ----------------------------------------------------------- editing --
    def undo(self):
        e = self.f.undo()
        self.status.showMessage(f"Undone: {e.note}" if e else "Nothing to undo", 4000)

    def redo(self):
        e = self.f.redo()
        self.status.showMessage(f"Redone: {e.note}" if e else "Nothing to redo", 4000)

    def history(self):
        rows = "".join(f"<li>0x{e.address:05X} · {len(e.after)} bytes · {dlg.esc(e.note)}</li>" for e in reversed(self.f.history))
        dlg.TextReport("Change history", f"<ol>{rows or '<p>No changes yet.</p>'}</ol>", self).exec()

    def _edit_scalar(self, kind):
        s = next(s for s in P.find_scalars(self.f.buf) if s.kind == kind)
        v, ok = QtWidgets.QInputDialog.getInt(self, s.name, f"{s.description}\n\nValue ({s.unit or 'raw'})",
                                              s.raw(self.f.buf), 0, 65535)
        if ok:
            T.set_scalar(self.f, kind, v)

    def svbl(self):
        self._edit_scalar("svbl")

    def mapmaf(self):
        self._edit_scalar("map_maf")

    # ---------------------------------------------------------- mappacks --
    def import_mappack(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import mappack", "", "Mappacks (*.xdf *.json);;All files (*)")
        if not path:
            return
        if path.lower().endswith(".xdf"):
            added, skipped = MP.import_xdf(self.f, path)
        else:
            added, skipped = self._import_json_any(path)
        self.fill_tree()
        QtWidgets.QMessageBox.information(self, "Import", f"Imported {added} maps ({skipped} skipped).")

    def _import_json_any(self, path):
        """Own JSON, or ZedSuite / WinOLS JSON through the ported importer."""
        import json
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
        if isinstance(obj, dict) and obj.get("schema", "").startswith("openedc.mappack") or \
                isinstance(obj, dict) and obj.get("schema", "").startswith("opencal.mappack"):
            return MP.import_json(self.f, path)
        from ..legacy import mappack as LM
        doc = LM.import_mappack(obj, bytes(self.f.buf))
        items = []
        for d in doc.get("maps", []):
            rows = int(d.get("rows", 1))
            cols = int(d.get("cols", 1))
            it = {"address": int(d["address"]), "rows": rows, "cols": cols, "name": d.get("name", ""),
                  "category": d.get("category") or "Imported (JSON)",
                  "factor": float(d.get("factor", 1)), "offset": float(d.get("offset", 0)), "unit": d.get("unit", "")}
            for ours, theirs in (("x", "y_axis"), ("y", "x_axis")):
                ax = d.get(theirs) or {}
                if isinstance(ax, dict) and ax.get("address") is not None:
                    it[ours] = {"address": int(ax["address"]), "count": int(ax.get("count", 0)) or (rows if ours == "x" else cols),
                                "factor": float(ax.get("factor", 1)), "offset": float(ax.get("offset", 0)),
                                "unit": ax.get("unit", ""), "name": ax.get("name", "")}
            items.append(it)
        MP._apply_items(self.f, items)
        return len(items), 0

    def export_json(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export mappack", f"{self.f.info.software}.json", "JSON (*.json)")
        if path:
            n = MP.export_json(self.f, path)
            self.status.showMessage(f"Exported {n} maps", 6000)

    def export_xdf(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export XDF", f"{self.f.info.software}.xdf", "TunerPro XDF (*.xdf)")
        if path:
            n = MP.export_xdf(self.f, path)
            self.status.showMessage(f"Exported {n} maps to XDF", 6000)

    # ----------------------------------------------------------- project --
    def new_project(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "New project", "Project name", text=os.path.splitext(self.f.name)[0])
        if not ok:
            return
        tmp = os.path.join(QtCore.QDir.tempPath(), "opencal_orig.bin")
        with open(tmp, "wb") as fh:
            fh.write(self.f.original)
        p = Project.create(tmp, self.settings.value("project_root", DEFAULT_ROOT), name)
        if self.f.dirty:
            rep = self._fix_or_ask()
            p.add_version(bytes(self.f.buf), "Imported edits", [e.note for e in self.f.history],
                          rep.summary() if rep else "")
        self.project = p
        self.f.history.clear()
        self.status.showMessage(f"Project created in {p.folder}", 8000)
        self._update_title()

    def open_project(self):
        if not self._confirm_discard():
            return
        projects = Project.list(self.settings.value("project_root", DEFAULT_ROOT))
        if not projects:
            QtWidgets.QMessageBox.information(self, "Projects", "No projects yet. Open a file and use Project › New project.")
            return
        names = [f"{p.name} — {len(p.versions)} version(s) — {p.meta.get('created', '')}" for p in projects]
        name, ok = QtWidgets.QInputDialog.getItem(self, "Open project", "Project", names, 0, False)
        if ok:
            p = projects[names.index(name)]
            self.load(p.latest_path, p)

    def save_version(self):
        if self.project is None:
            return self.new_project()
        label, ok = QtWidgets.QInputDialog.getText(self, "Save version", "Label (what changed)")
        if not ok:
            return
        rep = self._fix_or_ask() if self.settings.value("fix_checksums", True, type=bool) else self.f.checksum()
        idx = self.project.add_version(bytes(self.f.buf), label, [e.note for e in self.f.history],
                                       rep.summary() if rep else "")
        self.f.history.clear()
        self.status.showMessage(f"Saved version {idx}", 6000)
        self._update_title()

    def versions(self):
        if self.project is None:
            QtWidgets.QMessageBox.information(self, "Versions", "Versions belong to a project. Use Project › New project.")
            return
        items = [f"v{i}: {v['label']} ({v['time']}) {v.get('checksum', '')}" for i, v in enumerate(self.project.versions)]
        item, ok = QtWidgets.QInputDialog.getItem(self, "Versions", "Switch to version", items, len(items) - 1, False)
        if ok and self._confirm_discard():
            self.load(self.project.path_of(items.index(item)), self.project)

    def notes(self):
        if self.project is None:
            return self.new_project()
        html = "".join(f"<p><b>{dlg.esc(n['time'])}</b><br>{dlg.esc(n['text'])}</p>" for n in self.project.meta["notes"])
        text, ok = QtWidgets.QInputDialog.getMultiLineText(self, "Project notes", "Add a note", "")
        if ok and text.strip():
            self.project.add_note(text.strip())
        elif html:
            dlg.TextReport("Notes", html, self).exec()

    def backup(self):
        if self.project is None:
            return self.new_project()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Backup", f"{self.project.name}.zip", "ZIP (*.zip)")
        if path:
            self.status.showMessage(f"Backup written: {self.project.backup(path)}", 8000)

    def open_project_folder(self):
        folder = self.project.folder if self.project else os.path.dirname(self.f.path or "")
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(folder))

    # ----------------------------------------------------------- actions --
    def show_info(self):
        dlg.TextReport("Firmware info", dlg.info_html(self.f), self).exec()

    def verify_checksums(self):
        rep = self.f.checksum()
        if rep is None:
            return QtWidgets.QMessageBox.warning(self, "Checksums", "No known checksum layout for this ECU.")
        rows = "".join(f"<tr><td>0x{b.start:05X}–0x{b.end:05X}</td><td>0x{b.store:05X}</td>"
                       f"<td>{b.stored:08X}</td><td>{b.calculated:08X}</td>"
                       f"<td style='color:{'#3ecf6e' if b.ok else '#ff5b5b'}'>{'OK' if b.ok else 'wrong'}</td></tr>"
                       for b in rep.blocks if not b.skipped)
        dlg.TextReport("Checksums", f"<p><b>{rep.summary()}</b></p><table cellpadding=3>"
                       "<tr><th>range</th><th>stored at</th><th>file</th><th>calculated</th><th></th></tr>"
                       f"{rows}</table>", self).exec()

    def fix_checksums(self):
        if self.f.checksum_uncertain and not self.choose_checksum_layout():
            return
        if self.f.checksum_layout is None:
            return
        rep = self.f.fix_checksums()
        self.status.showMessage(rep.summary() if rep else "No known checksum layout", 6000)

    def preflash(self):
        dlg.TextReport("Safe to flash?", dlg.checks_html(T.preflash_check(self.f)), self).exec()

    def changed(self):
        rows = "".join(f"<tr><td>{dlg.esc(m.label())}</td><td>0x{m.address:05X}</td><td>{d:+.1f}%</td></tr>"
                       for m, d in self.f.changed_maps())
        rng = "".join(f"<li>0x{a:05X}–0x{b:05X} ({b - a} bytes)</li>" for a, b in self.f.diff_ranges()[:200])
        dlg.TextReport("Changed since original", f"<table cellpadding=3><tr><th>map</th><th>address</th><th>max Δ</th></tr>"
                       f"{rows}</table><h3>Byte ranges</h3><ul>{rng or 'none'}</ul>", self).exec()

    def compare_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Compare with", "", "ECU firmware (*.bin *.ori);;All files (*)")
        if not path:
            return
        other = open(path, "rb").read()
        if len(other) != len(self.f.buf):
            raise EcuFileError("Files differ in size; cannot compare.")
        diffs = self.f.changed_maps(other)
        rows = "".join(f"<tr><td>{dlg.esc(m.label())}</td><td>0x{m.address:05X}</td><td>{d:+.1f}%</td></tr>" for m, d in diffs)
        QtWidgets.QMessageBox.information(self, "Compare", f"{len(diffs)} map(s) differ.")
        from ..core import multimap
        mm = multimap.describe(self.f, other)
        patch = multimap.code_patch(self.f, other)
        code = "".join(f"<li>0x{a:05X}–0x{b:05X} ({b - a} bytes)</li>" for a, b in patch.ranges[:40])
        box = dlg.TextReport(f"Compared with {os.path.basename(path)}",
                             f"<p><b>Banks / code:</b> {dlg.esc(mm)}</p>"
                             + (f"<p>Code differences (switching patch, rpm cut or similar). OpenCal keeps them "
                                f"untouched when you edit maps:</p><ul>{code}</ul>" if patch.present else "")
                             + f"<table cellpadding=3><tr><th>map</th><th>address</th><th>max Δ vs other</th></tr>{rows}</table>", self)
        copy = QtWidgets.QPushButton("Copy every differing map from the other file")
        copy.clicked.connect(lambda: (self._copy_maps(diffs, other), box.accept()))
        box.layout().insertWidget(1, copy)
        box.exec()

    def _copy_maps(self, diffs, other):
        with self.f.begin() as tx:
            for m, _ in diffs:
                tx.write(m.address, other[m.address:m.end], f"{m.label()} copied from compared file")

    def hex_view(self):
        w = self.tabs.currentWidget()
        start = w.m.address if isinstance(w, MapEditor) else self.f.active_bank
        dlg.HexView(self.f, start, self).exec()

    def disasm(self):
        from ..legacy.c166 import C166Disassembler
        a, ok = QtWidgets.QInputDialog.getText(self, "C166 disassembly", "File address (hex)", text="10EE0")
        if not ok:
            return
        off = int(a, 16)
        rows = C166Disassembler().decode_range(self.f.buf[off:off + 0x200], off, 0x200)
        text = "\n".join(f"{ea:06X}  {raw:<10} {dlg.esc(t)}" for ea, raw, t in rows)
        dlg.TextReport("C166 disassembly (file addresses)", f"<pre>{text}</pre>", self, 760, 640).exec()

    def eeprom(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open EEPROM dump (95040)", "", "EEPROM (*.e2p *.eep *.bin);;All files (*)")
        if path:
            dlg.EepromDialog(path, self).exec()

    # ------------------------------------------------------------ tuning --
    def stage1(self):
        dlg.Stage1Dialog(self.f, self).exec()

    def codeblocks(self):
        dlg.CodeblockDialog(self.f, self).exec()
        self._fill_banks()
        self.fill_tree()

    def dtc(self):
        DtcDialog(self.f, self).exec()

    def egr_off(self):
        if QtWidgets.QMessageBox.question(
                self, "EGR off", "Raise every EGR airflow target in the active bank so the valve stays shut?\n\n"
                "For race / off-road use only: not legal on public roads. Undoable.") == QtWidgets.QMessageBox.Yes:
            n = T.egr_off(self.f)
            msg = f"EGR off: {len(n)} map(s) changed"
            try:
                egr_codes = [g for g in D.groups(self.f) if g.state != "Disabled" and
                             ("egr" in g.system.lower() or "recirculation" in g.description.lower())]
            except EcuFileError:
                egr_codes = []
            if egr_codes and QtWidgets.QMessageBox.question(
                    self, "EGR off", "Also disable the EGR fault codes?\n\n" +
                    "\n".join(f"{g.code} / {g.vag_code}  {g.description}" for g in egr_codes[:12])) == QtWidgets.QMessageBox.Yes:
                k = D.set_enabled(self.f, [g.vag_code for g in egr_codes], False)
                msg += f", {k} DTC record(s) disabled"
            self.status.showMessage(msg, 8000)

    def dup_smoke(self):
        n = T.duplicate_smoke(self.f)
        self.status.showMessage(f"Smoke limiter copied to {len(n)} sister table(s)", 6000)

    def launch(self):
        if QtWidgets.QMessageBox.question(self, "Launch control", "Give the dormant launch-control table a vehicle-speed "
                                          "axis?\nExperimental: verify with logs.") == QtWidgets.QMessageBox.Yes:
            n = T.activate_launch_control(self.f)
            self.f.rescan()
            self.fill_tree()
            self.status.showMessage(f"Launch control activated in {n} place(s)", 6000)

    def map_sensor(self):
        dlg.MapSensorDialog(self.f, self).exec()

    # ------------------------------------------------------- calculators --
    def calcs(self):
        dlg.CalcDialog(self.f, self).exec()

    def dyno(self):
        dlg.DynoDialog(self.f, self).exec()

    def log_analysis(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open datalog", "", "CSV (*.csv *.txt);;All files (*)")
        if not path:
            return
        d = dlg.LogDialog(self.f, path, self)
        d.overlay_ready.connect(self._apply_overlay)
        d.exec()

    def _apply_overlay(self, payload):
        key, ov = payload
        ed = self.open_map(key)
        if ed:
            ed.set_overlay(ov)

    def ecu(self):
        dlg.EcuDialog(self).exec()

    def units_dialog(self):
        if dlg.UnitsDialog(self).exec():
            U.save(self.settings)
            self.refresh_units()

    def refresh_units(self):
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, MapEditor):
                w.reload()
        if self.f is not None:
            idx = next((i for i in range(self.tabs.count()) if isinstance(self.tabs.widget(i), OverviewPage)), None)
            if idx is not None:
                old = self.tabs.widget(idx)
                self.tabs.removeTab(idx)
                old.deleteLater()
                self.tabs.insertTab(0, OverviewPage(self), "Overview")
        self.status.showMessage("Units updated", 4000)

    def about(self):
        QtWidgets.QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3><p>Free, offline calibration editor for Bosch EDC15P/V.</p>"
            "<p>GPL-3.0-only. No warranty, including no warranty of ECU compatibility. "
            "Detected maps are candidates: verify before flashing.</p>"
            "<p>Contributors: NiwiTheFox, Claude (Anthropic). Includes attributed ports from ZedSuite and "
            "VAG EDC15P Suite (see NOTICE).</p>")


class DtcDialog(QtWidgets.QDialog):
    def __init__(self, f: EcuFile, parent=None):
        super().__init__(parent)
        self.f = f
        self.setWindowTitle("Fault codes (DTC)")
        self.resize(820, 600)
        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel("Disabling a code stops the ECU from monitoring it in every codeblock. "
                                     "Enable restores the exact original record."))
        self.q = QtWidgets.QLineEdit()
        self.q.setPlaceholderText("Filter (P-code, VAG code, text)…")
        self.q.textChanged.connect(self.fill)
        v.addWidget(self.q)
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["P-code", "VAG", "System", "Description", "State"])
        self.table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        v.addWidget(self.table, 1)
        h = QtWidgets.QHBoxLayout()
        for text, en in (("Disable selected", False), ("Enable selected", True)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(lambda _=False, en=en: self.switch(en))
            h.addWidget(b)
        h.addStretch()
        v.addLayout(h)
        v.addWidget(dlg._bb(self, "Close", cancel=False))
        self.fill()

    def fill(self):
        q = self.q.text().lower()
        self.table.setRowCount(0)
        for g in D.groups(self.f):
            if q and q not in f"{g.code} {g.vag_code} {g.system} {g.description}".lower():
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, t in enumerate((g.code, str(g.vag_code), g.system, g.description, f"{g.state} ({g.enabled}/{g.total})")):
                it = QtWidgets.QTableWidgetItem(t)
                it.setData(Qt.UserRole, g.vag_code)
                if c == 4 and g.state != "Enabled":
                    it.setForeground(QtGui.QColor("#f0b429"))
                self.table.setItem(r, c, it)

    def switch(self, enable):
        codes = sorted({self.table.item(i.row(), 0).data(Qt.UserRole) for i in self.table.selectedIndexes()})
        if not codes:
            return
        shared = sorted({c for g in D.groups(self.f) if g.vag_code in codes for c in g.shared_with} - set(codes))
        if shared and QtWidgets.QMessageBox.question(
                self, "Shared fault path",
                "These codes share a fault path in this software, so they switch together:\n"
                + ", ".join(str(c) for c in shared) + "\n\nContinue?") != QtWidgets.QMessageBox.Yes:
            return
        try:
            n = D.set_enabled(self.f, codes, enable)
        except EcuFileError as e:
            QtWidgets.QMessageBox.warning(self, "DTC", str(e))
            return
        self.fill()
        self.setWindowTitle(f"Fault codes (DTC) — {n} record(s) changed")


class StartPage(QtWidgets.QWidget):
    """Welcome screen: open button, drop zone, recent files."""

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        outer = QtWidgets.QVBoxLayout(self)
        outer.addStretch(1)
        wrap = QtWidgets.QHBoxLayout()
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(14)
        wrap.addStretch(1)
        wrap.addLayout(col, 0)
        wrap.addStretch(1)
        outer.addLayout(wrap)
        outer.addStretch(2)
        icon = QtWidgets.QLabel()
        icon.setPixmap(theme.app_icon().pixmap(76, 76))
        icon.setAlignment(Qt.AlignCenter)
        col.addWidget(icon)
        t = theme.label(APP_NAME, "h1")
        t.setAlignment(Qt.AlignCenter)
        col.addWidget(t)
        sub = theme.label(f"v{__version__}  ·  free, offline calibration editor for Bosch EDC15P/V (VAG TDI PD)", "muted")
        sub.setAlignment(Qt.AlignCenter)
        col.addWidget(sub)
        self.drop = QtWidgets.QFrame(objectName="Drop")
        self.drop.setMinimumSize(600, 150)
        dl = QtWidgets.QVBoxLayout(self.drop)
        dl.setAlignment(Qt.AlignCenter)
        dl.setSpacing(10)
        b = QtWidgets.QPushButton("Open ECU file…")
        theme.role(b, "primary")
        b.setMinimumSize(200, 38)
        b.clicked.connect(lambda: win._guard(win.open_dialog))
        dl.addWidget(b, 0, Qt.AlignCenter)
        h = theme.label("or drop a .bin / .ori here  ·  the original stays untouched until you save", "muted")
        h.setAlignment(Qt.AlignCenter)
        dl.addWidget(h)
        col.addWidget(self.drop)
        row = QtWidgets.QHBoxLayout()
        for text, fn in (("Open project", win.open_project), ("EEPROM editor", win.eeprom),
                         ("ECU diagnostics", win.ecu), ("Calculators", win.calcs)):
            bb = QtWidgets.QPushButton(text)
            bb.setMinimumHeight(32)
            bb.clicked.connect(lambda _=False, fn=fn: win._guard(fn))
            row.addWidget(bb)
        col.addLayout(row)
        col.addSpacing(6)
        col.addWidget(theme.label("Recent files", "h2"))
        self.recent = QtWidgets.QListWidget()
        self.recent.setMinimumHeight(190)
        self.recent.setStyleSheet(
            f"QListWidget{{background:{theme.SURFACE};border:1px solid {theme.BORDER};border-radius:10px;padding:6px}}"
            f"QListWidget::item{{padding:7px 10px;border-radius:6px}}"
            f"QListWidget::item:hover{{background:{theme.SURFACE_3}}}")
        self.recent.itemActivated.connect(self._open_recent)
        self.recent.itemClicked.connect(self._open_recent)
        col.addWidget(self.recent)
        self.refresh()

    def refresh(self):
        self.recent.clear()
        for p in (self.win.settings.value("recent", []) or []):
            if os.path.exists(p):
                it = QtWidgets.QListWidgetItem(f"{os.path.basename(p)}\n{os.path.dirname(p)}")
                it.setData(Qt.UserRole, p)
                it.setIcon(theme.glyph_icon("Values"))
                self.recent.addItem(it)
        if not self.recent.count():
            it = QtWidgets.QListWidgetItem("No recent files yet")
            it.setFlags(Qt.NoItemFlags)
            self.recent.addItem(it)

    def _open_recent(self, it):
        p = it.data(Qt.UserRole)
        if p:
            self.win._guard(lambda: self.win.load(p))


class OverviewPage(QtWidgets.QScrollArea):
    """File overview: identity, banks, key maps, estimates, findings."""

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        f = win.f
        body = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(body)
        grid.setContentsMargins(22, 20, 22, 20)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)

        def card(title, rows, r, c, span=1):
            fr = QtWidgets.QFrame(objectName="Card")
            v = QtWidgets.QVBoxLayout(fr)
            v.setContentsMargins(18, 14, 18, 16)
            v.setSpacing(7)
            v.addWidget(theme.label(title, "h2"))
            for left, right in rows:
                h = QtWidgets.QHBoxLayout()
                h.addWidget(theme.label(left, "muted"))
                h.addStretch()
                rl = right if isinstance(right, QtWidgets.QWidget) else QtWidgets.QLabel(str(right))
                h.addWidget(rl)
                v.addLayout(h)
            v.addStretch()
            grid.addWidget(fr, r, c, 1, span)
            return fr

        card("File", [("Part number", f.info.part_number), ("Software", f.info.software),
                      ("Bosch number", f.info.bosch_number), ("Description", f.info.description),
                      ("ECU", f.info.ecu_type)], 0, 0)
        rep = f.checksum()
        rows = [("Checksum", theme.label(rep.summary() if rep else "unknown layout",
                                         "pill-ok" if rep and rep.all_ok else "pill-warn"))]
        for cb in f.codeblocks:
            rows.append((f"Bank 0x{cb.base:05X}", f"codeblock {cb.id} · {cb.gearbox or '?'}" if cb.populated else "empty"))
        if len(f.populated_banks) > 1:
            rows.append(("Multimap", f"{len(f.populated_banks)} calibrations · switching code kept as is"))
        for s in P.find_scalars(f.buf)[:2]:
            rows.append((s.name.split(" (")[0], U.fmt(s.value(f.buf), s.unit) if s.unit else f"{s.value(f.buf):g}"))
        card("Banks & limits", rows, 0, 1)
        bank = f.active_bank
        key = []
        for kind, label in (("driver_wish", "Driver wish"), ("smoke", "Smoke limiter"), ("torque_limiter", "Torque limiter"),
                            ("boost_target", "Boost target"), ("boost_limit", "Boost limit"), ("n75", "N75 duty")):
            m = f.first(kind, bank)
            if m is None:
                continue
            v = m.values(f.buf)
            b = QtWidgets.QPushButton(f"peak {U.fmt(float(v.max()), m.unit, 1)}   ›")
            theme.role(b, "ghost")
            b.clicked.connect(lambda _=False, k=m.key: win.open_map(k))
            key.append((label, b))
        card("Key maps · active bank", key or [("", "none identified")], 1, 0)
        est = []
        try:
            from ..core import sim
            r = sim.simulate(f, bank)
            pull = [s for s in r.samples if s.phase == "pull"]
            if pull:
                pk = max(pull, key=lambda s: s.power)
                pt = max(pull, key=lambda s: s.torque)
                est = [("Peak power (estimate)", f"≈ {U.fmt(pk.power, 'hp')} @ {pk.rpm:.0f} rpm"),
                       ("Peak torque (estimate)", f"≈ {U.fmt(pt.torque, 'Nm')} @ {pt.rpm:.0f} rpm")]
        except Exception:
            pass
        dyb = QtWidgets.QPushButton("Open virtual dyno   ›")
        theme.role(dyb, "ghost")
        dyb.clicked.connect(lambda: win._guard(win.dyno))
        card("Calibration", [("Tables found", len(f.maps)), ("Named", sum(m.identified for m in f.maps))] + est
             + [("", dyb)], 1, 1)
        lab = QtWidgets.QLabel(dlg.checks_html(T.preflash_check(f)))
        lab.setWordWrap(True)
        fr = card("Pre-flash check", [], 2, 0, 2)
        fr.layout().insertWidget(1, lab)
        grid.setRowStretch(3, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.setWidget(body)
