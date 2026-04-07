"""
config.py — Constantes globales, headers HTTP y scripts JS embebidos
"""

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

TIPOS = {"MET": "🟢", "HID": "🔵", "PLU": "🟡"}

# ══════════════════════════════════════════════════════════════════
#  Scripts JS
# ══════════════════════════════════════════════════════════════════

JS_SNAPSHOT = r"""
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

JS_LEAFLET = r"""
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


def js_select_periodo(val):
    """Genera el JS para seleccionar un período en el combo."""
    import json
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
