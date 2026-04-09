# 🌦️ SENAMHI Scraper

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![PySide6](https://img.shields.io/badge/Framework-PySide6-green.svg)
![Status](https://img.shields.io/badge/Status-Estable-brightgreen.svg)
![Scraping](https://img.shields.io/badge/Engine-Requests%20%2B%20WebEngine-orange.svg)

**SENAMHI Scraper** es una solución avanzada de escritorio para la extracción masiva y saneamiento de datos climáticos del portal oficial de SENAMHI (Perú). Diseñada para investigadores y estudiantes que necesitan series históricas limpias sin errores de servidor.

---

## 🚀 Funcionalidades Estrella

* **🧼 Saneamiento "Clean-HTML":** Motor especializado en eliminar avisos `PHP Deprecated`, `Warning` y `Notice` que corrompen las tablas originales del SENAMHI.
* **⚡ Descarga Híbrida:** * **Modo Rápido:** Usa `Requests` para descargar años de datos en segundos.
  * **Modo Seguro:** Usa `WebEngine` (Navegador Chromium) para resolver **Captchas** cuando el servidor bloquea el acceso.
* **📂 Organización Automática:** Crea carpetas inteligentes por Tipo de Estación y Nombre, evitando el desorden de archivos.
* **📊 Normalización de Variables:** Renombra columnas automáticamente (Temperatura, Humedad, etc.) para que sean listas para usar en Excel o Python.

---

## 🛠️ Guía Maestra de Instalación

Sigue estos pasos para configurar un entorno limpio y evitar errores de librerías.

### 1. Clonar y Preparar
```bash
git clone [https://github.com/tu-usuario/senamhi-scraper.git](https://github.com/tu-usuario/senamhi-scraper.git)
cd senamhi-scraper
2. Configurar Entorno Virtual (VENV)
Es vital para no generar conflictos con otras versiones de Python.

En Windows:

Bash
python -m venv venv
venv\Scripts\activate
En Linux / macOS:

Bash
python3 -m venv venv
source venv/bin/activate
3. Instalación de Dependencias
Con el entorno activado (venv), ejecuta:

Bash
python -m pip install --upgrade pip
pip install requests beautifulsoup4 PySide6 PySide6-WebEngine
🖥️ Manual de Operación
Inicio: Ejecuta python main.py.

Exploración: Selecciona un departamento (ej. Puno o Madre de Dios) y dale a Consultar.

Filtrado: Usa la barra de búsqueda para encontrar tu estación por nombre o código (ej. 47E8336C).

Descarga Individual: Entra a la estación, elige el rango de fechas y dale a Descargar Rango.

Descarga Masiva: Usa la pestaña Masiva para bajar todas las estaciones automáticas de un departamento con un solo clic.

📂 Estructura de Salida (Output)
La aplicación genera una estructura de carpetas profesional:

Plaintext
output/
└── Estacion_Meteorologica_Automatica/
    └── MALINOWSKY/
        ├── senamhi_2024-01.csv  <-- Data limpia
        ├── senamhi_2024-02.csv
        └── ...
Ejemplo de CSV generado:
Fragmento de código
Estacion,MALINOWSKY
Codigo,47E8336C
Departamento,MADRE DE DIOS

FECHA,TEMPERATURA_MAX,TEMPERATURA_MIN,HUMEDAD_RELATIVA
2024-01-01,32.5,22.1,85
2024-01-02,31.8,21.5,88
