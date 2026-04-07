"""
api.py — Lógica de red y scraping:
  - Drivers HTTP y Selenium
  - Helpers WebEngine (JS síncrono, delay)
  - api_deptos / api_estaciones / api_curl_estacion
  - api_csv_por_mes
"""

import os
import re
import io
import csv
import time

from bs4 import BeautifulSoup

from config import BASE, HEADERS, JS_LEAFLET, JS_SNAPSHOT, js_select_periodo
from parser import (
    parse_meta, parse_tabla,
    periodos_desde_soup, tabla_desde_snapshot_json,
)


# ══════════════════════════════════════════════════════════════════
#  Drivers
# ══════════════════════════════════════════════════════════════════

def _headless():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    o = Options()
    for a in [
        "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-gpu", "--window-size=1280,800", "--log-level=3",
        "--blink-settings=imagesEnabled=false",
    ]:
        o.add_argument(a)
    o.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=o
    )


def _quit(driver):
    try:
        driver.quit()
    except Exception:
        pass


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
#  Helpers WebEngine (síncronos, usan QEventLoop)
# ══════════════════════════════════════════════════════════════════

def run_js_sync(page, script):
    from PySide6.QtCore import QEventLoop
    loop = QEventLoop()
    out = [None]

    def done(res):
        out[0] = res
        loop.quit()

    page.runJavaScript(script, done)
    loop.exec()
    return out[0]


def delay_ms(ms):
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


# ══════════════════════════════════════════════════════════════════
#  API pública — Departamentos
# ══════════════════════════════════════════════════════════════════

def api_deptos():
    """Obtiene el dict {nombre_depto: dp_key} desde SENAMHI."""
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
    except Exception:
        # Fallback estático
        return {
            "Amazonas": "amazonas", "Áncash": "ancash", "Apurímac": "apurimac",
            "Arequipa": "arequipa", "Ayacucho": "ayacucho", "Cajamarca": "cajamarca",
            "Cusco": "cusco", "Huancavelíca": "huancavelica", "Huánuco": "huanuco",
            "Ica": "ica", "Junín": "junin", "La Libertad": "la-libertad",
            "Lambayeque": "lambayeque", "Lima / Callao": "lima", "Loreto": "loreto",
            "Madre de Dios": "madre-de-dios", "Moquegua": "moquegua", "Pasco": "pasco",
            "Piura": "piura", "Puno": "puno", "San Martín": "san-martin",
            "Tacna": "tacna", "Tumbes": "tumbes", "Ucayali": "ucayali",
        }


# ══════════════════════════════════════════════════════════════════
#  API pública — Estaciones por departamento
# ══════════════════════════════════════════════════════════════════

def api_estaciones(dp_key, cb=None):
    """
    Obtiene la lista de estaciones de un departamento usando Selenium
    para leer los marcadores Leaflet.
    """
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
        raw = drv.execute_script(JS_LEAFLET) or []

        sin = [r for r in raw if not r.get("cod")]
        if sin and len(sin) > len(raw) * 0.5:
            p("Abriendo popups para obtener códigos...")
            markers = drv.find_elements(By.CSS_SELECTOR, "img.leaflet-marker-icon[title]")
            for mk in markers:
                try:
                    drv.execute_script("arguments[0].click();", mk)
                    time.sleep(0.04)
                except Exception:
                    pass
            try:
                drv.find_element(By.CSS_SELECTOR, ".leaflet-popup-close-button").click()
            except Exception:
                pass
            time.sleep(0.5)
            raw = drv.execute_script(JS_LEAFLET) or []

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
            ests.append({
                "nombre": nm.title(), "tipo": tp, "subtipo": sub,
                "dp_key": dp_key, "cod": item.get("cod", ""),
                "tipo_api": item.get("tipo_esta", ""), "cate_api": item.get("cate", ""),
            })

        sin2 = [e for e in ests if not e["cod"]]
        if sin2:
            p(f"Buscando {len(sin2)} codigos en el fuente...")
            src = drv.page_source
            for est in sin2:
                pat = (
                    r"(?i)" + re.escape(est["nombre"].upper()) +
                    r".{0,500}?cod=(\d+)[^\"']*tipo_esta=(\w+)[^\"']*cate=(\w+)"
                )
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


# ══════════════════════════════════════════════════════════════════
#  API pública — Datos iniciales de una estación (sin captcha)
# ══════════════════════════════════════════════════════════════════

def api_curl_estacion(info, cb=None):
    """Obtiene datos iniciales sin captcha (curl GET simple)."""
    def p(m):
        if cb:
            cb(m)

    cod = info["cod"]
    tipo = info["tipo_api"]
    cate = info["cate_api"]
    url = (
        f"{BASE}map_red_graf.php"
        f"?cod={cod}&estado=REAL&tipo_esta={tipo}&cate={cate}&cod_old="
    )
    p("Consultando estacion...")
    html = _http_get(url, timeout=25)
    soup = BeautifulSoup(html, "html.parser")
    periodos = periodos_desde_soup(soup)
    meta = parse_meta(soup)
    hdrs, rows = parse_tabla(soup)
    return {
        "url": url,
        "periodos": periodos,
        "meta": meta,
        "hdrs": hdrs,
        "rows": rows,
        "curl_ok": len(rows) > 0,
    }


# ══════════════════════════════════════════════════════════════════
#  API pública — Descarga CSV granular (un archivo por mes)
# ══════════════════════════════════════════════════════════════════

def api_csv_por_mes(page, desde, hasta, nombre_est, meta, periodos_all, carpeta, cb=None):
    """
    Itera cada mes en [desde, hasta] y guarda un CSV independiente.

    Args:
        page:         QWebEnginePage activa (post-captcha).
        desde/hasta:  Códigos de período "YYYY-MM" (extremos inclusivos).
        nombre_est:   Nombre de la estación (para el nombre de archivo).
        meta:         Dict de metadatos (se escribe al inicio de cada CSV).
        periodos_all: Lista completa de (cod, label) de la estación.
        carpeta:      Ruta de destino donde guardar los archivos.
        cb:           Callback opcional para mensajes de progreso.

    Returns:
        Lista de rutas de archivos guardados.
    """
    def p(m):
        if cb:
            cb(m)

    ds, hs = str(desde).strip(), str(hasta).strip()
    en_rango = [(v.strip(), lbl) for v, lbl in periodos_all if ds <= v.strip() <= hs]

    if not en_rango:
        p(f"Sin períodos en rango {ds} a {hs}.")
        return []

    p(f"{len(en_rango)} mes(es) a descargar ({en_rango[0][1]} → {en_rango[-1][1]})")

    base = "senamhi_" + re.sub(r"[^\w.\-]", "_", nombre_est).strip("_")
    guardados = []

    for i, (cod, lbl) in enumerate(en_rango, 1):
        p(f"[{i}/{len(en_rango)}] {lbl} ({cod})…")
        try:
            run_js_sync(page, js_select_periodo(cod))
            delay_ms(1000)
            snap = run_js_sync(page, JS_SNAPSHOT)
            _, _, hdrs, rows, container_divs = tabla_desde_snapshot_json(snap)

            if not rows:
                p(f"  ⚠ Sin datos para {lbl}, se omite.")
                continue

            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")

            # Metadatos al encabezado del CSV
            if meta:
                for k, v in meta.items():
                    w.writerow([k, v])
                w.writerow([])

            if len(container_divs) >= 2:
                w.writerow([container_divs[0], container_divs[1]])
            elif container_divs:
                w.writerow([container_divs[0]])

            if hdrs:
                w.writerow(hdrs)

            nh = len(hdrs)
            for row in rows:
                if nh and len(row) != nh:
                    row = (list(row) + [""] * nh)[:nh]
                w.writerow(row)

            nombre_archivo = f"{base}_{cod}.csv"
            ruta = os.path.join(carpeta, nombre_archivo)
            with open(ruta, "wb") as f:
                f.write(("\ufeff" + buf.getvalue()).encode("utf-8"))

            guardados.append(ruta)
            p(f"  ✓ {len(rows)} registros → {nombre_archivo}")

        except Exception as e:
            p(f"  ⚠ Error en {lbl} ({cod}): {e}")

    return guardados
