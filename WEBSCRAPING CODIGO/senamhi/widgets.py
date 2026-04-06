"""
senamhi/widgets.py — EstacionCard + PanelDatos con tabla + rango de años.
"""
import os, re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFrame, QSizePolicy, QFileDialog, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor
from .styles  import TIPO_STYLE, DEFAULT_STYLE, SUBTIPO_LABEL, fix_combo_palette
from .workers import WorkerAbrirEstacion, WorkerTabla, WorkerCSV


# ══════════════════════════════════════════════════════════════════
#  Tarjeta de estación
# ══════════════════════════════════════════════════════════════════
class EstacionCard(QFrame):
    clicked = Signal(dict)

    def __init__(self, idx: int, est: dict):
        super().__init__()
        self.est = est
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        color, bg   = TIPO_STYLE.get(est["tipo"], DEFAULT_STYLE)
        subtipo_txt = SUBTIPO_LABEL.get(est["subtipo"], est["subtipo"])
        badge_txt   = f"{est['tipo']}  {subtipo_txt}" if subtipo_txt else est["tipo"]
        self.setStyleSheet(f"""
            QFrame#card {{ background:{bg}; border:1px solid #151f32;
                border-left:3px solid {color}; border-radius:7px; }}
            QFrame#card:hover {{ background:#162040; }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(12,8,14,8); row.setSpacing(10)
        lbl_n = QLabel(f"{idx:03d}")
        lbl_n.setFixedWidth(30); lbl_n.setAlignment(Qt.AlignCenter)
        lbl_n.setStyleSheet("color:#2c3e5a;font-size:10px;font-weight:600;background:transparent;")
        badge = QLabel(badge_txt); badge.setFixedWidth(160); badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"border:1px solid {color}55;color:{color};border-radius:4px;"
            "padding:2px 6px;font-size:10px;font-weight:700;background:transparent;")
        lbl_nm = QLabel(est["nombre"])
        lbl_nm.setStyleSheet("color:#dde6f5;font-size:13px;font-weight:500;background:transparent;")
        lbl_nm.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row.addWidget(lbl_n); row.addWidget(badge); row.addWidget(lbl_nm, 1)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self.clicked.emit(self.est)
        super().mousePressEvent(e)


# ══════════════════════════════════════════════════════════════════
#  Panel de datos
# ══════════════════════════════════════════════════════════════════
class PanelDatos(QWidget):
    volver = Signal()

    def __init__(self):
        super().__init__()
        self._info     = {}
        self._periodos = []
        self._meta     = {}
        self._worker   = None
        self._dot = 0; self._sbase = ""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._build_ui()

    # ── construcción ──────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(8)

        # Encabezado
        top = QHBoxLayout()
        self.btn_back = QPushButton("← Volver")
        self.btn_back.setObjectName("btnBack")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.clicked.connect(self.volver.emit)
        self.lbl_nombre = QLabel(""); self.lbl_nombre.setObjectName("estNombre")
        top.addWidget(self.btn_back); top.addWidget(self.lbl_nombre, 1)
        root.addLayout(top)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setObjectName("sep")
        root.addWidget(sep)

        # ── Metadata de la estación ───────────────────────────────
        self.frm_meta = QFrame()
        self.frm_meta.setStyleSheet(
            "QFrame{background:#0a1628;border:1px solid #1a3060;border-radius:7px;}")
        meta_lay = QHBoxLayout(self.frm_meta)
        meta_lay.setContentsMargins(14,8,14,8); meta_lay.setSpacing(24)
        self.lbl_cod  = self._meta_lbl(); meta_lay.addWidget(self.lbl_cod)
        self.lbl_dep  = self._meta_lbl(); meta_lay.addWidget(self.lbl_dep)
        self.lbl_prov = self._meta_lbl(); meta_lay.addWidget(self.lbl_prov)
        self.lbl_alt  = self._meta_lbl(); meta_lay.addWidget(self.lbl_alt)
        meta_lay.addStretch()
        root.addWidget(self.frm_meta)
        self.frm_meta.hide()

        # ── Controles: año actual + rango + descarga ──────────────
        ctrl = QFrame()
        ctrl.setStyleSheet(
            "QFrame{background:#0d1a30;border:1px solid #1a3060;border-radius:7px;}")
        cl = QVBoxLayout(ctrl); cl.setContentsMargins(12,10,12,10); cl.setSpacing(8)

        # Fila 1: ver tabla
        r1 = QHBoxLayout(); r1.setSpacing(8)
        lbl_a = QLabel("Año:"); lbl_a.setStyleSheet("color:#6e8ab0;font-size:12px;")
        lbl_a.setFixedWidth(30)
        self.combo_anio = QComboBox(); self.combo_anio.setObjectName("combo")
        self.combo_anio.setEnabled(False); self.combo_anio.setMinimumWidth(140)
        self.combo_anio.setMaxVisibleItems(16)
        fix_combo_palette(self.combo_anio)
        self.btn_ver = QPushButton("Ver tabla"); self.btn_ver.setObjectName("btn")
        self.btn_ver.setEnabled(False); self.btn_ver.setCursor(Qt.PointingHandCursor)
        self.btn_ver.clicked.connect(self._ver_tabla)
        r1.addWidget(lbl_a); r1.addWidget(self.combo_anio,1); r1.addWidget(self.btn_ver)
        cl.addLayout(r1)

        # Separador interno
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color:#1a3060;"); cl.addWidget(sep2)

        # Fila 2: rango + descarga
        r2 = QHBoxLayout(); r2.setSpacing(8)
        lbl_r = QLabel("Rango:"); lbl_r.setStyleSheet("color:#6e8ab0;font-size:12px;")
        lbl_r.setFixedWidth(48)
        self.combo_desde = QComboBox(); self.combo_desde.setObjectName("combo")
        self.combo_desde.setEnabled(False); self.combo_desde.setMinimumWidth(110)
        fix_combo_palette(self.combo_desde)
        lbl_h = QLabel("→"); lbl_h.setStyleSheet("color:#2a4a6a;font-size:13px;")
        lbl_h.setAlignment(Qt.AlignCenter)
        self.combo_hasta = QComboBox(); self.combo_hasta.setObjectName("combo")
        self.combo_hasta.setEnabled(False); self.combo_hasta.setMinimumWidth(110)
        fix_combo_palette(self.combo_hasta)
        self.btn_csv = QPushButton("⬇  Descargar CSV"); self.btn_csv.setObjectName("btnCsv")
        self.btn_csv.setEnabled(False); self.btn_csv.setCursor(Qt.PointingHandCursor)
        self.btn_csv.clicked.connect(self._descargar_csv)
        r2.addWidget(lbl_r)
        r2.addWidget(self.combo_desde,1); r2.addWidget(lbl_h)
        r2.addWidget(self.combo_hasta,1); r2.addWidget(self.btn_csv)
        cl.addLayout(r2)
        root.addWidget(ctrl)

        # ── Tabla de datos ────────────────────────────────────────
        self.tabla = QTableWidget()
        self.tabla.setObjectName("tabla")
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setSelectionBehavior(QTableWidget.SelectRows)
        root.addWidget(self.tabla, 1)

        # Estado
        self.lbl_st = QLabel(""); self.lbl_st.setObjectName("status")
        self.lbl_st.setAlignment(Qt.AlignCenter); self.lbl_st.setWordWrap(True)
        root.addWidget(self.lbl_st)

    def _meta_lbl(self) -> QLabel:
        l = QLabel("")
        l.setStyleSheet("color:#4a6a9a;font-size:11px;background:transparent;")
        return l

    # ── API pública ────────────────────────────────────────────────
    def cargar(self, est: dict):
        self._info = est; self._periodos = []; self._meta = {}
        color, _ = TIPO_STYLE.get(est["tipo"], DEFAULT_STYLE)
        self.lbl_nombre.setText(
            f'<span style="color:{color};font-weight:700;">[{est["tipo"]}]</span>'
            f'  {est["nombre"]}'
        )
        for w in [self.combo_anio, self.combo_desde, self.combo_hasta]:
            w.clear(); w.setEnabled(False)
        for b in [self.btn_ver, self.btn_csv]: b.setEnabled(False)
        self.tabla.setRowCount(0); self.tabla.setColumnCount(0)
        self.frm_meta.hide()
        self._start("Buscando código y años disponibles")
        w = WorkerAbrirEstacion(est)
        w.progreso.connect(self._on_prog)
        w.listo.connect(self._on_listo)
        w.error.connect(self._on_err)
        self._worker = w; w.start()

    # ── Slots ──────────────────────────────────────────────────────
    def _on_listo(self, info: dict, periodos: list, meta: dict):
        self._stop()
        self._info = info; self._periodos = periodos; self._meta = meta

        # Metadata
        if meta:
            self.lbl_cod.setText(f"Cód: {info['cod']}")
            self.lbl_dep.setText(f"Dpto: {meta.get('departamento','—')}")
            self.lbl_prov.setText(f"Prov: {meta.get('provincia','—')}")
            self.lbl_alt.setText(f"Alt: {meta.get('altitud','—')}")
            self.frm_meta.show()

        for w in [self.combo_anio, self.combo_desde, self.combo_hasta]:
            w.clear()

        if periodos:
            for val, lbl in periodos:
                self.combo_anio.addItem(lbl, userData=val)
                self.combo_desde.addItem(lbl, userData=val)
                self.combo_hasta.addItem(lbl, userData=val)
            # Por defecto: hasta = último, desde = 5 años antes
            last = len(periodos)-1
            self.combo_hasta.setCurrentIndex(last)
            self.combo_desde.setCurrentIndex(max(0, last-4))
            for w in [self.combo_anio, self.combo_desde, self.combo_hasta]:
                w.setEnabled(True)
            self.btn_ver.setEnabled(True)
            self.btn_csv.setEnabled(True)
            n = len(periodos)
            self.lbl_st.setText(
                f"✓  {n} año{'s' if n!=1 else ''} disponibles  —  "
                f"Código: {info['cod']}"
            )
        else:
            self.lbl_st.setText(
                "⚠ No se cargaron los años.\n"
                "El sitio puede estar bloqueando la solicitud.\n"
                "Instala curl_cffi:  pip install curl_cffi"
            )

    def _ver_tabla(self):
        anio = self.combo_anio.currentData()
        if not anio: return
        self._set_busy(True)
        self._start(f"Cargando tabla {anio}")
        w = WorkerTabla(self._info, anio)
        w.progreso.connect(self._on_prog)
        w.lista.connect(self._on_tabla)
        w.error.connect(self._on_err)
        self._worker = w; w.start()

    def _on_tabla(self, headers: list, rows: list):
        self._stop(); self._set_busy(False)
        if not rows:
            self.lbl_st.setText("Sin datos para este año"); return
        self.tabla.setColumnCount(len(headers))
        self.tabla.setHorizontalHeaderLabels(headers)
        self.tabla.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                # Colorear celdas vacías o con guión
                if val.strip() in ("", "-", "---"):
                    item.setForeground(QColor("#334466"))
                self.tabla.setItem(r, c, item)
        self.lbl_st.setText(f"{len(rows)} registros")

    def _descargar_csv(self):
        desde = self.combo_desde.currentData()
        hasta  = self.combo_hasta.currentData()
        if not desde or not hasta: return
        if int(desde) > int(hasta):
            self.lbl_st.setText("⚠ El año 'desde' no puede ser mayor que 'hasta'")
            return
        lbl_d = self.combo_desde.currentText()
        lbl_h = self.combo_hasta.currentText()
        nombre_sug = re.sub(r'[^\w.\-]','_',
            f"SENAMHI_{self._info['nombre']}_{lbl_d}-{lbl_h}.csv")
        ruta, _ = QFileDialog.getSaveFileName(self,"Guardar CSV",nombre_sug,"CSV (*.csv)")
        if not ruta: return
        self._set_busy(True)
        self._start(f"Descargando {lbl_d}→{lbl_h}")
        w = WorkerCSV(self._info, desde, hasta, self._meta)
        w.progreso.connect(self._on_prog)
        w.listo.connect(lambda data,_fn: self._guardar(data, ruta))
        w.error.connect(self._on_err)
        self._worker = w; w.start()

    def _guardar(self, data: bytes, ruta: str):
        self._stop(); self._set_busy(False)
        try:
            with open(ruta,"wb") as f: f.write(data)
            kb = len(data)//1024
            self.lbl_st.setText(f"✓ Guardado: {os.path.basename(ruta)}  ({kb} KB)")
            QMessageBox.information(self,"Descarga completa",f"CSV guardado en:\n{ruta}")
        except Exception as ex:
            self.lbl_st.setText(f"⚠ Error al guardar: {ex}")

    # ── Helpers ────────────────────────────────────────────────────
    def _set_busy(self, busy: bool):
        for b in [self.btn_ver, self.btn_csv]: b.setEnabled(not busy)
        for w in [self.combo_anio, self.combo_desde, self.combo_hasta]:
            w.setEnabled(not busy and bool(self._periodos))

    def _on_prog(self, msg): self._sbase=msg; self.lbl_st.setText(msg)

    def _on_err(self, msg):
        self._stop(); self._set_busy(False)
        has_p = bool(self._periodos)
        for b in [self.btn_ver, self.btn_csv]: b.setEnabled(has_p)
        for w in [self.combo_anio,self.combo_desde,self.combo_hasta]: w.setEnabled(has_p)
        self.lbl_st.setText(f"⚠ {msg[:300]}")

    def _tick(self):
        self._dot=(self._dot+1)%4
        self.lbl_st.setText(self._sbase+"."*self._dot)

    def _start(self, msg):
        self._sbase=msg; self._dot=0; self._timer.start(450)

    def _stop(self):
        self._timer.stop()
