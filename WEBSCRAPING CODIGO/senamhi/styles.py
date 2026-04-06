"""
senamhi/styles.py — Estilos QSS.
Fix ComboBox: se usa setPalette() en código + QSS con selector explícito #combo
para garantizar texto visible en Windows/Linux independientemente del tema nativo.
"""

TIPO_STYLE = {
    "MET": ("#38bdf8", "#0b1e2e"),
    "HID": ("#4ade80", "#0b2019"),
    "PLU": ("#facc15", "#1e1a07"),
}
DEFAULT_STYLE = ("#94a3b8", "#0f1628")

SUBTIPO_LABEL = {
    "CO":   "Convencional",
    "AU":   "Automática",
    "HLG":  "Hidrológica",
    "HLM":  "Hidro Manual",
    "PLU":  "Pluviométrica",
    "EAMA": "Automática",
}

APP_QSS = """
/* ── Globals ─────────────────────────────────────────── */
* { font-family: "Segoe UI", system-ui, sans-serif; }
QWidget { background: #07101f; color: #c8d4e8; font-size: 13px; }

/* ── Etiquetas ──────────────────────────────────────── */
QLabel#title    { font-size:21px; font-weight:700; color:#eef2fc; letter-spacing:2px; }
QLabel#subtitle { font-size:11px; color:#2a3a58; }
QLabel#count    { color:#2a4a6a; font-size:11px; }
QLabel#status   { color:#4a7aaa; font-size:11px; font-style:italic; }
QLabel#placeholder { color:#1e2e48; font-size:13px; }
QLabel#estNombre   { font-size:14px; color:#cbd5e1; }

/* ── Separador ──────────────────────────────────────── */
QFrame#sep { color:#0f1c30; max-height:1px; }

/* ── ComboBox — selector doble para mayor especificidad ── */
QComboBox, QComboBox#combo {
    background: #0e1f3d;
    border: 1px solid #1e3a6e;
    border-radius: 6px;
    padding: 7px 36px 7px 12px;
    color: #e2eaf8;
    font-size: 13px;
}
QComboBox:hover,   QComboBox#combo:hover   { border-color: #2a5090; }
QComboBox:focus,   QComboBox#combo:focus   { border-color: #3b82f6; }
QComboBox:disabled,QComboBox#combo:disabled{ color:#2a3a58; background:#080e1a; }

QComboBox::drop-down, QComboBox#combo::drop-down {
    border: none; width: 28px;
    subcontrol-origin: padding;
    subcontrol-position: right center;
}
QComboBox::down-arrow, QComboBox#combo::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #4a6fa0;
    width: 0; height: 0;
}

/* ── Popup list ────────────────────────────────────── */
QComboBox QAbstractItemView {
    background: #0d1a30;
    border: 1px solid #1e3a6e;
    selection-background-color: #1a3560;
    color: #e2eaf8;
    outline: none;
    padding: 2px;
    show-decoration-selected: 1;
}
QComboBox QAbstractItemView::item {
    color: #e2eaf8;
    background: #0d1a30;
    padding: 6px 14px;
    min-height: 26px;
}
QComboBox QAbstractItemView::item:selected,
QComboBox QAbstractItemView::item:hover {
    background: #1a3a6a;
    color: #ffffff;
}

/* ── Botones ────────────────────────────────────────── */
QPushButton#btn {
    background:#163a96; color:#fff; border:none;
    border-radius:7px; padding:8px 20px;
    font-weight:600; min-width:100px;
}
QPushButton#btn:hover    { background:#1d4bbf; }
QPushButton#btn:pressed  { background:#102e78; }
QPushButton#btn:disabled { background:#0f1c30; color:#2a3a58; }

QPushButton#btnBack {
    background:#0f1c30; color:#64748b;
    border:1px solid #172340; border-radius:7px;
    padding:6px 14px; font-size:12px;
}
QPushButton#btnBack:hover { color:#94a3b8; border-color:#253660; }

QPushButton#btnCsv {
    background:#14532d; color:#4ade80;
    border:1px solid #166534; border-radius:7px;
    padding:8px 16px; font-weight:600;
}
QPushButton#btnCsv:hover    { background:#166534; }
QPushButton#btnCsv:disabled { background:#0f1c30; color:#2a3a58; border-color:#172340; }

/* ── Input búsqueda ─────────────────────────────────── */
QLineEdit#search {
    background:#0b1629; border:1px solid #1e3a6e;
    border-radius:7px; padding:8px 12px; color:#d6e0f4;
}
QLineEdit#search:focus { border-color:#3b82f6; }

/* ── Scroll ─────────────────────────────────────────── */
QScrollArea#scrollArea, QWidget#container { background:transparent; }
QScrollBar:vertical { background:#07101f; width:5px; border-radius:3px; }
QScrollBar::handle:vertical { background:#1e3a6e; border-radius:3px; min-height:24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
"""


def fix_combo_palette(combo):
    """
    Llama esto después de crear cada QComboBox.
    Fuerza colores via QPalette para que funcione
    incluso cuando el QSS es ignorado por el tema nativo.
    """
    from PySide6.QtGui import QPalette, QColor
    pal = combo.palette()
    txt   = QColor("#e2eaf8")
    bg    = QColor("#0e1f3d")
    sel   = QColor("#1a3a6a")
    seltx = QColor("#ffffff")
    dis   = QColor("#2a3a58")

    for role, color in [
        (QPalette.Text,             txt),
        (QPalette.WindowText,       txt),
        (QPalette.ButtonText,       txt),
        (QPalette.Base,             bg),
        (QPalette.Window,           bg),
        (QPalette.Button,           bg),
        (QPalette.Highlight,        sel),
        (QPalette.HighlightedText,  seltx),
        (QPalette.PlaceholderText,  dis),
    ]:
        pal.setColor(QPalette.Active,   role, color)
        pal.setColor(QPalette.Inactive, role, color)
        pal.setColor(QPalette.Disabled, role, dis if role == QPalette.Text else color)

    combo.setPalette(pal)
    combo.view().setPalette(pal)   # también el popup
