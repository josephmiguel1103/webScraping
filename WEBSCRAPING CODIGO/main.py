#!/usr/bin/env python3
"""
main.py — SENAMHI: ventana principal y punto de entrada.

Estructura del proyecto:
  main.py        ← este archivo (ventana principal + __main__)
  config.py      ← constantes, headers HTTP, scripts JS
  parser.py      ← parseo de HTML: tablas, metadatos, períodos
  api.py         ← red: curl, Selenium, descarga CSV por mes
  widgets.py     ← componentes reutilizables: Worker, Card, fix_combo
  panel_datos.py ← panel de detalle de estación con WebEngine

pip install PySide6 PySide6-WebEngine beautifulsoup4 selenium webdriver-manager requests curl_cffi
"""

import sys

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QScrollArea, QLineEdit, QStackedWidget,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from api import api_deptos, api_estaciones
from panel_datos import PanelDatos
from widgets import Worker, Card, fix_combo


class MainWindow(QWidget):
    """Ventana principal: lista de departamentos y estaciones."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SENAMHI — Estaciones")
        self.setMinimumSize(700, 500)
        self.resize(850, 600)

        self._deptos: dict = {}
        self._todas: list = []
        self._sb = ""
        self._dot = 0
        self._workers: list = []

        self._build_ui()

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._tick)

        self._load_deptos()

    # ══════════════════════════════════════════════════════════════
    #  Construcción de la interfaz
    # ══════════════════════════════════════════════════════════════

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(6)

        titulo = QLabel("SENAMHI")
        titulo.setFont(QFont("Arial", 16, QFont.Bold))
        v.addWidget(titulo)

        self.stack = QStackedWidget()

        # ── Página 0: lista de estaciones ──────────────────────
        pg = QWidget()
        pg_v = QVBoxLayout(pg)
        pg_v.setContentsMargins(0, 0, 0, 0)
        pg_v.setSpacing(6)

        r2 = QHBoxLayout()
        r2.setSpacing(6)
        self.cb = QComboBox()
        self.cb.setEnabled(False)
        fix_combo(self.cb)
        self.b = QPushButton("Consultar")
        self.b.setEnabled(False)
        self.b.setMaximumWidth(100)
        self.b.clicked.connect(self._load_est)
        r2.addWidget(QLabel("Departamento:"))
        r2.addWidget(self.cb, 1)
        r2.addWidget(self.b)
        pg_v.addLayout(r2)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrar...")
        self.search.textChanged.connect(self._filtrar)
        pg_v.addWidget(self.search)

        sc2 = QScrollArea()
        sc2.setWidgetResizable(True)
        self.cont = QWidget()
        self.vl = QVBoxLayout(self.cont)
        self.vl.setContentsMargins(0, 0, 0, 0)
        self.vl.setSpacing(2)
        self.vl.addStretch()
        sc2.setWidget(self.cont)
        pg_v.addWidget(sc2, 1)

        self.l_cnt = QLabel("")
        pg_v.addWidget(self.l_cnt)
        self.l_st = QLabel("")
        self.l_st.setAlignment(Qt.AlignCenter)
        pg_v.addWidget(self.l_st)
        self.stack.addWidget(pg)

        # ── Página 1: detalle de estación ──────────────────────
        self.panel = PanelDatos()
        self.panel.volver.connect(lambda: self.stack.setCurrentIndex(0))
        self.stack.addWidget(self.panel)

        v.addWidget(self.stack, 1)

    # ══════════════════════════════════════════════════════════════
    #  Carga de departamentos
    # ══════════════════════════════════════════════════════════════

    def _load_deptos(self):
        self._start("Cargando departamentos...")
        w = Worker(lambda p: api_deptos())
        w.ok.connect(self._on_deptos)
        w.err.connect(self._on_err)
        self._track(w)
        w.start()

    def _on_deptos(self, d: dict):
        self._stop()
        self._deptos = d
        self.cb.clear()
        for n in sorted(d):
            self.cb.addItem(n)
        idx = self.cb.findText("Ucayali")
        if idx >= 0:
            self.cb.setCurrentIndex(idx)
        self.cb.setEnabled(True)
        self.b.setEnabled(True)
        self.l_st.setText("Selecciona un departamento y presiona Consultar")

    # ══════════════════════════════════════════════════════════════
    #  Carga de estaciones
    # ══════════════════════════════════════════════════════════════

    def _load_est(self):
        n = self.cb.currentText()
        k = self._deptos.get(n)
        if not k:
            return
        self.b.setEnabled(False)
        self._clear()
        self._start(f"Cargando {n}...")
        w = Worker(lambda p: api_estaciones(k, p))
        w.prog.connect(self._on_prog)
        w.ok.connect(self._on_est)
        w.err.connect(self._on_err)
        self._track(w)
        w.start()

    def _on_est(self, ests: list):
        self._stop()
        self._todas = ests
        self._render(ests)
        self.b.setEnabled(True)

    # ══════════════════════════════════════════════════════════════
    #  Renderizado de la lista
    # ══════════════════════════════════════════════════════════════

    def _clear(self):
        while self.vl.count() > 1:
            it = self.vl.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()

    def _render(self, ests: list):
        self._clear()
        for i, e in enumerate(ests, 1):
            c = Card(i, e)
            c.clicked.connect(self._on_card)
            self.vl.insertWidget(i - 1, c)
        con = sum(1 for e in ests if e.get("cod"))
        self.l_cnt.setText(f"{len(ests)} estaciones  ·  {con} con código")

    def _filtrar(self, txt: str):
        if not self._todas:
            return
        t = txt.strip().lower()
        self._render([
            e for e in self._todas
            if t in e["nombre"].lower() or t in e["tipo"].lower()
        ])

    def _on_card(self, est: dict):
        self.panel.cargar(est)
        self.stack.setCurrentIndex(1)

    # ══════════════════════════════════════════════════════════════
    #  Utilidades internas
    # ══════════════════════════════════════════════════════════════

    def _on_prog(self, m: str):
        self._sb = m
        self.l_st.setText(m)

    def _on_err(self, m: str):
        self._stop()
        self.l_st.setText(f"Error: {m[:150]}")
        self.b.setEnabled(True)

    def _track(self, w: Worker):
        self._workers.append(w)
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        w.finished.connect(w.deleteLater)

    def _tick(self):
        self._dot = (self._dot + 1) % 4
        self.l_st.setText(self._sb + "." * self._dot)

    def _start(self, m: str):
        self._sb = m
        self._dot = 0
        self._tmr.start(400)

    def _stop(self):
        self._tmr.stop()

    def closeEvent(self, e):
        if hasattr(self, "panel"):
            self.panel._cerrar_session()
        super().closeEvent(e)


# ══════════════════════════════════════════════════════════════════
#  Punto de entrada
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    except ImportError:
        pass
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
