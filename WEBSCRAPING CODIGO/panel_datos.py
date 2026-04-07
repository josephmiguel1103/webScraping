"""
panel_datos.py — PanelDatos: vista de detalle de una estación.
  Muestra tabla de datos, maneja captcha con WebEngine,
  permite descargar CSVs por rango o completo.
"""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QTextEdit, QSplitter,
)
from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QFont

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    QWebEngineView = None
    HAS_WEBENGINE = False

from api import api_curl_estacion, api_csv_por_mes, run_js_sync, delay_ms
from config import JS_SNAPSHOT, js_select_periodo
from parser import tabla_desde_snapshot_json
from widgets import Worker, fix_combo


class PanelDatos(QWidget):
    """Panel completo de una estación: tabla, info y descarga."""

    volver = Signal()

    def __init__(self):
        super().__init__()
        self._info = {}
        self._periodos = []
        self._meta = {}
        self._page = None
        self._url_datos = ""
        self._poll_n = 0
        self._workers = []
        self._dot = 0
        self._sb = ""
        self._ignore_combo = False

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._tick)

        self._poll_tmr = QTimer(self)
        self._poll_tmr.setInterval(1200)
        self._poll_tmr.timeout.connect(self._poll_snap)

        self._build_ui()

    # ══════════════════════════════════════════════════════════════
    #  Construcción de la interfaz
    # ══════════════════════════════════════════════════════════════

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        # — Barra superior —
        top = QHBoxLayout()
        self.b_back = QPushButton("← Volver")
        self.b_back.setMaximumWidth(100)
        self.b_back.clicked.connect(self._volver)
        self.l_nom = QLabel("")
        self.l_nom.setFont(QFont("Arial", 14, QFont.Bold))
        top.addWidget(self.b_back)
        top.addWidget(self.l_nom, 1)
        v.addLayout(top)

        # — Tabs —
        tabs = QHBoxLayout()
        self.btn_tabla = QPushButton("Tabla")
        self.btn_tabla.setCheckable(True)
        self.btn_tabla.setChecked(True)
        self.btn_tabla.clicked.connect(self._show_tabla)
        self.btn_estacion = QPushButton("Estación")
        self.btn_estacion.setCheckable(True)
        self.btn_estacion.clicked.connect(self._show_estacion)
        tabs.addWidget(self.btn_tabla)
        tabs.addWidget(self.btn_estacion)
        tabs.addStretch()
        v.addLayout(tabs)

        # — Combo período (vista previa) —
        r1 = QHBoxLayout()
        r1.setSpacing(6)
        self.cb_a = QComboBox()
        self.cb_a.setEnabled(False)
        self.cb_a.setMaxVisibleItems(16)
        fix_combo(self.cb_a)
        self.cb_a.currentIndexChanged.connect(self._on_anio_changed)
        r1.addWidget(QLabel("Período:"))
        r1.addWidget(self.cb_a, 1)
        v.addLayout(r1)

        # — Fila rango + botones descarga —
        r2 = QHBoxLayout()
        r2.setSpacing(6)
        self.cb_d = QComboBox()
        self.cb_d.setEnabled(False)
        self.cb_d.setMaxVisibleItems(16)
        fix_combo(self.cb_d)
        self.cb_h = QComboBox()
        self.cb_h.setEnabled(False)
        self.cb_h.setMaxVisibleItems(16)
        fix_combo(self.cb_h)

        self.b_csv = QPushButton("⬇ Descargar rango")
        self.b_csv.setEnabled(False)
        self.b_csv.setToolTip("Descarga un CSV por mes para el rango seleccionado")
        self.b_csv.clicked.connect(self._csv_rango)

        self.b_all = QPushButton("⬇ Descargar TODO")
        self.b_all.setEnabled(False)
        self.b_all.setStyleSheet("font-weight: bold; color: #003d99;")
        self.b_all.setToolTip("Descarga todos los meses disponibles, un CSV por mes")
        self.b_all.clicked.connect(self._csv_todo)

        r2.addWidget(QLabel("Rango:"))
        r2.addWidget(self.cb_d, 1)
        r2.addWidget(QLabel("→"))
        r2.addWidget(self.cb_h, 1)
        r2.addWidget(self.b_csv)
        r2.addWidget(self.b_all)
        v.addLayout(r2)

        # — Splitter: webview arriba, tabla/info abajo —
        self.split = QSplitter(Qt.Vertical)
        self.webview = None
        if HAS_WEBENGINE and QWebEngineView:
            self.webview = QWebEngineView()
            self.webview.setMinimumHeight(260)
            self.webview.setVisible(False)
            self.split.addWidget(self.webview)
        else:
            lbl = QLabel("Para ver datos con captcha instala: pip install PySide6-WebEngine")
            lbl.setWordWrap(True)
            lbl.setVisible(False)
            self.split.addWidget(lbl)

        self.stack2 = QStackedWidget()

        self.tbl = QTableWidget()
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.verticalHeader().setVisible(False)
        self.stack2.addWidget(self.tbl)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.stack2.addWidget(self.info_text)

        self.split.addWidget(self.stack2)
        v.addWidget(self.split, 1)

        self.l_st = QLabel("")
        self.l_st.setAlignment(Qt.AlignCenter)
        self.l_st.setWordWrap(True)
        v.addWidget(self.l_st)

    # ══════════════════════════════════════════════════════════════
    #  Carga de estación
    # ══════════════════════════════════════════════════════════════

    def cargar(self, est: dict):
        self._cerrar_session()
        self._info = est
        self._periodos = []
        self._meta = {}
        self.l_nom.setText(est["nombre"])
        self._ignore_combo = True
        for cb in [self.cb_a, self.cb_d, self.cb_h]:
            cb.clear()
            cb.setEnabled(False)
        self._ignore_combo = False
        self.b_csv.setEnabled(False)
        self.b_all.setEnabled(False)
        self.tbl.setRowCount(0)
        self.tbl.setColumnCount(0)
        self._start("Consultando estación…")
        w = Worker(lambda p: api_curl_estacion(est, p))
        w.prog.connect(self._on_prog)
        w.ok.connect(self._post_curl)
        w.err.connect(self._on_err)
        self._track(w)
        w.start()

    def _post_curl(self, data: dict):
        self._stop()
        self._url_datos = data["url"]
        self._meta = data.get("meta") or {}
        self._periodos = data.get("periodos") or []

        if data.get("curl_ok"):
            self._page = None
            self._fill_combos()
            self._mostrar_tabla(data["hdrs"], data["rows"])
            self._fill_info_text()
            self.b_csv.setEnabled(False)
            self.b_all.setEnabled(False)
            self.l_st.setText(
                "✓ Datos vía curl. Para descargar CSV completa el captcha (necesita WebEngine)."
            )
            return

        if not HAS_WEBENGINE or not self.webview:
            self._fill_combos()
            self._fill_info_text()
            self.l_st.setText("Instala PySide6-WebEngine para el captcha y la descarga CSV.")
            QMessageBox.warning(
                self, "WebEngine",
                "pip install PySide6-WebEngine\n\nNecesario para descargar CSVs dentro de la app.",
            )
            return

        self._poll_n = 0
        self.webview.setVisible(True)
        self.split.setSizes([340, 320])
        self.l_st.setText("Completa el captcha en el panel superior…")
        self.webview.load(QUrl(self._url_datos))
        QTimer.singleShot(2500, self._start_poll_embed)

    # ══════════════════════════════════════════════════════════════
    #  Polling de snapshot (post-captcha)
    # ══════════════════════════════════════════════════════════════

    def _start_poll_embed(self):
        if not self.webview or not self.webview.isVisible():
            return
        self._poll_n = 0
        if not self._poll_tmr.isActive():
            self._poll_tmr.start()

    def _poll_snap(self):
        if not self.webview or not self.webview.isVisible():
            self._poll_tmr.stop()
            return
        self._poll_n += 1
        if self._poll_n > 120:
            self._poll_tmr.stop()
            self.l_st.setText("Sin datos aún — revisa el captcha.")
            return
        self.webview.page().runJavaScript(JS_SNAPSHOT, self._on_snap_result)

    def _on_snap_result(self, jstr):
        per, meta, hdrs, rows, _ = tabla_desde_snapshot_json(jstr)
        if per:
            self._periodos = per
        if meta:
            self._meta.update(meta)
        if rows:
            self._poll_tmr.stop()
            self._page = self.webview.page()
            self._fill_combos()
            self._mostrar_tabla(hdrs, rows)
            self._fill_info_text()
            self.webview.setVisible(False)
            self.split.setSizes([80, 520])
            self.b_csv.setEnabled(True)
            self.b_all.setEnabled(True)
            n = len(self._periodos)
            rng = f"{self._periodos[0][1]} → {self._periodos[-1][1]}" if n else ""
            self.l_st.setText(f"✓ {n} mes(es) disponibles  |  {rng}")

    # ══════════════════════════════════════════════════════════════
    #  Combos
    # ══════════════════════════════════════════════════════════════

    def _fill_combos(self):
        self._ignore_combo = True
        for cb in [self.cb_a, self.cb_d, self.cb_h]:
            cb.clear()
            for val, lbl in self._periodos:
                cb.addItem(lbl, userData=val)
            cb.setEnabled(bool(self._periodos))
        if self._periodos:
            last = len(self._periodos) - 1
            self.cb_a.setCurrentIndex(last)
            self.cb_h.setCurrentIndex(last)
            self.cb_d.setCurrentIndex(max(0, last - 4))
        self._ignore_combo = False

    def _fill_info_text(self):
        lines = [f"{self._info.get('nombre', '')}  (cod. {self._info.get('cod', '')})", ""]
        for k, v in self._meta.items():
            lines.append(f"{k}: {v}")
        self.info_text.setPlainText("\n".join(lines))

    # ══════════════════════════════════════════════════════════════
    #  Cambio de período
    # ══════════════════════════════════════════════════════════════

    def _on_anio_changed(self, idx):
        if self._ignore_combo or not self._periodos or not self._page:
            return
        anio = self.cb_a.currentData()
        if not anio:
            return
        self._busy(True)
        self._start(f"Cargando {self.cb_a.currentText()}…")
        QTimer.singleShot(0, lambda: self._tabla_periodo_web(anio))

    def _tabla_periodo_web(self, anio):
        try:
            run_js_sync(self._page, js_select_periodo(anio))
            delay_ms(900)
            snap = run_js_sync(self._page, JS_SNAPSHOT)
            _, _, hdrs, rows, _ = tabla_desde_snapshot_json(snap)
            if not rows:
                self.l_st.setText("Sin datos para este período")
            else:
                self._mostrar_tabla(hdrs, rows)
        except Exception as e:
            self.l_st.setText(f"Error: {e}")
        finally:
            self._stop()
            self._busy(False)

    def _mostrar_tabla(self, hdrs, rows):
        self.tbl.setColumnCount(len(hdrs))
        self.tbl.setHorizontalHeaderLabels(hdrs)
        self.tbl.setRowCount(len(rows))
        for ri, row in enumerate(rows):
            for ci, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                self.tbl.setItem(ri, ci, item)
        self._show_tabla()
        self.l_st.setText(f"✓ {len(rows)} registros")

    # ══════════════════════════════════════════════════════════════
    #  Descarga CSV
    # ══════════════════════════════════════════════════════════════

    def _pedir_carpeta(self):
        return QFileDialog.getExistingDirectory(self, "Selecciona la carpeta de destino")

    def _csv_rango(self):
        d = self.cb_d.currentData()
        h = self.cb_h.currentData()
        if not d or not h or not self._page:
            self.l_st.setText("Completa primero el captcha o selecciona un rango.")
            return
        ds, hs = str(d).strip(), str(h).strip()
        if ds > hs:
            self.l_st.setText("Error: 'Desde' debe ser anterior o igual a 'Hasta'.")
            return
        carpeta = self._pedir_carpeta()
        if not carpeta:
            return
        n = sum(1 for v, _ in self._periodos if ds <= v.strip() <= hs)
        self._busy(True)
        self._start(f"Descargando {n} mes(es)…")
        nombre = self._info.get("nombre", "estacion")
        QTimer.singleShot(0, lambda: self._run_descarga(ds, hs, carpeta, nombre))

    def _csv_todo(self):
        if not self._periodos or not self._page:
            self.l_st.setText("Sin períodos disponibles.")
            return
        carpeta = self._pedir_carpeta()
        if not carpeta:
            return
        ds = str(self._periodos[0][0]).strip()
        hs = str(self._periodos[-1][0]).strip()
        self._busy(True)
        self._start(f"Descargando TODO: {len(self._periodos)} mes(es)…")
        nombre = self._info.get("nombre", "estacion")
        QTimer.singleShot(0, lambda: self._run_descarga(ds, hs, carpeta, nombre))

    def _run_descarga(self, ds, hs, carpeta, nombre):
        try:
            guardados = api_csv_por_mes(
                self._page, ds, hs, nombre,
                dict(self._meta), self._periodos,
                carpeta, self._on_prog,
            )
            self._post_descarga(guardados, carpeta)
        except Exception as e:
            self._on_err(str(e))

    def _post_descarga(self, guardados, carpeta):
        self._stop()
        self._busy(False)
        if not guardados:
            self.l_st.setText("Sin datos — no se generó ningún CSV.")
            return
        total_kb = sum(os.path.getsize(r) for r in guardados if os.path.exists(r)) // 1024
        self.l_st.setText(f"✓ {len(guardados)} archivo(s) guardados (~{total_kb} KB)")
        nombres = [os.path.basename(r) for r in guardados[:20]]
        extra = f"\n… y {len(guardados) - 20} más" if len(guardados) > 20 else ""
        QMessageBox.information(
            self, "Descarga completada",
            f"{len(guardados)} CSV (uno por mes):\n\n"
            + "\n".join(nombres) + extra
            + f"\n\nCarpeta:\n{carpeta}",
        )

    # ══════════════════════════════════════════════════════════════
    #  Tabs
    # ══════════════════════════════════════════════════════════════

    def _show_tabla(self):
        self.btn_tabla.setChecked(True)
        self.btn_estacion.setChecked(False)
        self.stack2.setCurrentIndex(0)

    def _show_estacion(self):
        self.btn_tabla.setChecked(False)
        self.btn_estacion.setChecked(True)
        self.stack2.setCurrentIndex(1)

    # ══════════════════════════════════════════════════════════════
    #  Utilidades internas
    # ══════════════════════════════════════════════════════════════

    def _volver(self):
        self._cerrar_session()
        self.volver.emit()

    def _cerrar_session(self):
        self._poll_tmr.stop()
        self._page = None
        if self.webview:
            self.webview.load(QUrl("about:blank"))
            self.webview.setVisible(False)

    def _busy(self, b: bool):
        ok = self._page is not None and bool(self._periodos)
        self.b_csv.setEnabled(not b and ok)
        self.b_all.setEnabled(not b and ok)
        self.cb_a.setEnabled(not b and ok)
        self.cb_d.setEnabled(not b and bool(self._periodos))
        self.cb_h.setEnabled(not b and bool(self._periodos))

    def _on_prog(self, m: str):
        self._sb = m
        self.l_st.setText(m)

    def _on_err(self, m: str):
        self._stop()
        self._busy(False)
        self.l_st.setText(f"Error: {m[:300]}")

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
        self._cerrar_session()
        super().closeEvent(e)
