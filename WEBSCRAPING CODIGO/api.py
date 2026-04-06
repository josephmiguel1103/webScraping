"""
senamhi/api.py — Todo via curl_cffi (sin Selenium para datos).

Flujo:
  1. obtener_estaciones()   → Selenium headless (Leaflet, sin CF)
  2. obtener_cod_periodos() → curl_cffi: GET map_red_graf.php
                              parsea CBOFiltro + tableHidden (metadata)
  3. obtener_tabla()        → curl_cffi: POST/GET con CBOFiltro=año
                              parsea #dataTable y retorna headers+rows
  4. descargar_rango_csv()  → bucle sobre años, concatena filas → CSV

Instalar: pip install curl_cffi beautifulsoup4 selenium webdriver-manager
"""
import re
import io
import csv
import time
from bs4 import BeautifulSoup

BASE = "https://www.senamhi.gob.pe/mapas/mapa-estaciones-2/"
_UA  = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36")


# ─── Session con impersonación Chrome (pasa Cloudflare) ──────────
def _sess():
    """
    curl_cffi imita el TLS fingerprint de Chrome → pasa CF sin captcha.
    Fallback a requests si no está instalado (puede fallar con CF).
    """
    try:
        from curl_cffi.requests import Session
        s = Session(impersonate="chrome120")
        s.headers.update({"User-Agent": _UA,
                          "Accept-Language": "es-PE,es;q=0.9"})
        return s
    except ImportError:
        import requests
        s = requests.Session()
        s.headers.update({"User-Agent": _UA,
                          "Accept-Language": "es-PE,es;q=0.9"})
        return s


# ─── Selenium headless solo para el mapa Leaflet ─────────────────
def _driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--no-sandbox")
    o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--disable-gpu")
    o.add_argument("--window-size=1280,800")
    o.add_argument("--log-level=3")
    o.add_argument("--blink-settings=imagesEnabled=false")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_experimental_option("excludeSwitches", ["enable-logging","enable-automation"])
    drv = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=o)
    drv.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return drv


# ─── Departamentos ────────────────────────────────────────────────
def obtener_departamentos() -> dict:
    try:
        r    = _sess().get("https://www.senamhi.gob.pe/main.php?p=estaciones", timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        menu = soup.find("div", {"aria-labelledby": "dropdown01"})
        if not menu: raise ValueError("dropdown no encontrado")
        out = {}
        for a in menu.find_all("a", class_="dropdown-item"):
            n = a.get_text(strip=True)
            h = a.get("href","")
            if "dp=" in h:
                slug = h.split("dp=")[1].split("&")[0]
                if n and slug: out[n] = slug
        return out
    except Exception as ex:
        print(f"[api] fallback deptos: {ex}")
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


# ─── Estaciones — Selenium headless (Leaflet, sin CF) ────────────
def obtener_estaciones(dp_key: str, cb=None) -> list[dict]:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    def _p(m):
        if cb: cb(m)

    drv = None
    try:
        _p("Iniciando navegador")
        drv = _driver()
        _p("Cargando mapa")
        drv.get(f"{BASE}?dp={dp_key}")
        WebDriverWait(drv, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img.leaflet-marker-icon[title]"))
        )
        time.sleep(1.2)
        titles = drv.execute_script("""
            return Array.from(
                document.querySelectorAll('img.leaflet-marker-icon[title]')
            ).map(i=>i.getAttribute('title'));
        """)
        ests, seen = [], set()
        for t in (titles or []):
            t = (t or "").strip()
            if not t or t in seen: continue
            seen.add(t)
            p = t.split()
            if len(p) >= 3: sub,tipo,nom = p[-1].upper(),p[-2].upper()," ".join(p[:-2])
            elif len(p)==2: sub,tipo,nom = "",p[-1].upper(),p[0]
            else:           sub,tipo,nom = "","—",t
            ests.append({"nombre":nom.title(),"tipo":tipo,"subtipo":sub,
                         "dp_key":dp_key,"cod":"","tipo_api":"","cate_api":""})
        ests.sort(key=lambda x:(x["tipo"],x["nombre"]))
        return ests
    finally:
        if drv:
            try: drv.quit()
            except: pass


# ─── Obtener cod desde marker click (headless, solo attr) ────────
def _cod_desde_click(drv, nombre: str) -> dict | None:
    from selenium.webdriver.common.by import By
    markers = drv.find_elements(By.CSS_SELECTOR, "img.leaflet-marker-icon[title]")
    nu = nombre.upper()
    target = None
    for m in markers:
        t = (m.get_attribute("title") or "").upper()
        p = t.split()
        nm = " ".join(p[:-2]) if len(p)>=3 else t
        if nm == nu: target=m; break
    if not target: return None
    drv.execute_script("arguments[0].click();", target)
    time.sleep(1.8)
    src = drv.execute_script("""
        var f=document.querySelector('.leaflet-popup-content iframe');
        return f?f.getAttribute('src'):null;
    """)
    if not src: return None
    params={}
    for part in src.split("?")[-1].split("&"):
        if "=" in part:
            k,v=part.split("=",1); params[k]=v
    cod=params.get("cod","")
    if not cod: return None
    return {"cod":cod,"tipo_api":params.get("tipo_esta","M"),
            "cate_api":params.get("cate","CO"),"estado":"REAL"}


# ─── Helpers de parsing HTML ──────────────────────────────────────
def _get_ajax_action(html: str) -> str | None:
    """
    Detecta si CBOFiltro tiene un action AJAX en el JS de la página.
    Busca patrones como: $.post('endpoint.php', ...) o $.get(...)
    o fetch('endpoint') tras el change del select.
    """
    patterns = [
        r"(?:post|get|ajax)\s*\(\s*['\"]([^'\"]+\.php[^'\"]*)['\"]",
        r"action\s*=\s*['\"]([^'\"]+\.php[^'\"]*)['\"]",
        r"url\s*:\s*['\"]([^'\"]+\.php[^'\"]*)['\"]",
    ]
    for pat in patterns:
        for m in re.finditer(pat, html, re.IGNORECASE):
            url = m.group(1)
            if "graf" in url or "data" in url or "est" in url:
                return url
    return None


def _parse_metadata(soup: BeautifulSoup) -> dict:
    """Lee #tableHidden para obtener depto/provincia/etc."""
    meta = {}
    tbl  = soup.find("table", id="tableHidden")
    if not tbl: return meta
    rows = tbl.find_all("tr")
    if rows:
        # Fila 0: nombre estación
        font = rows[0].find("font")
        if font: meta["nombre_oficial"] = font.get_text(strip=True).replace("Estación :","").strip()
    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        for i in range(0, len(cells)-1, 2):
            k = cells[i].replace(":","").replace("\xa0","").strip().lower()
            v = cells[i+1].strip()
            if k and v: meta[k] = v
    return meta


def _parse_tabla(soup: BeautifulSoup) -> tuple[list, list]:
    """
    Parsea #dataTable (estructura real de SENAMHI):
    - Primera fila: cabecera principal (colspan)
    - Segunda fila: sub-cabeceras (horas o columnas)
    - Resto: filas de datos
    Retorna (headers, rows).
    """
    tbl = soup.find("table", id="dataTable")
    if not tbl: return [], []

    # Construir headers aplanados desde las 2 primeras filas (rowspan/colspan)
    all_rows = tbl.find_all("tr")
    if not all_rows: return [], []

    # Extraer texto de th/td de las filas de cabecera
    header_rows = []
    data_start  = 0
    for i, tr in enumerate(all_rows):
        cells = tr.find_all(["th","td"])
        texts = [c.get_text(strip=True) for c in cells]
        # Si tiene bgcolor oscuro o todos son negrita → es cabecera
        is_hdr = tr.get("bgcolor") or all(c.find("b") for c in cells if c.get_text(strip=True))
        if is_hdr and i < 4:
            header_rows.append((cells, texts))
            data_start = i + 1
        else:
            if not header_rows: data_start = 0
            break

    # Construir lista de encabezados aplanada
    if len(header_rows) >= 2:
        # Fila 1: grupos (NIVEL DEL RIO, etc.)
        # Fila 2: sub-columnas (06, 10, 14, 18, PROMEDIO)
        row1_cells = header_rows[0][0]
        row2_cells = header_rows[1][0] if len(header_rows)>1 else []
        headers = []
        col_idx = 0
        for cell in row1_cells:
            cs   = int(cell.get("colspan","1"))
            rs   = int(cell.get("rowspan","1"))
            name = cell.get_text(strip=True)
            if rs >= 2 or cs == 1:
                headers.append(name)
            else:
                for sub in row2_cells[col_idx:col_idx+cs]:
                    headers.append(f"{name} {sub.get_text(strip=True)}")
                col_idx += cs - 1
            col_idx += 1
        if not headers:
            headers = [c.get_text(strip=True) for c in (row1_cells or row2_cells)]
    elif header_rows:
        headers = header_rows[0][1]
    else:
        # Sin cabecera detectada: usar primera fila
        first = all_rows[0].find_all(["th","td"])
        headers = [c.get_text(strip=True) for c in first]
        data_start = 1

    # Filas de datos
    rows = []
    for tr in all_rows[data_start:]:
        tds  = tr.find_all("td")
        vals = [td.get_text(" ", strip=True) for td in tds]
        if any(v.strip() for v in vals):
            rows.append(vals)

    return headers, rows


# ─── Fetch de página de datos con curl_cffi ───────────────────────
def _fetch_graf(sess, cod: str, tipo: str, cate: str,
                anio: str | None = None, cb=None) -> BeautifulSoup:
    """
    Intenta GET primero, luego POST con CBOFiltro.
    Detecta si el cambio de año usa AJAX y lo replica.
    """
    def _p(m):
        if cb: cb(m)

    base_url = (f"{BASE}map_red_graf.php"
                f"?cod={cod}&estado=REAL&tipo_esta={tipo}&cate={cate}&cod_old=")
    hdrs_extra = {
        "Referer": BASE,
        "Origin":  "https://www.senamhi.gob.pe",
    }

    # Primera visita: obtener cookies + detectar mecanismo AJAX
    _p("Conectando al sitio")
    r0   = sess.get(base_url, headers=hdrs_extra, timeout=20)
    if r0.status_code == 403:
        raise RuntimeError(
            "Cloudflare bloqueó la solicitud.\n"
            "Instala curl_cffi:  pip install curl_cffi"
        )
    soup0 = BeautifulSoup(r0.text, "html.parser")

    if anio is None:
        return soup0

    # Detectar action AJAX del form o del JS
    ajax_url = None
    form = soup0.find("form")
    if form:
        action = form.get("action","")
        if action and action != "#": ajax_url = action

    if not ajax_url:
        ajax_url = _get_ajax_action(r0.text)

    payload = {
        "CBOFiltro":  anio,
        "estaciones": cod,
        "t_e":        tipo,
        "estado":     "REAL",
        "cod_old":    "",
        "cate_esta":  cate,
    }

    hdrs_post = {
        **hdrs_extra,
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": base_url,
    }

    # Estrategias en orden:
    urls_try = []
    if ajax_url:
        full_ajax = ajax_url if ajax_url.startswith("http") else BASE + ajax_url.lstrip("/")
        urls_try.append(("POST", full_ajax))
    urls_try += [
        ("POST", base_url),
        ("GET",  base_url + f"&CBOFiltro={anio}"),
    ]

    for method, url in urls_try:
        try:
            _p(f"Cargando año {anio}…")
            if method == "POST":
                r = sess.post(url, data=payload, headers=hdrs_post, timeout=20)
            else:
                r = sess.get(url, headers=hdrs_extra, timeout=20)

            if r.status_code not in (200, 206): continue
            soup = BeautifulSoup(r.text, "html.parser")
            # Verificar que tenga datos
            tbl = soup.find("table", id="dataTable")
            if tbl and tbl.find_all("tr"):
                return soup
        except Exception:
            continue

    # Último recurso: devolver lo que teníamos
    return soup0


# ─── API pública ──────────────────────────────────────────────────

def obtener_cod_periodos(est: dict, cb=None) -> tuple[dict, list, dict]:
    """
    1. Selenium headless → cod desde marker (mapa sin CF)
    2. curl_cffi → page map_red_graf → CBOFiltro options + metadata

    Retorna (info_est, [(val,lbl),...], metadata_dict)
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    def _p(m):
        if cb: cb(m)

    nombre = est["nombre"]
    dp_key = est["dp_key"]

    # ── Paso 1: cod via Selenium headless ─────────────────────────
    drv      = None
    cod_info = None
    try:
        _p("Buscando código de estación en el mapa")
        drv = _driver()
        drv.get(f"{BASE}?dp={dp_key}")
        WebDriverWait(drv, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR,"img.leaflet-marker-icon[title]"))
        )
        time.sleep(1.2)

        # Intento A: JS source
        src = drv.page_source
        pat = (r'(?i)' + re.escape(nombre.upper()) +
               r'.{0,400}?cod=(\d+)[^"\']*tipo_esta=(\w+)[^"\']*cate=(\w+)')
        m = re.search(pat, src)
        if m:
            cod_info = {"cod":m.group(1),"tipo_api":m.group(2),
                        "cate_api":m.group(3),"estado":"REAL"}

        # Intento B: clic en marker
        if not cod_info:
            cod_info = _cod_desde_click(drv, nombre)

    finally:
        if drv:
            try: drv.quit()
            except: pass

    if not cod_info:
        raise ValueError(f"No se encontró el código de '{nombre}'.")

    info = {**est, **cod_info}

    # ── Paso 2: curl_cffi → años + metadata ───────────────────────
    _p("Obteniendo años disponibles (sin abrir navegador)")
    sess = _sess()
    soup = _fetch_graf(sess, info["cod"], info["tipo_api"], info["cate_api"], cb=_p)

    # CBOFiltro
    sel = soup.find("select", id="CBOFiltro")
    periodos = []
    if sel:
        for opt in sel.find_all("option"):
            v = opt.get("value","").strip()
            l = opt.get_text(strip=True)
            if v: periodos.append((v, l))

    # Metadata de la estación
    meta = _parse_metadata(soup)

    return info, periodos, meta


def obtener_tabla(info: dict, anio: str, cb=None) -> tuple[list, list]:
    """Descarga y parsea la tabla de datos para un año dado."""
    def _p(m):
        if cb: cb(m)
    sess = _sess()
    # warm-up cookie
    try: sess.get(BASE, timeout=8)
    except: pass
    soup = _fetch_graf(sess, info["cod"], info["tipo_api"], info["cate_api"],
                       anio=anio, cb=_p)
    _p("Parseando tabla")
    return _parse_tabla(soup)


def descargar_rango_csv(info: dict, anio_desde: str, anio_hasta: str,
                        meta: dict, cb=None) -> bytes:
    """
    Descarga todos los años en [anio_desde, anio_hasta] y los
    concatena en un solo CSV con BOM UTF-8 (compatible con Excel).
    """
    def _p(m):
        if cb: cb(m)

    sess   = _sess()
    try: sess.get(BASE, timeout=8)
    except: pass

    buf      = io.StringIO()
    writer   = csv.writer(buf)
    wrote_hdr = False

    # Cabecera de metadata
    if meta:
        for k, v in meta.items():
            writer.writerow([k.title(), v])
        writer.writerow([])

    años = list(range(int(anio_desde), int(anio_hasta)+1))
    for i, año in enumerate(años):
        _p(f"Descargando {año} ({i+1}/{len(años)})")
        try:
            soup = _fetch_graf(sess, info["cod"], info["tipo_api"], info["cate_api"],
                               anio=str(año), cb=lambda m: None)
            hdrs, rows = _parse_tabla(soup)
            if not rows:
                continue
            if not wrote_hdr and hdrs:
                writer.writerow(hdrs)
                wrote_hdr = True
            for row in rows:
                writer.writerow(row)
        except Exception as e:
            _p(f"  ⚠ Error en {año}: {e}")
            continue

    return ("\ufeff" + buf.getvalue()).encode("utf-8")
