"""
parser.py — Parseo de HTML: tablas de datos, metadatos de estación,
             períodos disponibles y snapshots JSON del WebEngine.
"""

import re
import json
from bs4 import BeautifulSoup


# ══════════════════════════════════════════════════════════════════
#  Headers
# ══════════════════════════════════════════════════════════════════

def _first_cell_is_data_row(tr):
    cell = tr.find(["td", "th"])
    if not cell:
        return False
    t = cell.get_text(strip=True)
    return bool(
        re.match(r"^\d{4}-\d{2}-\d{2}", t) or
        re.match(r"^\d{1,2}/\d{1,2}/\d{4}", t)
    )


def _parse_headers_grid(hdr_rows):
    """Parsea headers con colspan/rowspan como grid 2D."""
    if not hdr_rows:
        return []
    ncols = max(
        sum(int(c.get("colspan", 1)) for c in tr.find_all(["th", "td"]))
        for tr in hdr_rows
    )
    if ncols == 0:
        return []
    grid = [[None] * ncols for _ in hdr_rows]
    for ri, tr in enumerate(hdr_rows):
        ci = 0
        for cell in tr.find_all(["th", "td"]):
            while ci < ncols and grid[ri][ci] is not None:
                ci += 1
            txt = re.sub(r"\s+", " ", cell.get_text(strip=True))
            rs = int(cell.get("rowspan", 1))
            cs = int(cell.get("colspan", 1))
            for rr in range(ri, min(ri + rs, len(hdr_rows))):
                for cc in range(ci, min(ci + cs, ncols)):
                    grid[rr][cc] = txt
            ci += cs
    headers = []
    for c in range(ncols):
        parts = []
        for r in range(len(grid)):
            cell = grid[r][c]
            if cell and cell not in parts:
                parts.append(cell)
        headers.append(" ".join(parts).strip())
    return headers


def normalize_header(h):
    """
    Normaliza variaciones de nombres de columnas para consistencia:
      "TEMPERATURA (°C)" → "TEMPERATURA_MAX/MIN"
      "HUMEDAD RELATIVA (%)" → "HUMEDAD_RELATIVA"
      etc.
    """
    h_upper = h.upper().strip()

    if "TEMPERATURA" in h_upper:
        if "MAX" in h_upper:
            return "TEMPERATURA_MAX"
        elif "MIN" in h_upper:
            return "TEMPERATURA_MIN"
        return "TEMPERATURA"

    if "HUMEDAD" in h_upper:
        return "HUMEDAD_RELATIVA"

    if "PRECIPITACIÓN" in h_upper or "PRECIPITACION" in h_upper:
        if "TOTAL" in h_upper:
            return "PRECIPITACION_TOTAL"
        return "PRECIPITACION"

    if "AÑO" in h_upper or "MES" in h_upper or "DÍA" in h_upper or "DIA" in h_upper:
        return "FECHA"

    return h_upper


# ══════════════════════════════════════════════════════════════════
#  Tabla principal
# ══════════════════════════════════════════════════════════════════

def parse_tabla(soup):
    """Parsea la tabla HTML con flexibilidad para distintos formatos.

    Returns:
        (headers_normalized, rows)
    """
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

    headers_normalized = [normalize_header(h) for h in headers]

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


# ══════════════════════════════════════════════════════════════════
#  Metadatos de estación
# ══════════════════════════════════════════════════════════════════

def parse_meta(soup):
    """Parsea metadatos de la estación desde la tabla oculta."""
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
            meta["Estacion"] = (
                re.sub(r"\s+", " ", f.get_text())
                .replace("Estacion :", "")
                .strip()
            )

    for tr in trs[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        for i in range(0, len(cells) - 1, 2):
            k = cells[i].replace(":", "").replace("\xa0", "").strip()
            v = cells[i + 1].strip() if i + 1 < len(cells) else ""
            if k and v and len(k) < 40:
                meta[k] = v

    return meta


# ══════════════════════════════════════════════════════════════════
#  Períodos
# ══════════════════════════════════════════════════════════════════

def periodos_desde_soup(soup):
    """Extrae TODOS los períodos disponibles del dropdown."""
    sel = soup.find("select", id="CBOFiltro")
    if not sel:
        return []
    return [
        (opt.get("value", "").strip(), opt.get_text(strip=True))
        for opt in sel.find_all("option")
        if opt.get("value", "").strip()
    ]


# ══════════════════════════════════════════════════════════════════
#  Snapshot JSON (WebEngine)
# ══════════════════════════════════════════════════════════════════

def tabla_desde_snapshot_json(jstr):
    """
    Extrae tabla y períodos del JSON producido por JS_SNAPSHOT.

    Returns:
        (periodos, meta, hdrs, rows, container_divs)
    """
    if not jstr:
        return [], [], [], [], []
    try:
        data = json.loads(jstr)
    except Exception:
        return [], [], [], [], []

    periodos = [(a, b) for a, b in (data.get("periodos") or [])]

    meta = {}
    if data.get("mainHtml"):
        meta = parse_meta(BeautifulSoup(data["mainHtml"], "html.parser"))

    hdrs, rows = [], []
    if data.get("iframeHtml"):
        hdrs, rows = parse_tabla(BeautifulSoup(data["iframeHtml"], "html.parser"))

    return periodos, meta, hdrs, rows, data.get("containerDivs") or []
