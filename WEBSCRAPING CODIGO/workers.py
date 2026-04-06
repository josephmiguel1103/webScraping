"""senamhi/workers.py"""
from PySide6.QtCore import QThread, Signal
from . import api


class WorkerDeptos(QThread):
    resultado = Signal(dict)
    error     = Signal(str)
    def run(self):
        try:    self.resultado.emit(api.obtener_departamentos())
        except Exception as e: self.error.emit(str(e))


class WorkerEstaciones(QThread):
    resultado = Signal(list)
    error     = Signal(str)
    progreso  = Signal(str)
    def __init__(self, dp_key): super().__init__(); self.dp_key=dp_key
    def run(self):
        try:    self.resultado.emit(api.obtener_estaciones(self.dp_key, self.progreso.emit))
        except Exception as e: self.error.emit(str(e))


class WorkerAbrirEstacion(QThread):
    """Cod + períodos + metadata → sin abrir navegador para los datos."""
    listo    = Signal(dict, list, dict)   # info, periodos, meta
    error    = Signal(str)
    progreso = Signal(str)
    def __init__(self, est): super().__init__(); self.est=est
    def run(self):
        try:
            info, periodos, meta = api.obtener_cod_periodos(self.est, self.progreso.emit)
            self.listo.emit(info, periodos, meta)
        except Exception as e: self.error.emit(str(e))


class WorkerTabla(QThread):
    lista    = Signal(list, list)
    error    = Signal(str)
    progreso = Signal(str)
    def __init__(self, info, anio): super().__init__(); self.info=info; self.anio=anio
    def run(self):
        try:
            h,r = api.obtener_tabla(self.info, self.anio, self.progreso.emit)
            self.lista.emit(h, r)
        except Exception as e: self.error.emit(str(e))


class WorkerCSV(QThread):
    listo    = Signal(bytes, str)
    error    = Signal(str)
    progreso = Signal(str)
    def __init__(self, info, desde, hasta, meta):
        super().__init__()
        self.info=info; self.desde=desde; self.hasta=hasta; self.meta=meta
    def run(self):
        import re
        try:
            data   = api.descargar_rango_csv(
                self.info, self.desde, self.hasta, self.meta, self.progreso.emit
            )
            nombre = re.sub(r'[^\w.\-]','_',
                f"SENAMHI_{self.info['nombre']}_{self.desde}-{self.hasta}.csv")
            self.listo.emit(data, nombre)
        except Exception as e: self.error.emit(str(e))
