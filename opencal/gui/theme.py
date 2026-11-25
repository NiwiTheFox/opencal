"""Visual design: palette tokens, stylesheet, icons."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

BG = "#0f1216"
SURFACE = "#161a20"
SURFACE_2 = "#1c2129"
SURFACE_3 = "#232933"
BORDER = "#2a313c"
TEXT = "#e3e6eb"
MUTED = "#8b94a3"
ACCENT = "#3d8bfd"
ACCENT_DIM = "#1f3b66"
OK = "#38c172"
WARN = "#f2b33d"
BAD = "#ef5350"

FONT_UI = "Segoe UI"
FONT_MONO = "Cascadia Mono"

QSS = f"""
* {{ font-family: "{FONT_UI}"; font-size: 10pt; outline: 0; }}
QMainWindow, QDialog {{ background: {BG}; color: {TEXT}; }}
QWidget {{ color: {TEXT}; }}
QLabel {{ background: transparent; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="h1"] {{ font-size: 22pt; font-weight: 600; }}
QLabel[role="h2"] {{ font-size: 13pt; font-weight: 600; }}
QLabel[role="chip"] {{ background: {SURFACE_3}; border: 1px solid {BORDER}; border-radius: 9px; padding: 1px 8px; color: {MUTED}; }}
QLabel[role="pill-ok"] {{ background: #12301f; border: 1px solid #1f5a37; color: {OK}; border-radius: 9px; padding: 1px 9px; }}
QLabel[role="pill-warn"] {{ background: #3a2c10; border: 1px solid #6b5016; color: {WARN}; border-radius: 9px; padding: 1px 9px; }}
QLabel[role="pill-bad"] {{ background: #3a1414; border: 1px solid #6b2222; color: {BAD}; border-radius: 9px; padding: 1px 9px; }}

QMenuBar {{ background: {BG}; border-bottom: 1px solid {BORDER}; padding: 2px 4px; }}
QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; background: transparent; }}
QMenuBar::item:selected {{ background: {SURFACE_3}; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; padding: 4px; border-radius: 6px; }}
QMenu::item {{ padding: 6px 24px 6px 14px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMenu::item:disabled {{ color: #59616e; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QFrame#Header {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
QFrame#Sidebar {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
QFrame#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#Drop {{ background: {SURFACE}; border: 2px dashed {BORDER}; border-radius: 12px; }}
QFrame#Drop[hover="true"] {{ border-color: {ACCENT}; background: #14213a; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextBrowser {{
  background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 8px;
  selection-background-color: {ACCENT}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: 0; width: 18px; }}
QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_DIM}; }}

QPushButton, QToolButton {{ background: {SURFACE_3}; border: 1px solid {BORDER}; border-radius: 6px; padding: 5px 12px; }}
QPushButton:hover, QToolButton:hover {{ background: #2b3340; border-color: #384252; }}
QPushButton:pressed, QToolButton:pressed {{ background: #20262f; }}
QPushButton:disabled, QToolButton:disabled {{ color: #59616e; }}
QPushButton[role="primary"] {{ background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: 600; }}
QPushButton[role="primary"]:hover {{ background: #5a9cff; }}
QPushButton[role="ghost"], QToolButton[role="ghost"] {{ background: transparent; border-color: transparent; }}
QPushButton[role="ghost"]:hover, QToolButton[role="ghost"]:hover {{ background: {SURFACE_3}; }}
QToolButton:checked, QPushButton:checked {{ background: {ACCENT_DIM}; border-color: {ACCENT}; color: white; }}

QTreeWidget, QTreeView {{ background: transparent; border: 0; }}
QTreeView::item {{ padding: 4px 2px; border-radius: 4px; }}
QTreeView::item:hover {{ background: {SURFACE_3}; }}
QTreeView::item:selected {{ background: {ACCENT_DIM}; color: white; }}

QTableView, QTableWidget {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px;
  gridline-color: #0d1014; selection-background-color: rgba(61,139,253,0.55); selection-color: white; }}
QHeaderView::section {{ background: {SURFACE_2}; color: {MUTED}; border: 0; border-right: 1px solid {BORDER};
  border-bottom: 1px solid {BORDER}; padding: 4px; font-family: "{FONT_MONO}"; font-size: 9pt; }}
QTableCornerButton::section {{ background: {SURFACE_2}; border: 0; }}

QTabWidget::pane {{ border: 0; }}
QTabBar {{ background: {BG}; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 7px 14px; border: 0;
  border-bottom: 2px solid transparent; margin-right: 2px; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::close-button {{ subcontrol-position: right; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #333b47; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #333b47; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: 0; width: 0; height: 0; }}

QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar::item {{ border: 0; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border-radius: 4px; border: 1px solid #45505f; background: {SURFACE_2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QToolTip {{ background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; border-radius: 6px; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 8px; margin-top: 14px; padding: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; color: {MUTED}; }}
"""


def apply(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    for role, color in ((QtGui.QPalette.Window, BG), (QtGui.QPalette.WindowText, TEXT),
                        (QtGui.QPalette.Base, SURFACE), (QtGui.QPalette.AlternateBase, SURFACE_2),
                        (QtGui.QPalette.Text, TEXT), (QtGui.QPalette.Button, SURFACE_3),
                        (QtGui.QPalette.ButtonText, TEXT), (QtGui.QPalette.Highlight, ACCENT),
                        (QtGui.QPalette.HighlightedText, "#ffffff"), (QtGui.QPalette.ToolTipBase, SURFACE_3),
                        (QtGui.QPalette.ToolTipText, TEXT), (QtGui.QPalette.PlaceholderText, "#6b7482"),
                        (QtGui.QPalette.Link, ACCENT)):
        pal.setColor(role, QtGui.QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
    app.setWindowIcon(app_icon())


def mono(size: int = 10) -> QtGui.QFont:
    f = QtGui.QFont(FONT_MONO, size)
    f.setStyleHint(QtGui.QFont.Monospace)
    return f


def role(w: QtWidgets.QWidget, name: str) -> QtWidgets.QWidget:
    w.setProperty("role", name)
    w.style().unpolish(w)
    w.style().polish(w)
    return w


def label(text: str, kind: str | None = None) -> QtWidgets.QLabel:
    lb = QtWidgets.QLabel(text)
    if kind:
        role(lb, kind)
    return lb


# ----------------------------------------------------------------- icons --

def _pix(size=64) -> tuple[QtGui.QPixmap, QtGui.QPainter]:
    pm = QtGui.QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    return pm, p


def app_icon() -> QtGui.QIcon:
    icon = QtGui.QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm, p = _pix(s)
        r = QtCore.QRectF(0, 0, s, s).adjusted(s * .04, s * .04, -s * .04, -s * .04)
        grad = QtGui.QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0, QtGui.QColor("#3d8bfd"))
        grad.setColorAt(1, QtGui.QColor("#7b5cff"))
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, s * .22, s * .22)
        # a stylised map surface: 3 rising bars + curve
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 235), max(1.0, s * .07), Qt.SolidLine, Qt.RoundCap))
        path = QtGui.QPainterPath()
        path.moveTo(r.left() + s * .18, r.bottom() - s * .25)
        path.cubicTo(r.left() + s * .38, r.bottom() - s * .28, r.left() + s * .45, r.top() + s * .3,
                     r.right() - s * .18, r.top() + s * .22)
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(255, 255, 255, 150))
        for i, h in enumerate((.18, .3, .44)):
            x = r.left() + s * (.22 + i * .2)
            p.drawRoundedRect(QtCore.QRectF(x, r.bottom() - s * .14 - s * h * .4, s * .1, s * h * .4), s * .02, s * .02)
        p.end()
        icon.addPixmap(pm)
    return icon


CATEGORY_GLYPH = {
    "Changed": ("●", WARN), "Torque": ("⟋", "#8fb7ff"), "Limiters": ("⊤", "#ff8f8f"), "Boost": ("◎", "#7fd6ff"),
    "Injection": ("✦", "#ffd27f"), "EGR": ("⇄", "#a6e3a1"), "Air": ("≈", "#9ad0ff"), "Misc": ("◇", MUTED),
    "Detected maps": ("▦", MUTED), "Unidentified": ("·", "#59616e"), "Values": ("#", "#c8a2ff"),
    "Imported (JSON)": ("⇣", "#c8a2ff"), "Imported (XDF)": ("⇣", "#c8a2ff"),
}


def glyph_icon(category: str) -> QtGui.QIcon:
    ch, color = CATEGORY_GLYPH.get(category, ("•", MUTED))
    pm, p = _pix(32)
    f = QtGui.QFont(FONT_UI, 15)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QtGui.QColor(color))
    p.drawText(QtCore.QRect(0, 0, 32, 32), Qt.AlignCenter, ch)
    p.end()
    return QtGui.QIcon(pm)


def save_ico(path: str) -> None:
    app_icon().pixmap(256, 256).save(path, "ICO")
