🌦️ SENAMHI Scraper v4.1

Aplicación de escritorio en Python para consultar y descargar datos meteorológicos e hidrológicos del portal de SENAMHI.

🚀 Características
Limpieza agresiva de errores del servidor (PHP Deprecated, Warning, etc.)
Parsing robusto de tablas HTML
Descarga automática por períodos (mes/año)
Descarga masiva por tipo de estación
Exportación a CSV estructurado
Interfaz gráfica con PySide6
Soporte para captcha (opcional con WebEngine)
🧠 Tipos de estaciones soportadas
🟢 Meteorológica Convencional
🟢 Meteorológica Automática
🔵 Hidrológica Convencional
🔵 Hidrológica Automática
🏗️ Estructura del proyecto
senamhi_scraper/
│
├── main.py
├── README.md
└── output/
    ├── Estacion_Meteorologica_Automatica/
    │   └── Nombre_Estacion/
    │       ├── senamhi_2024-01.csv
    │       ├── senamhi_2024-02.csv
    │       └── ...
⚙️ Requisitos
Python 3.10 o superior
📦 Instalación de dependencias
pip install requests beautifulsoup4 PySide6
(Opcional para captcha)
pip install PySide6-WebEngine
▶️ Ejecución
python main.py
🖥️ Uso
1. Seleccionar departamento
Cargar lista
Elegir uno (ej: Lima, Cusco, etc.)
2. Consultar estaciones
Filtrar por tipo
Buscar por nombre
3. Visualizar datos
Tabla de registros
Información de estación
4. Descargar CSV

Opciones disponibles:

Descargar por rango
Descargar todo
Descarga masiva por tipo
📁 Formato de salida (CSV)

Ejemplo:

Estacion,Nombre
Ubicacion,Lima

FECHA,TEMPERATURA_MAX,TEMPERATURA_MIN,HUMEDAD_RELATIVA
2024-01-01,28,19,85
2024-01-02,27,18,88
🔧 Arquitectura del código
Componente	Función
_http_get / _http_post	Manejo HTTP robusto
_clean()	Limpieza de errores PHP
_parse_tabla()	Parsing de tablas
_parse_meta()	Extracción de metadatos
_fetch_periodo()	Descarga por período
descargar_estacion_completa()	Descarga total
api_estaciones()	Listado por departamento
🧼 Manejo de errores

El sistema:

Elimina errores Deprecated, Warning, Notice
Filtra datos corruptos
Ignora filas vacías
Reintenta solicitudes fallidas automáticamente
🧩 Tecnologías usadas
Python
Requests
BeautifulSoup
PySide6 (Qt)
WebEngine (opcional)
⚠️ Limitaciones
Dependencia del HTML de SENAMHI (puede cambiar)
Algunos datos requieren captcha
Descarga masiva puede tardar