#!/usr/bin/env python3
"""
SENAMHI — Mejorado para datos completos 2021-2026
- Parsea flexiblemente el nuevo formato de columnas
- Obtiene todos los períodos disponibles (sin limitantes)
- Maneja captchas con Qt WebEngine

pip install PySide6 PySide6-WebEngine beautifulsoup4 selenium webdriver-manager requests curl_cffi
"""
import sys, os, re, io, csv, time, json
from bs4 import BeautifulSoup

BASE = "https://www.senamhi.gob.pe/mapas/mapa-estaciones-2/"

HEADERS = {
    "User-Agent":      ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
    "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}

# ══════════════════════════════════════════════════════════════════
#  DRIVERS
# ══════════════════════════════════════════════════════════════════

def _headless():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    o = Options()
    for a in ["--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
              "--disable-gpu", "--window-size=1280,800", "--log-level=3",
              "--blink-settings=imagesEnabled=false"]:
        o.add_argument(a)
    o.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=o)


def _quit(d):
    try: d.quit()
    except: pass


def _http_get(url, timeout=15):
    try:
        from curl_cffi import requests as cr
        r = cr.get(url, headers=HEADERS, impersonate="chrome", timeout=timeout)
        r.raise_for_status()
        return r.text
    except ImportError:
        import requests
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.text


# ══════════════════════════════════════════════════════════════════
#  JS — snapshot de la página de datos
# ══════════════════════════════════════════════════════════════════

_JS_SNAPSHOT = r"""
(function() {
    var o = { periodos: [], iframeHtml: "", mainHtml: "", containerDivs: [], err: "" };
    try {
        var sel = document.getElementById("CBOFiltro");
        if (sel) {
            var opts = sel.querySelectorAll("option");
            for (var i = 0; i < opts.length; i++) {
                var el = opts[i];
                if (el.value) o.periodos.push([el.value, el.textContent.trim()]);
            }
        }
        o.mainHtml = document.documentElement.outerHTML;
        var f = document.getElementById("contenedor");
        if (f) {
            var d = f.contentDocument || f.contentWindow.document;
            if (d && d.documentElement) {
                o.iframeHtml = d.documentElement.outerHTML;
                var cont = d.getElementById("container");
                if (cont) {
                    var divs = cont.getElementsByTagName("div");
                    for (var j = 0; j < divs.length && j < 4; j++) {
                        o.containerDivs.push(divs[j].innerText.trim().replace(/\s+/g, ' '));
                    }
                }
            }
        }
    } catch (e) { o.err = String(e); }
    return JSON.stringify(o);
})()
"""


def _js_select_periodo(val):
    v = json.dumps(str(val))
    return f"""
(function() {{
    var val = {v};
    var s = document.getElementById("CBOFiltro");
    if (!s) return "no_cbo";
    s.value = val;
    if (typeof s.onchange === "function") s.onchange();
    s.dispatchEvent(new Event("change", {{ bubbles: true }}));
    try {{
        if (s.form) {{ s.form.target = "contenedor"; s.form.submit(); }}
    }} catch (e) {{}}
    return "ok";
}})()
"""


# ══════════════════════════════════════════════════════════════════
#  JS Leaflet
# ══════════════════════════════════════════════════════════════════

_JS_LEAFLET = r"""
return (function() {
    var out = [];
    var layers = [];
    function addMap(m) {
        if (!m || !m._layers) return;
        Object.values(m._layers).forEach(function(layer) {
            if (!layer || !layer.options || !layer.options.title) return;
            layers.push(layer);
        });
    }
    document.querySelectorAll('.leaflet-container').forEach(function(c) { addMap(c._leaflet_map); });
    if (window.mymap) addMap(window.mymap);
    if (!layers.length) {
        document.querySelectorAll('img.leaflet-marker-icon[title]').forEach(function(img) {
            if (img.title) layers.push({options:{title:img.title}, getPopup:function(){return null;}});
        });
    }
    layers.forEach(function(layer) {
        var title = layer.options.title;
        var popup = layer.getPopup ? layer.getPopup() : null;
        var content = "";
        try { content = popup ? popup.getContent() : ""; } catch(e) {}
        var m = content.match(/cod=(\d+)[^"']*tipo_esta=(\w+)[^"']*cate=(\w+)/);
        out.push(m
            ? {title:title, cod:m[1], tipo_esta:m[2], cate:m[3]}
            : {title:title, cod:"",   tipo_esta:"",    cate:""});
    });
    return out;
})();
"""

# ══════════════════════════════════════════════════════════════════
#  PARSING HTML — MEJORADO PARA NUEVO FORMATO
# ══════════════════════════════════════════════════════════════════

def _first_cell_is_data_row(tr):
    cell = tr.find(["td", "th"])
    if not cell: return False
    t = cell.get_text(strip=True)
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}", t) or re.match(r"^\d{1,2}/\d{1,2}/\d{4}", t))


def _parse_headers_grid(hdr_rows):
    """Parsea headers con colspan/rowspan como grid 2D"""
    if not hdr_rows: return []
    ncols = max(sum(int(c.get("colspan", 1)) for c in tr.find_all(["th", "td"])) for tr in hdr_rows)
    if ncols == 0: return []
    grid = [[None] * ncols for _ in hdr_rows]
    for ri, tr in enumerate(hdr_rows):
        ci = 0
        for cell in tr.find_all(["th", "td"]):
            while ci < ncols and grid[ri][ci] is not None: ci += 1
            txt = re.sub(r"\s+", " ", cell.get_text(strip=True))
            rs, cs = int(cell.get("rowspan", 1)), int(cell.get("colspan", 1))
            for rr in range(ri, min(ri + rs, len(hdr_rows))):
                for cc in range(ci, min(ci + cs, ncols)):
                    grid[rr][cc] = txt
            ci += cs
    headers = []
    for c in range(ncols):
        parts = []
        for r in range(len(grid)):
            cell = grid[r][c]
            if cell and cell not in parts: parts.append(cell)
        headers.append(" ".join(parts).strip())
    return headers


def _normalize_header(h):
    """
    Normaliza variaciones de nombres de columnas:
    - "TEMPERATURA (°C)" → "TEMPERATURA_MAX/MIN"
    - "TEMPERATURA (C)" → "TEMPERATURA_MAX/MIN"
    - "HUMEDAD RELATIVA (%)" → "HUMEDAD_RELATIVA"
    - etc.
    """
    h_upper = h.upper().strip()
    
    # Detectar si es parte de TEMPERATURA
    if "TEMPERATURA" in h_upper:
        if "MAX" in h_upper:
            return "TEMPERATURA_MAX"
        elif "MIN" in h_upper:
            return "TEMPERATURA_MIN"
        else:
            return "TEMPERATURA"
    
    # Humedad
    if "HUMEDAD" in h_upper:
        return "HUMEDAD_RELATIVA"
    
    # Precipitación
    if "PRECIPITACIÓN" in h_upper or "PRECIPITACION" in h_upper:
        if "TOTAL" in h_upper:
            return "PRECIPITACION_TOTAL"
        return "PRECIPITACION"
    
    # Fecha
    if "AÑO" in h_upper or "MES" in h_upper or "DÍA" in h_upper or "DIA" in h_upper:
        return "FECHA"
    
    return h_upper


def _parse_tabla(soup):
    """Parsea tabla HTML con flexibilidad para diferentes formatos"""
    tbl = soup.find("table", id="dataTable")
    if not tbl:
        for t in soup.find_all("table"):
            if t.find("tbody") and t.find("tbody").find_all("tr"): 
                tbl = t
                break
    if not tbl: 
        tbl = soup.find("table")
    if not tbl: 
        return [], []
    
    thead = tbl.find("thead")
    all_tr = tbl.find_all("tr")
    
    if thead:
        hdr_rows = thead.find_all("tr")
        tbody = tbl.find("tbody")
        data_trs = tbody.find_all("tr") if tbody else all_tr[len(hdr_rows):]
    else:
        n_hdr = 0
        for tr in all_tr:
            if _first_cell_is_data_row(tr): 
                break
            n_hdr += 1
        if n_hdr == 0 and all_tr: 
            n_hdr = 1
        hdr_rows = all_tr[:n_hdr]
        data_trs = all_tr[n_hdr:]
    
    headers = _parse_headers_grid(hdr_rows)
    if not headers and hdr_rows:
        headers = [c.get_text(strip=True) for c in hdr_rows[0].find_all(["th", "td"])]
    
    # Normalizar headers para consistencia
    headers_normalized = [_normalize_header(h) for h in headers]
    
    rows = []
    nh = len(headers)
    for tr in data_trs:
        vals = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if not vals or not any(v.strip() for v in vals): 
            continue
        if nh and len(vals) != nh:
            vals = (list(vals) + [""] * nh)[:nh]
        rows.append(vals)
    
    return headers_normalized, rows


def _parse_meta(soup):
    """Parsea metadatos de la estación"""
    meta = {}
    tbl = soup.find("table", id="tableHidden")
    if not tbl:
        div = soup.find("div", hidden=True)
        if div: 
            tbl = div.find("table")
    if not tbl: 
        return meta
    
    trs = tbl.find_all("tr")
    if trs:
        f = trs[0].find("font")
        if f: 
            meta["Estacion"] = re.sub(r"\s+", " ", f.get_text()).replace("Estacion :", "").strip()
    
    for tr in trs[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        for i in range(0, len(cells)-1, 2):
            k = cells[i].replace(":", "").replace("\xa0", "").strip()
            v = cells[i+1].strip() if i+1 < len(cells) else ""
            if k and v and len(k) < 40: 
                meta[k] = v
    
    return meta


def _periodos_desde_soup(soup):
    """Extrae TODOS los períodos disponibles del dropdown"""
    sel = soup.find("select", id="CBOFiltro")
    if not sel: 
        return []
    return [(opt.get("value","").strip(), opt.get_text(strip=True))
            for opt in sel.find_all("option") if opt.get("value","").strip()]


# ══════════════════════════════════════════════════════════════════
#  WebEngine helpers
# ══════════════════════════════════════════════════════════════════

def _run_js_sync(page, script):
    from PySide6.QtCore import QEventLoop
    loop = QEventLoop()
    out = [None]
    def done(res): 
        out[0] = res
        loop.quit()
    page.runJavaScript(script, done)
    loop.exec()
    return out[0]


def _delay_ms(ms):
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _tabla_desde_snapshot_json(jstr):
    """Extrae tabla y períodos del JSON snapshot"""
    if not jstr: 
        return [], [], [], [], []
    try: 
        data = json.loads(jstr)
    except: 
        return [], [], [], [], []
    
    periodos = [(a, b) for a, b in (data.get("periodos") or [])]
    meta = {}
    if data.get("mainHtml"): 
        meta = _parse_meta(BeautifulSoup(data["mainHtml"], "html.parser"))
    
    hdrs, rows = [], []
    if data.get("iframeHtml"): 
        hdrs, rows = _parse_tabla(BeautifulSoup(data["iframeHtml"], "html.parser"))
    
    return periodos, meta, hdrs, rows, data.get("containerDivs") or []


# ══════════════════════════════════════════════════════════════════
#  API — CSV GRANULAR: UN ARCHIVO POR MES
# ══════════════════════════════════════════════════════════════════

def api_csv_por_mes(page, desde, hasta, nombre_est, meta, periodos_all, carpeta, cb=None):
    """
    Itera cada mes en [desde, hasta] y guarda un CSV independiente por mes.
    Retorna lista de rutas guardadas.
    """
    def p(m):
        if cb: 
            cb(m)

    ds = str(desde).strip()
    hs = str(hasta).strip()

    # Filtrar y ordenar los períodos del rango
    en_rango = [(v.strip(), lbl) for v, lbl in periodos_all if ds <= v.strip() <= hs]

    if not en_rango:
        p(f"Sin períodos en rango {ds} a {hs}.")
        return []

    p(f"{len(en_rango)} mes(es) a descargar ({en_rango[0][1]} → {en_rango[-1][1]})")

    # Nombre base del archivo
    base = "senamhi_" + re.sub(r"[^\w.\-]", "_", nombre_est).strip("_")

    guardados = []
    for i, (cod, lbl) in enumerate(en_rango, 1):
        p(f"[{i}/{len(en_rango)}] {lbl} ({cod})…")
        try:
            _run_js_sync(page, _js_select_periodo(cod))
            _delay_ms(1000)
            snap = _run_js_sync(page, _JS_SNAPSHOT)
            _, _, hdrs, rows, container_divs = _tabla_desde_snapshot_json(snap)

            if not rows:
                p(f"  ⚠ Sin datos para {lbl}, se omite.")
                continue

            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")

            # Metadatos
            if meta:
                for k, v in meta.items():
                    w.writerow([k, v])
                w.writerow([])

            # Info del container
            if len(container_divs) >= 2:
                w.writerow([container_divs[0], container_divs[1]])
            elif container_divs:
                w.writerow([container_divs[0]])

            # Cabeceras
            if hdrs:
                w.writerow(hdrs)

            # Datos
            nh = len(hdrs)
            for row in rows:
                if nh and len(row) != nh:
                    row = (list(row) + [""] * nh)[:nh]
                w.writerow(row)

            # Guardar
            nombre_archivo = f"{base}_{cod}.csv"
            ruta = os.path.join(carpeta, nombre_archivo)
            with open(ruta, "wb") as f:
                f.write(("\ufeff" + buf.getvalue()).encode("utf-8"))

            guardados.append(ruta)
            p(f"  ✓ {len(rows)} registros → {nombre_archivo}")

        except Exception as e:
            p(f"  ⚠ Error en {lbl} ({cod}): {e}")

    return guardados


# ══════════════════════════════════════════════════════════════════
#  API pública
# ══════════════════════════════════════════════════════════════════

def api_deptos():
    try:
        html = _http_get("https://www.senamhi.gob.pe/main.php?p=estaciones", timeout=12)
        soup = BeautifulSoup(html, "html.parser")
        menu = soup.find("div", {"aria-labelledby": "dropdown01"})
        if not menu: 
            raise ValueError
        out = {}
        for a in menu.find_all("a", class_="dropdown-item"):
            n = a.get_text(strip=True)
            h = a.get("href", "")
            if "dp=" in h:
                sl = h.split("dp=")[1].split("&")[0]
                if n and sl: 
                    out[n] = sl
        return out
    except:
        return {
            "Amazonas":"amazonas","Áncash":"ancash","Apurímac":"apurimac",
            "Arequipa":"arequipa","Ayacucho":"ayacucho","Cajamarca":"cajamarca",
            "Cusco":"cusco","Huancavelíca":"huancavelica","Huánuco":"huanuco",
            "Ica":"ica","Junín":"junin","La Libertad":"la-libertad",
            "Lambayeque":"lambayeque","Lima / Callao":"lima","Loreto":"loreto",
            "Madre de Dios":"madre-de-dios","Moquegua":"moquegua","Pasco":"pasco",
            "Piura":"piura","Puno":"puno","San Martín":"san-martin",
            "Tacna":"tacna","Tumbes":"tumbes","Ucayali":"ucayali",
        }


def api_estaciones(dp_key, cb=None):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    def p(m):
        if cb: 
            cb(m)

    drv = None
    try:
        p("Cargando mapa...")
        drv = _headless()
        drv.get(f"{BASE}?dp={dp_key}")
        WebDriverWait(drv, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img.leaflet-marker-icon[title]"))
        )
        time.sleep(1.5)
        p("Extrayendo estaciones...")
        raw = drv.execute_script(_JS_LEAFLET) or []
        sin = [r for r in raw if not r.get("cod")]
        if sin and len(sin) > len(raw) * 0.5:
            p("Abriendo popups para obtener códigos...")
            markers = drv.find_elements(By.CSS_SELECTOR, "img.leaflet-marker-icon[title]")
            for mk in markers:
                try: 
                    drv.execute_script("arguments[0].click();", mk)
                    time.sleep(0.04)
                except: 
                    pass
            try: 
                drv.find_element(By.CSS_SELECTOR, ".leaflet-popup-close-button").click()
            except: 
                pass
            time.sleep(0.5)
            raw = drv.execute_script(_JS_LEAFLET) or []
        
        ests, seen = [], set()
        for item in raw:
            t = (item.get("title") or "").strip()
            if not t or t in seen: 
                continue
            seen.add(t)
            ps = t.split()
            if len(ps) >= 3: 
                sub, tp, nm = ps[-1].upper(), ps[-2].upper(), " ".join(ps[:-2])
            elif len(ps) == 2: 
                sub, tp, nm = "", ps[-1].upper(), ps[0]
            else: 
                sub, tp, nm = "", "—", t
            ests.append({"nombre": nm.title(), "tipo": tp, "subtipo": sub,
                         "dp_key": dp_key, "cod": item.get("cod",""),
                         "tipo_api": item.get("tipo_esta",""), "cate_api": item.get("cate","")})
        
        sin2 = [e for e in ests if not e["cod"]]
        if sin2:
            p(f"Buscando {len(sin2)} codigos en el fuente...")
            src = drv.page_source
            for est in sin2:
                pat = (r'(?i)' + re.escape(est["nombre"].upper()) +
                       r'.{0,500}?cod=(\d+)[^"\']*tipo_esta=(\w+)[^"\']*cate=(\w+)')
                m = re.search(pat, src, re.DOTALL)
                if m:
                    est["cod"] = m.group(1)
                    est["tipo_api"] = m.group(2)
                    est["cate_api"] = m.group(3)
        
        ests.sort(key=lambda x: (x["tipo"], x["nombre"]))
        con = sum(1 for e in ests if e["cod"])
        p(f"{len(ests)} estaciones ({con} con codigo)")
        return ests
    finally:
        _quit(drv)


def api_curl_estacion(info, cb=None):
    """Obtiene datos iniciales sin captcha (curl GET simple)"""
    def p(m):
        if cb: 
            cb(m)
    
    cod = info["cod"]
    tipo = info["tipo_api"]
    cate = info["cate_api"]
    url = f"{BASE}map_red_graf.php?cod={cod}&estado=REAL&tipo_esta={tipo}&cate={cate}&cod_old="
    p("Consultando estacion...")
    html = _http_get(url, timeout=25)
    soup = BeautifulSoup(html, "html.parser")
    periodos = _periodos_desde_soup(soup)
    meta = _parse_meta(soup)
    hdrs, rows = _parse_tabla(soup)
    return {"url": url, "periodos": periodos, "meta": meta,
            "hdrs": hdrs, "rows": rows, "curl_ok": len(rows) > 0}


# ══════════════════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════════════════

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QScrollArea, QFrame, QLineEdit, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QSizePolicy, QTextEdit, QSplitter,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QFont, QPalette, QColor

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except ImportError:
    QWebEngineView = None
    HAS_WEBENGINE = False


def _fix_combo(cb):
    p = cb.palette()
    for role, c in [
        (QPalette.Text, "#111111"), (QPalette.Base, "#ffffff"),
        (QPalette.Button, "#ffffff"), (QPalette.ButtonText, "#111111"),
        (QPalette.Highlight, "#0078d4"), (QPalette.HighlightedText, "#ffffff"),
    ]:
        for st in [QPalette.Active, QPalette.Inactive]:
            p.setColor(st, role, QColor(c))
        p.setColor(QPalette.Disabled, role,
                   QColor("#888888" if role == QPalette.Text else c))
    cb.setPalette(p)
    cb.view().setPalette(p)
    cb.setStyleSheet(
        "QComboBox { color: #111111; background: #ffffff; font-size: 13px; font-weight: 600; "
        "padding: 4px 8px; min-height: 22px; }"
        "QComboBox QAbstractItemView { color: #111111; background: #ffffff; font-size: 13px; }"
    )


class Worker(QThread):
    ok = Signal(object)
    err = Signal(str)
    prog = Signal(str)
    
    def __init__(self, fn):
        super().__init__()
        self._fn = fn
    
    def run(self):
        try:
            self.ok.emit(self._fn(self.prog.emit))
        except Exception as e:
            self.err.emit(str(e))


TIPOS = {"MET": "🟢", "HID": "🔵", "PLU": "🟡"}


class Card(QFrame):
    clicked = Signal(dict)
    
    def __init__(self, idx, est):
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


class PanelDatos(QWidget):
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
        self._ui()

    def _ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(10,10,10,10)
        v.setSpacing(8)

        # Barra superior
        top = QHBoxLayout()
        self.b_back = QPushButton("← Volver")
        self.b_back.setMaximumWidth(100)
        self.b_back.clicked.connect(self._volver)
        self.l_nom = QLabel("")
        self.l_nom.setFont(QFont("Arial", 14, QFont.Bold))
        top.addWidget(self.b_back)
        top.addWidget(self.l_nom, 1)
        v.addLayout(top)

        # Tabs
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

        # Combo período (vista previa)
        r1 = QHBoxLayout()
        r1.setSpacing(6)
        self.cb_a = QComboBox()
        self.cb_a.setEnabled(False)
        self.cb_a.setMaxVisibleItems(16)
        _fix_combo(self.cb_a)
        self.cb_a.currentIndexChanged.connect(self._on_anio_changed)
        r1.addWidget(QLabel("Período:"))
        r1.addWidget(self.cb_a, 1)
        v.addLayout(r1)

        # ── Fila de rango + botones de descarga ──────────────────
        r2 = QHBoxLayout()
        r2.setSpacing(6)
        self.cb_d = QComboBox()
        self.cb_d.setEnabled(False)
        self.cb_d.setMaxVisibleItems(16)
        _fix_combo(self.cb_d)
        self.cb_h = QComboBox()
        self.cb_h.setEnabled(False)
        self.cb_h.setMaxVisibleItems(16)
        _fix_combo(self.cb_h)

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

        # Splitter: webview + tabla/info
        self.split = QSplitter(Qt.Vertical)
        self.webview = None
        if HAS_WEBENGINE and QWebEngineView:
            self.webview = QWebEngineView()
            self.webview.setMinimumHeight(260)
            self.webview.setVisible(False)
            self.split.addWidget(self.webview)
        else:
            lbl = QLabel("Para ver datos con captcha, instala: pip install PySide6-WebEngine")
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

    # ── carga ─────────────────────────────────────────────────────

    def cargar(self, est):
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

    def _post_curl(self, data):
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
            self.l_st.setText("✓ Datos vía curl. Para descargar CSV completa el captcha (necesita WebEngine).")
            return
        if not HAS_WEBENGINE or not self.webview:
            self._fill_combos()
            self._fill_info_text()
            self.l_st.setText("Instala PySide6-WebEngine para el captcha y la descarga CSV.")
            QMessageBox.warning(self, "WebEngine",
                "pip install PySide6-WebEngine\n\nNecesario para descargar CSVs dentro de la app.")
            return
        self._poll_n = 0
        self.webview.setVisible(True)
        self.split.setSizes([340, 320])
        self.l_st.setText("Completa el captcha en el panel superior…")
        self.webview.load(QUrl(self._url_datos))
        QTimer.singleShot(2500, self._start_poll_embed)

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
        self.webview.page().runJavaScript(_JS_SNAPSHOT, self._on_snap_result)

    def _on_snap_result(self, jstr):
        per, meta, hdrs, rows, _ = _tabla_desde_snapshot_json(jstr)
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

    # ── combos ────────────────────────────────────────────────────

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
        lines = [f"{self._info.get('nombre','')}  (cod. {self._info.get('cod','')})", ""]
        for k, v in self._meta.items(): 
            lines.append(f"{k}: {v}")
        self.info_text.setPlainText("\n".join(lines))

    # ── cambio de período ─────────────────────────────────────────

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
            _run_js_sync(self._page, _js_select_periodo(anio))
            _delay_ms(900)
            snap = _run_js_sync(self._page, _JS_SNAPSHOT)
            _, _, hdrs, rows, _ = _tabla_desde_snapshot_json(snap)
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

    # ── descarga ──────────────────────────────────────────────────

    def _pedir_carpeta(self):
        return QFileDialog.getExistingDirectory(self, "Selecciona la carpeta de destino")

    def _csv_rango(self):
        """Un CSV por mes para el rango Desde→Hasta seleccionado."""
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
        """Un CSV por mes para TODOS los meses disponibles."""
        if not self._periodos or not self._page:
            self.l_st.setText("Sin períodos disponibles.")
            return
        carpeta = self._pedir_carpeta()
        if not carpeta: 
            return
        ds = str(self._periodos[0][0]).strip()
        hs = str(self._periodos[-1][0]).strip()
        n = len(self._periodos)
        self._busy(True)
        self._start(f"Descargando TODO: {n} mes(es)…")
        nombre = self._info.get("nombre", "estacion")
        QTimer.singleShot(0, lambda: self._run_descarga(ds, hs, carpeta, nombre))

    def _run_descarga(self, ds, hs, carpeta, nombre):
        try:
            guardados = api_csv_por_mes(
                self._page, ds, hs, nombre,
                dict(self._meta), self._periodos,
                carpeta, self._on_prog
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
        extra = f"\n… y {len(guardados)-20} más" if len(guardados) > 20 else ""
        QMessageBox.information(
            self, "Descarga completada",
            f"{len(guardados)} CSV (uno por mes):\n\n"
            + "\n".join(nombres) + extra
            + f"\n\nCarpeta:\n{carpeta}"
        )

    # ── tabs ──────────────────────────────────────────────────────

    def _show_tabla(self):
        self.btn_tabla.setChecked(True)
        self.btn_estacion.setChecked(False)
        self.stack2.setCurrentIndex(0)

    def _show_estacion(self):
        self.btn_tabla.setChecked(False)
        self.btn_estacion.setChecked(True)
        self.stack2.setCurrentIndex(1)

    # ── utilidades ────────────────────────────────────────────────

    def _volver(self):
        self._cerrar_session()
        self.volver.emit()

    def _cerrar_session(self):
        self._poll_tmr.stop()
        self._page = None
        if self.webview:
            self.webview.load(QUrl("about:blank"))
            self.webview.setVisible(False)

    def _busy(self, b):
        ok = self._page is not None and bool(self._periodos)
        self.b_csv.setEnabled(not b and ok)
        self.b_all.setEnabled(not b and ok)
        self.cb_a.setEnabled(not b and ok)
        self.cb_d.setEnabled(not b and bool(self._periodos))
        self.cb_h.setEnabled(not b and bool(self._periodos))

    def _on_prog(self, m):
        self._sb = m
        self.l_st.setText(m)
    
    def _on_err(self, m):
        self._stop()
        self._busy(False)
        self.l_st.setText(f"Error: {m[:300]}")
    
    def _track(self, w):
        self._workers.append(w)
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        w.finished.connect(w.deleteLater)
    
    def _tick(self):
        self._dot = (self._dot+1)%4
        self.l_st.setText(self._sb + "."*self._dot)
    
    def _start(self, m):
        self._sb = m
        self._dot = 0
        self._tmr.start(400)
    
    def _stop(self):
        self._tmr.stop()
    
    def closeEvent(self, e):
        self._cerrar_session()
        super().closeEvent(e)


# ══════════════════════════════════════════════════════════════════
#  Ventana principal
# ══════════════════════════════════════════════════════════════════

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SENAMHI — Estaciones")
        self.setMinimumSize(700, 500)
        self.resize(850, 600)
        self._deptos = {}
        self._todas = []
        self._sb = ""
        self._dot = 0
        self._workers = []
        self._ui()
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._tick)
        self._load_deptos()

    def _ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(10,10,10,10)
        v.setSpacing(6)
        t = QLabel("SENAMHI")
        t.setFont(QFont("Arial", 16, QFont.Bold))
        v.addWidget(t)
        self.stack = QStackedWidget()

        pg = QWidget()
        pg_v = QVBoxLayout(pg)
        pg_v.setContentsMargins(0,0,0,0)
        pg_v.setSpacing(6)
        
        r2 = QHBoxLayout()
        r2.setSpacing(6)
        self.cb = QComboBox()
        self.cb.setEnabled(False)
        _fix_combo(self.cb)
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
        self.vl.setContentsMargins(0,0,0,0)
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

        self.panel = PanelDatos()
        self.panel.volver.connect(lambda: self.stack.setCurrentIndex(0))
        self.stack.addWidget(self.panel)
        v.addWidget(self.stack, 1)

    def _load_deptos(self):
        self._start("Cargando departamentos...")
        w = Worker(lambda p: api_deptos())
        w.ok.connect(self._on_deptos)
        w.err.connect(self._on_err)
        self._track(w)
        w.start()

    def _on_deptos(self, d):
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

    def _on_est(self, ests):
        self._stop()
        self._todas = ests
        self._render(ests)
        self.b.setEnabled(True)

    def _clear(self):
        while self.vl.count() > 1:
            it = self.vl.takeAt(0)
            if it and it.widget(): 
                it.widget().deleteLater()

    def _render(self, ests):
        self._clear()
        for i, e in enumerate(ests, 1):
            c = Card(i, e)
            c.clicked.connect(self._on_card)
            self.vl.insertWidget(i-1, c)
        con = sum(1 for e in ests if e.get("cod"))
        self.l_cnt.setText(f"{len(ests)} estaciones  ·  {con} con código")

    def _filtrar(self, txt):
        if not self._todas: 
            return
        t = txt.strip().lower()
        self._render([e for e in self._todas
                      if t in e["nombre"].lower() or t in e["tipo"].lower()])

    def _on_card(self, est):
        self.panel.cargar(est)
        self.stack.setCurrentIndex(1)

    def _on_prog(self, m):
        self._sb = m
        self.l_st.setText(m)
    
    def _on_err(self, m):
        self._stop()
        self.l_st.setText(f"Error: {m[:150]}")
        self.b.setEnabled(True)
    
    def _track(self, w):
        self._workers.append(w)
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        w.finished.connect(w.deleteLater)
    
    def _tick(self):
        self._dot = (self._dot+1)%4
        self.l_st.setText(self._sb + "."*self._dot)
    
    def _start(self, m):
        self._sb = m
        self._dot = 0
        self._tmr.start(400)
    
    def _stop(self):
        self._tmr.stop()
    
    def closeEvent(self, e):
        if hasattr(self, "panel"): 
            self.panel._cerrar_session()
        super().closeEvent(e)


if __name__ == "__main__":
    if HAS_WEBENGINE:
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())