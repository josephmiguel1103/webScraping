"""
senamhi/app.py — Ventana principal (solo lógica de UI, sin network).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QScrollArea, QFrame, QLineEdit, QStackedWidget,
)
from PySide6.QtCore import Qt, QTimer

from .styles  import TIPO_STYLE, APP_QSS, fix_combo_palette
from .widgets import EstacionCard, PanelDatos
from .workers import WorkerDeptos, WorkerEstaciones


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SENAMHI — Estaciones")
        self.setMinimumSize(720, 600)
        self.resize(780, 700)

        self._deptos: dict  = {}
        self._todas:  list  = []
        self._sbase         = ""
        self._dot           = 0

        self._build_ui()
        self.setStyleSheet(APP_QSS)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._load_deptos()

    # ── construcción ──────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)

        # Cabecera
        lbl_t = QLabel("SENAMHI")
        lbl_t.setObjectName("title")
        lbl_t.setAlignment(Qt.AlignCenter)
        lbl_s = QLabel("Red de Estaciones Hidrometeorológicas del Perú")
        lbl_s.setObjectName("subtitle")
        lbl_s.setAlignment(Qt.AlignCenter)
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("sep")
        root.addWidget(lbl_t)
        root.addWidget(lbl_s)
        root.addWidget(sep)

        # Stack: página 0 = lista, página 1 = panel datos
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.stack.addWidget(self._build_page_lista())

        self.panel = PanelDatos()
        self.panel.volver.connect(lambda: self.stack.setCurrentIndex(0))
        self.stack.addWidget(self.panel)

    def _build_page_lista(self) -> QWidget:
        pg = QWidget()
        lay = QVBoxLayout(pg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # Fila departamento + botón
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)
        self.combo = QComboBox()
        self.combo.setObjectName("combo")
        self.combo.setPlaceholderText("Cargando…")
        self.combo.setEnabled(False)
        fix_combo_palette(self.combo)
        self.btn = QPushButton("Consultar")
        self.btn.setObjectName("btn")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setEnabled(False)
        self.btn.clicked.connect(self._load_estaciones)
        ctrl.addWidget(self.combo, 1)
        ctrl.addWidget(self.btn)
        lay.addLayout(ctrl)

        # Buscador
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("🔍  Filtrar por nombre o tipo…")
        self.search.textChanged.connect(self._filtrar)
        lay.addWidget(self.search)

        # Info: conteo + leyenda
        info_row = QHBoxLayout()
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("count")
        info_row.addWidget(self.lbl_count)
        info_row.addStretch()
        for t, (c, _) in TIPO_STYLE.items():
            d = QLabel(f"● {t}")
            d.setStyleSheet(
                f"color:{c};font-size:10px;font-weight:700;background:transparent;"
            )
            info_row.addWidget(d)
        lay.addLayout(info_row)

        # Lista de estaciones
        self.scroll = QScrollArea()
        self.scroll.setObjectName("scrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.cont = QWidget()
        self.cont.setObjectName("container")
        self.vlay = QVBoxLayout(self.cont)
        self.vlay.setContentsMargins(0, 0, 4, 0)
        self.vlay.setSpacing(4)
        self.vlay.addStretch()
        self.scroll.setWidget(self.cont)
        lay.addWidget(self.scroll, 1)

        # Estado
        self.lbl_st = QLabel("Obteniendo departamentos…")
        self.lbl_st.setObjectName("status")
        self.lbl_st.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl_st)

        return pg

    # ── Departamentos ──────────────────────────────────────────────
    def _load_deptos(self):
        self._start("Obteniendo departamentos")
        w = WorkerDeptos()
        w.resultado.connect(self._on_deptos)
        w.error.connect(self._on_err)
        self._wd = w
        w.start()

    def _on_deptos(self, deptos: dict):
        self._stop()
        self._deptos = deptos
        self.combo.clear()
        for n in sorted(deptos):
            self.combo.addItem(n)
        idx = self.combo.findText("Puno")
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        self.combo.setEnabled(True)
        self.btn.setEnabled(True)
        self._placeholder("Selecciona un departamento y presiona Consultar")

    # ── Estaciones ─────────────────────────────────────────────────
    def _load_estaciones(self):
        nombre = self.combo.currentText()
        key    = self._deptos.get(nombre)
        if not key:
            return
        self.btn.setEnabled(False)
        self.btn.setText("Cargando…")
        self.search.clear()
        self._todas = []
        self._placeholder(f"Consultando estaciones de {nombre}…")
        self._start("Iniciando navegador")
        w = WorkerEstaciones(key)
        w.progreso.connect(self._on_prog)
        w.resultado.connect(self._on_est)
        w.error.connect(self._on_err)
        self._we = w
        w.start()

    def _on_est(self, estaciones: list):
        self._stop()
        self._todas = estaciones
        self._render(estaciones)
        self.btn.setEnabled(True)
        self.btn.setText("Consultar")

    # ── Render lista ───────────────────────────────────────────────
    def _clear(self):
        while self.vlay.count() > 1:
            item = self.vlay.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _placeholder(self, txt: str):
        self._clear()
        lbl = QLabel(txt)
        lbl.setObjectName("placeholder")
        lbl.setAlignment(Qt.AlignCenter)
        self.vlay.insertWidget(0, lbl)
        self.lbl_count.setText("")

    def _render(self, ests: list):
        self._clear()
        if not ests:
            self._placeholder("Sin estaciones para este filtro")
            return
        for i, e in enumerate(ests, 1):
            card = EstacionCard(i, e)
            card.clicked.connect(self._on_card)
            self.vlay.insertWidget(i - 1, card)
        n = len(ests)
        self.lbl_count.setText(
            f"{n} estación{'es' if n != 1 else ''}  —  clic para ver datos"
        )

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

    # ── Estado / animación ─────────────────────────────────────────
    def _on_prog(self, msg: str):
        self._sbase = msg
        self.lbl_st.setText(msg)

    def _on_err(self, msg: str):
        self._stop()
        self._placeholder(f"⚠ {msg[:140]}")
        self.btn.setEnabled(True)
        self.btn.setText("Consultar")

    def _tick(self):
        self._dot = (self._dot + 1) % 4
        self.lbl_st.setText(self._sbase + "." * self._dot)

    def _start(self, msg: str):
        self._sbase = msg
        self._dot   = 0
        self._timer.start(450)

    def _stop(self):
        self._timer.stop()
        self.lbl_st.setText("")
