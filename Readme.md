# 🌦️ SENAMHI Scraper 

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![PySide6](https://img.shields.io/badge/Framework-PySide6-green.svg)
![Status](https://img.shields.io/badge/Status-Estable-brightgreen.svg)

**SENAMHI Scraper** es una aplicación de escritorio profesional para la extracción, limpieza y gestión de datos climatológicos desde el portal oficial de **SENAMHI (Perú)**.

---

## 🚀 Características Principales

* **🧼 Limpieza Agresiva:** Elimina automáticamente avisos de servidor (`PHP Deprecated`, `Warning`, `Notice`) antes de procesar la data.
* **📊 Parsing Robusto:** Algoritmo avanzado para interpretar tablas HTML y metadatos técnicos.
* **📂 Estructura Automática:** Organiza las descargas por tipo de estación y nombre automáticamente.
* **⚡ Descarga Masiva:** Procesa departamentos enteros filtrando por tecnología de estación.
* **🛠️ Modo Híbrido:** Usa *Requests* para velocidad y *WebEngine* (Navegador) para resolver **Captchas**.

---

## 🧠 Estaciones Soportadas

* **🟢 Meteorológica:** Convencional y Automática.
* **🔵 Hidrológica:** Convencional y Automática.

---

## 🏗️ Estructura del Proyecto

```text
senamhi_scraper/
├── main.py                # Interfaz y lógica principal
├── README.md              # Documentación
└── output/                # Carpeta de descargas
    └── Estacion_Tipo/
        └── Nombre_Estacion/
            └── senamhi_2024-01.csv

⚙️ Requisitos e Instalación
1. Requisitos
Python 3.10 o superior.

2. Instalación de dependencias
Copia y ejecuta esto en tu terminal:

Bash
pip install requests beautifulsoup4 PySide6 PySide6-WebEngine
🖥️ Guía de Uso Rápido
Selección: Elige un departamento y presiona Consultar.

Filtrado: Usa el buscador para encontrar estaciones por nombre o código.

Visualización: Haz clic en una estación para cargar su previsualización.

Descarga: * Usa Descargar Rango para meses específicos.

Usa Descargar TODO para el historial completo.

Usa el panel Masiva para bajar todo un departamento.

📁 Formato de Salida (CSV)
Los archivos se guardan con codificación utf-8-sig para que abran correctamente en Excel:

Fragmento de código
Estacion,MALINOWSKY
Codigo,47E8336C
Departamento,MADRE DE DIOS

FECHA,TEMPERATURA_MAX,TEMPERATURA_MIN,HUMEDAD_RELATIVA
2024-01-01,32.5,22.1,85
2024-01-02,31.8,21.5,88
🧼 Manejo de Errores y Seguridad
El sistema está diseñado para ser resiliente:

Saneamiento: Ignora filas vacías o corruptas.

Reintentos: Si una petición falla, el sistema reintenta automáticamente.

Sesión: Mantiene cookies persistentes para evitar bloqueos por parte del servidor.
