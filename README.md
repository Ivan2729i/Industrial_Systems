# TerraFlare

**Visualización, comparación y armonización de detecciones satelitales de actividad térmica.**

TerraFlare es una plataforma web desarrollada para el **NASA Space Apps Challenge**. Integra observaciones de **MODIS** y **VIIRS**, permite explorarlas en un globo terrestre 3D y presenta resultados de integración y armonización con información sobre su procedencia.


## Objetivo

Facilitar la comparación de sensores con resoluciones, horarios de sobrevuelo y características diferentes, conservando la trazabilidad de los datos y las limitaciones de cada producto.

## Funcionalidades

### Mapa interactivo

- Globo 3D con **CesiumJS**, cartografía y etiquetas geográficas.
- Detecciones individuales de MODIS y VIIRS obtenidas mediante servicios NASA FIRMS.
- Filtros por fechas UTC, sensor y ubicación; selección de áreas geográficas.
- Visualización alternativa de densidad, basada en concentración de detecciones.
- Consulta de atributos y procedencia de observaciones.

### Integración y armonización

TerraFlare distingue explícitamente dos productos:

| Producto | Descripción | Alcance |
| --- | --- | --- |
| **Integración operativa FIRMS** | Reúne detecciones de MODIS y VIIRS y aplica asociaciones exploratorias. | Depende de las fechas, áreas y datos FIRMS disponibles o almacenados. |
| **Armonización científica Level 2** | Procesa observaciones de los productos satelitales originales, con criterios de comparación, tiempo y calidad. | Se limita a las escenas y regiones efectivamente procesadas; no se debe asumir cobertura global. |

Los análisis experimentales pueden utilizar **H3** como estructura de comparación espacial. Las celdas H3 **no** representan perímetros de incendios.

### Analítica

El módulo de Analítica permite consultar datos almacenados en PostgreSQL mediante:

- Filtros de fechas y sensor.
- Conteos de detecciones MODIS y VIIRS y resultados armonizados.
- Gráficas de evolución temporal y comparación.
- Exportación de registros filtrados por fecha y producto a **CSV**.

Los resultados dependen de los datos efectivamente cargados. Un día sin información almacenada no debe confundirse con un día en el que se verificó la ausencia de detecciones.

### Integridad y trazabilidad (fase planificada)

Está prevista una sección para registrar **hashes SHA-256**, historial de procesamientos y verificación de integridad de artefactos exportados. **No se presenta como una blockchain descentralizada ni como una función ya desplegada.**

## Tecnologías

| Capa | Tecnologías |
| --- | --- |
| Frontend | React, TypeScript, Vite, Tailwind CSS, TanStack Query |
| Globo geoespacial | CesiumJS |
| Gráficas | Recharts |
| Backend y API | Python, Django, Django REST Framework |
| Base de datos | PostgreSQL |
| Procesamiento | NumPy, Pandas, H3, herramientas de lectura de productos satelitales |
| Datos | NASA FIRMS, MODIS, VIIRS, NASA Earthdata |

## Estructura general

```text
TerraFlare/
├── frontend/
│   └── src/
│       ├── main.tsx                 # Navegación y página principal
│       ├── Globe.tsx                # Globo CesiumJS
│       ├── Analytics.tsx            # Módulo Analítica
│       └── Analytics.css
├── backend/
│   ├── manage.py
│   └── analysis/                    # Modelos, APIs y servicios
├── src/                             # Scripts científicos y procesamiento
└── README.md
```

La estructura puede contener otros módulos, configuraciones y carpetas de datos.

## Requisitos

- Python y `pip`.
- Node.js y `pnpm`.
- PostgreSQL en ejecución.
- Credenciales o claves NASA necesarias para las operaciones que las requieran.

## Instalación local (Windows / PowerShell)

Clona el repositorio y entra a la carpeta del proyecto:

```powershell
git clone https://github.com/Ivan2729i/Industrial_Systems.git
cd Industrial_Systems
```

Crea y activa un entorno virtual Python:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instala dependencias desde el archivo `requirements.txt` existente en el proyecto:

```powershell
if (Test-Path .\backend\requirements.txt) {
    python -m pip install -r .\backend\requirements.txt
} elseif (Test-Path .\requirements.txt) {
    python -m pip install -r .\requirements.txt
} else {
    Write-Host 'Localiza el archivo de dependencias Python del repositorio.'
}
```

Configura las variables de entorno siguiendo el archivo `.env.example` del repositorio. En particular, verifica la conexión PostgreSQL y, para recuperación de datos FIRMS, `NASA_FIRMS_MAP_KEY`. **Nunca subas claves, contraseñas o archivos `.env` a Git.**

Prepara y ejecuta Django:

```powershell
cd backend
python manage.py migrate
python manage.py check
python manage.py runserver
```

En **otra terminal**, inicia el frontend desde la raíz del repositorio:

```powershell
cd frontend
pnpm install
pnpm dev
```

Abre **http://localhost:5173**. Por defecto, el backend de desarrollo utiliza **http://127.0.0.1:8000**.

> Los comandos de instalación pueden requerir ajustes según la ubicación de `requirements.txt`, el contenido de `.env.example` y la configuración local de PostgreSQL.

## API: ejemplos

Los siguientes endpoints forman parte de la API versionada del proyecto:

```http
GET /api/v1/detections/
GET /api/v1/detections/availability/?sensor=modis
GET /api/v1/harmonized-detections/
GET /api/v1/harmonization/detections/
GET /api/v1/analytics/summary/?start_date=2024-04-16&end_date=2024-04-19
GET /api/v1/analytics/timeline/?start_date=2024-04-16&end_date=2024-04-19
GET /api/v1/analytics/export/?start_date=2024-04-16&end_date=2024-04-19&dataset=modis
```

Las respuestas y la disponibilidad dependen del estado de la base de datos, los trabajos de importación y la configuración del servidor.

## Validaciones básicas

```powershell
# Desde backend/
python manage.py check

# Desde frontend/
pnpm exec tsc --noEmit -p tsconfig.app.json
pnpm build
```

Para evaluar resultados, verifica además la procedencia, cobertura temporal, producto seleccionado y consistencia de los conteos con PostgreSQL.

## Fuentes de datos y referencias

- [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/)
- [NASA Earthdata](https://www.earthdata.nasa.gov/)
- [NASA Space Apps Challenge](https://www.spaceappschallenge.org/)
- [CesiumJS](https://cesium.com/platform/cesiumjs/)

## Proyecto

Repositorio: [Ivan2729i/Industrial_Systems](https://github.com/Ivan2729i/Industrial_Systems)

Proyecto desarrollado para el **NASA Space Apps Challenge**. TerraFlare no es un producto oficial de la NASA.
