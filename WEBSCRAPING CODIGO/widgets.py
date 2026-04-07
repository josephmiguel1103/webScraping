"""
widgets.py — Componentes UI reutilizables:
  - Worker (QThread genérico)
  - _fix_combo (estilo de QComboBox)
  - Card (tarjeta de estación)
"""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QComboBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QPalette, QColor

from config import TIPOS


# ══════════════════════════════════════════════════════════════════
#  Worker genérico
# ══════════════════════════════════════════════════════════════════

class Worker(QThread):
    """Ejecuta una función en un hilo aparte y emite ok/err/prog."""

    ok   = Signal(object)
    err  = Signal(str)
    prog = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.ok.emit(self._fn(self.prog.emit))
        except Exception as e:
            self.err.emit(str(e))


# ══════════════════════════════════════════════════════════════════
#  Estilo de QComboBox
# ══════════════════════════════════════════════════════════════════

def fix_combo(cb: QComboBox):
    """Aplica paleta y stylesheet para que el combo sea legible en modo oscuro."""
    p = cb.palette()
    color_map = [
        (QPalette.Text,            "#111111"),
        (QPalette.Base,            "#ffffff"),
        (QPalette.Button,          "#ffffff"),
        (QPalette.ButtonText,      "#111111"),
        (QPalette.Highlight,       "#0078d4"),
        (QPalette.HighlightedText, "#ffffff"),
    ]
    for role, c in color_map:
        for st in [QPalette.Active, QPalette.Inactive]:
            p.setColor(st, role, QColor(c))
        p.setColor(
            QPalette.Disabled, role,
            QColor("#888888" if role == QPalette.Text else c),
        )
    cb.setPalette(p)
    cb.view().setPalette(p)
    cb.setStyleSheet(
        "QComboBox { color: #111111; background: #ffffff; font-size: 13px; font-weight: 600; "
        "padding: 4px 8px; min-height: 22px; }"
        "QComboBox QAbstractItemView { color: #111111; background: #ffffff; font-size: 13px; }"
    )


# ══════════════════════════════════════════════════════════════════
#  Card de estación
# ══════════════════════════════════════════════════════════════════

class Card(QFrame):
    """Tarjeta visual para una estación en la lista."""

    clicked = Signal(dict)

    def __init__(self, idx: int, est: dict):
        super().__init__()
        self.est = est
        has_cod = bool(est.get("cod"))
        if has_cod:
            self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        lbl_idx = QLabel(f"{idx:03d}")
        lbl_idx.setFixedWidth(35)
        lbl_idx.setAlignment(Qt.AlignCenter)
        lbl_idx.setFont(QFont("Arial", 9))
        lbl_idx.setAttribute(Qt.WA_TransparentForMouseEvents)

        lbl_tipo = QLabel(TIPOS.get(est["tipo"], "⚪"))
        lbl_tipo.setFixedWidth(20)
        lbl_tipo.setAlignment(Qt.AlignCenter)
        lbl_tipo.setAttribute(Qt.WA_TransparentForMouseEvents)

        lbl_nom = QLabel(est["nombre"])
        lbl_nom.setFont(QFont("Arial", 11))
        lbl_nom.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lbl_nom.setAttribute(Qt.WA_TransparentForMouseEvents)
        if not has_cod:
            lbl_nom.setStyleSheet("color: gray;")

        layout.addWidget(lbl_idx)
        layout.addWidget(lbl_tipo)
        layout.addWidget(lbl_nom, 1)

        if has_cod:
            lbl_cod = QLabel(est["cod"])
            lbl_cod.setStyleSheet("color: #aaa; font-size: 10px;")
            lbl_cod.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout.addWidget(lbl_cod)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.est.get("cod"):
            self.clicked.emit(self.est)
        super().mousePressEvent(e)
