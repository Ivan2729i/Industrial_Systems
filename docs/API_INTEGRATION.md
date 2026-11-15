# TerraFlare — Contrato de integración de la API

**Versión del documento:** 1.0 (contrato de desarrollo, no versión pública estable)  
**Fecha de referencia:** 14 de noviembre de 2026  
**Backend:** Python 3.13, Django y Django REST Framework (DRF)  
**Cliente previsto:** React + TypeScript + Vite + CesiumJS  
**Ámbito:** piloto espacial en Michoacán, México

> **Alcance y nivel de certeza.** Este documento combina: **[VERIFICADO]** resultados observados en respuestas de la API, pruebas y CSV suministrados; **[IMPLEMENTADO, ESQUEMA PENDIENTE]** rutas existentes cuyo JSON exacto debe inspeccionarse; y **[PROPUESTO]** recomendaciones para la integración. No debe interpretarse como certificación científica de las detecciones o de la metodología.

## 1. Objetivo y límites de responsabilidad

TerraFlare permite explorar coberturas, observaciones por celdas H3, mediciones temporales, comparaciones exploratorias de MODIS y VIIRS y puntos georreferenciados de detecciones provenientes de CSV con formato FIRMS.

- **Equipo científico:** interpreta productos satelitales, máscaras y controles de calidad; produce los archivos de resultados. Debe verificar procedencia, selección de observaciones, criterios y limitaciones de cada producto.
- **Backend:** lee resultados preparados, valida estructura y parámetros, expone API JSON, conserva estados de validación y evita convertir datos ausentes en falsos ceros.
- **Frontend:** consulta las rutas, dibuja las celdas y detecciones, conserva etiquetas de incertidumbre y evita inferencias científicas no respaldadas.

**Terminología:** una *detección* es un registro o píxel clasificado por un producto; **no** representa necesariamente un incendio independiente. Una *celda H3* es una unidad de análisis espacial; su polígono **no** delimita un incendio. *Candidata experimental* **no** significa comparación científicamente validada.

## 2. Entorno local y puesta en marcha

Estructura orientativa del repositorio:

```text
Industrial_Systems/
├── backend/
│   ├── manage.py
│   └── analysis/
│       ├── views.py
│       ├── urls.py
│       ├── firms_detections.py
│       ├── pilot_comparisons.py
│       ├── comparison.py
│       ├── temporal.py
│       └── tests.py
├── src/
│   ├── datos/
│   │   ├── modis.csv
│   │   └── viirs.csv
│   └── resultados_lotes/
│       └── observaciones_pareadas_piloto.csv
└── docs/
    └── API_INTEGRATION.md
```

**Nota:** esta es la estructura funcional usada en desarrollo; verificar los nombres de los demás archivos existentes en Git. Los productos NASA HDF de nivel 2 requeridos por `exportar_detecciones.py` **no estaban disponibles** en la copia local examinada. Los CSV no los sustituyen automáticamente.

Ejecutar el backend desde la raíz del repositorio en PowerShell:

```powershell
# Activar el entorno del proyecto si no está activado.
cd .\backend
python manage.py check
python manage.py test analysis -v 2
python manage.py runserver 127.0.0.1:8000
```

Dejar el proceso `runserver` abierto. En otra terminal:

```powershell
$response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/firms-detections/?date=2024-04-06&limit=100"
$response.summary
$response.data.Count
```

**[VERIFICADO]** En ese conjunto local la consulta devolvió 22 registros: 4 MODIS y 18 VIIRS. Las pruebas de `analysis` finalizaron con `Ran 42 tests ... OK`; no constituyen prueba de validación científica ni de la UI.

**Base URL local:** `http://127.0.0.1:8000`  
**Prefijo común:** `/api/`  
**Formato de respuesta conocido:** `application/json` (DRF permite también interfaz navegable durante desarrollo).  
**Autenticación, permisos, despliegue público y limitación de tasa:** no documentados/configurados en la evidencia disponible; confirmar antes de publicar en Internet.

## 3. Inventario de rutas

| Ruta | Parámetros principales | Uso previsto | Grado de verificación |
|---|---|---|---|
| `GET /api/available-dates/` | ninguno conocido | Fechas con CSV de análisis espacial | Implementada; esquema JSON por confirmar |
| `GET /api/cells/` | `date` obligatorio | Registros originales por celda H3 | Implementada; esquema de cada fila por confirmar |
| `GET /api/statistics/` | `date` obligatorio | Estadísticas del conjunto espacial | Implementada; campos exactos por confirmar |
| `GET /api/geojson/` | `date` obligatorio | `FeatureCollection` de polígonos H3 | Tipo GeoJSON verificado; propiedades por confirmar |
| `GET /api/coverage/` | `date` obligatorio | Cobertura y celdas útiles | Implementada; campos exactos por confirmar |
| `GET /api/temporal/` | `date` obligatorio | Medición temporal por celda H3 | Implementada; campos exactos por confirmar |
| `GET /api/audit/` | `date` obligatorio | Comprobaciones estructurales | Respuesta de ejemplo comprobada |
| `GET /api/comparison/` | `date` obligatorio | Unión espacial-temporal por celda | Resumen y estados comprobados |
| `GET /api/pilot-comparisons/` | `date`, `status`, `modis_overpass`, `viirs_overpass`, `limit`, `offset` | Consolidado por pareja de sobrevuelos y H3 | Conteos y contrato implementado comprobados |
| `GET /api/firms-detections/` | `date`, `sensor`, `satellite`, `limit`, `offset` | Puntos georreferenciados desde CSV | Respuesta y paginación comprobadas |

**Restricción de fechas:** `/api/available-dates/` se basa en archivos de análisis espacial. No presupone que exista cobertura temporal, consolidado piloto o CSV de detecciones para todas esas fechas. La API actualmente no garantiza un catálogo unificado de disponibilidad entre fuentes.

### 3.1 Validación general de fechas

En las vistas descritas, `date` usa `YYYY-MM-DD` (por ejemplo `2024-04-06`). No usar fechas en otro formato ni interpretarlas en hora local. Una fecha válida sin archivo asociado puede producir un resultado vacío o un `404`, según la ruta; esa conducta **debe comprobarse por endpoint**.

## 4. Especificación detallada: detecciones georreferenciadas

### 4.1 `GET /api/firms-detections/`

**[VERIFICADO]** Fuente: `src/datos/modis.csv` y `src/datos/viirs.csv`, con columnas de formato compatible con NASA FIRMS. **Procedencia exacta pendiente de verificar**. El servicio filtra el rectángulo geográfico del piloto, y **no** extrae directamente detecciones de los HDF nivel 2.

**Límites espaciales del filtro actual** (rectángulo de estudio, no límite administrativo de Michoacán):

- Latitud sur: `19.35`; norte: `19.60`.
- Longitud oeste: `-102.15`; este: `-101.80`.
- Los bordes están incluidos.
- Las coordenadas son latitud/longitud geográficas en grados decimales; para Cesium se pasan **longitud primero, latitud después**.

| Query parameter | Tipo | Obligatorio | Valores / semántica | Comportamiento |
|---|---|---|---|---|
| `date` | cadena | No | `YYYY-MM-DD` | Igualdad exacta sobre `acq_date` |
| `sensor` | cadena | No | `MODIS`, `VIIRS` | Se normaliza a mayúsculas; sin filtro consulta ambos CSV |
| `satellite` | cadena | No | valor exacto del CSV, por ejemplo `Aqua`, `Terra`, `SNPP` | Coincidencia de texto, sensible a mayúsculas |
| `limit` | entero | No | `1` a `500` | Predeterminado: `100` |
| `offset` | entero | No | `>= 0` | Predeterminado: `0` |

**Ejemplos:**

```http
GET /api/firms-detections/?date=2024-04-06&limit=100
GET /api/firms-detections/?sensor=VIIRS&date=2024-04-06
GET /api/firms-detections/?sensor=MODIS&satellite=Aqua
GET /api/firms-detections/?limit=10&offset=10
```

**[VERIFICADO] Resumen de la consulta del 6 de abril:**

```json
{
  "source": "FIRMS-format CSV (provenance pending)",
  "scientific_validation": "not_evaluated",
  "region": "Michoacan_pilot",
  "filters": {
    "date": "2024-04-06",
    "sensor": null,
    "satellite": null
  },
  "summary": {
    "total_detections": 22,
    "by_sensor": {"MODIS": 4, "VIIRS": 18}
  },
  "pagination": {
    "limit": 100,
    "offset": 0,
    "total": 22,
    "has_more": false
  }
}
```

Este fragmento muestra **solo los metadatos de la respuesta**: se omite intencionalmente `data`, que en la respuesta completa contiene 22 objetos. Un **objeto de detección real** que sí se observó en la página con `offset=10` es:

```json
{
  "id": "MODIS-60523",
  "sensor": "MODIS",
  "satellite": "Aqua",
  "instrument": "MODIS",
  "latitude": 19.4683,
  "longitude": -101.9762,
  "acq_date": "2024-04-06",
  "acq_time": "2020",
  "observed_at": "2024-04-06T20:20:00Z",
  "confidence": "90",
  "frp": 93.1,
  "brightness": 342.7,
  "daynight": "D",
  "source_file": "modis.csv",
  "source_line": 60523
}
```

| Campo de `data[]` | Tipo | Nota de integración |
|---|---|---|
| `id` | `string` | Identificador local construido con sensor y número de línea; **no** es ID permanente NASA; puede cambiar si se reordena el CSV |
| `sensor` | `"MODIS" \| "VIIRS"` | Familia instrumental; no identifica por sí sola el satélite |
| `satellite` | `string` | Ejemplos observados: `Aqua`, `Terra`, `SNPP` |
| `instrument` | `string` | Valor conservado del CSV original; no asumir taxonomía homogénea entre archivos |
| `latitude`, `longitude` | `number` | Grados decimales; ubicación del registro; no usar el centro H3 como reemplazo |
| `acq_date` | `string` | Fecha de adquisición `YYYY-MM-DD` |
| `acq_time` | `string` | Hora `HHmm`, con ceros iniciales |
| `observed_at` | `string` | Fecha/hora construida de las columnas del CSV, expresada en UTC con `Z`; precisión al minuto |
| `confidence` | `string` | **No convertir directamente a porcentaje para VIIRS**: existen códigos categóricos como `n` |
| `frp` | `number \| null` | Potencia radiativa del fuego; unidad habitual MW para FIRMS, pendiente de confirmación de metadatos de origen |
| `brightness` | `number \| null` | Valor de brillo del CSV; no inferir equivalencia física directa entre productos |
| `daynight` | `string \| null` | Código original `D`/`N` cuando existe |
| `source_file` | `string` | `modis.csv` o `viirs.csv` |
| `source_line` | `number` | Línea de origen en el CSV, para rastreo local |

**Paginación:** `summary` y `pagination.total` se calculan **antes** de cortar la página. `data.length <= limit`. `pagination.has_more` indica si existen más filas. Los datos **no están ordenados cronológicamente**: el lector concatena primero MODIS y después VIIRS, conservando el orden de cada CSV. Si la UI necesita una línea de tiempo, debe ordenar explícitamente por `observed_at` y evitar tomar el orden de las páginas como una cronología global.

**[VERIFICADO] Conteos para los CSV locales actuales:**

| Filtro | Total |
|---|---:|
| Sin filtros | 122 |
| `sensor=MODIS` | 25 (14 Aqua, 11 Terra) |
| `sensor=VIIRS` | 97 (SNPP) |
| `date=2024-04-06` | 22 (4 MODIS, 18 VIIRS) |
| `sensor=MODIS&satellite=Aqua` | 14 |
| `limit=10&offset=10` | 10 elementos en la página; total 122; `has_more=true` |

Estos totales dependen del **contenido actual** de los CSV, no son invariantes científicos ni garantías para archivos futuros.

### 4.2 Errores conocidos de `/api/firms-detections/`

| Caso | HTTP | Respuesta orientativa |
|---|---:|---|
| `sensor` distinto de MODIS/VIIRS | 400 | `{"error":"Sensor invalido. Usa MODIS o VIIRS."}` |
| `date` no válida | 400 | `{"error":"Fecha invalida. Usa YYYY-MM-DD."}` |
| `limit` / `offset` no numéricos o fuera de rango | 400 | `{"error":"Paginacion invalida."}` o `{"error":"Limit u offset fuera de rango."}` |
| CSV de origen inexistente | 404 | `{"error":"No se encontro el CSV de origen."}` |
| CSV con datos que el lector no puede interpretar | 422 | `{"error":"Los datos de origen son invalidos."}` |

Los textos corresponden a la implementación compartida durante el desarrollo; el frontend debe basarse **principalmente en el código HTTP** y no en coincidencias exactas de las frases. No hay un formato de error homogéneo garantizado entre las diez rutas.

## 5. Especificación detallada: comparaciones piloto

### 5.1 `GET /api/pilot-comparisons/`

**[VERIFICADO]** Fuente: `src/resultados_lotes/observaciones_pareadas_piloto.csv`, con **585 filas, 41 columnas**, tres parejas de sobrevuelos y una clave compuesta:

```text
(modis_sobrevuelo, viirs_sobrevuelo, celda_h3)
```

**No usar solamente `celda_h3` como ID de fila de este dataset.** Una misma celda puede aparecer para distintas parejas.

| Query parameter | Tipo | Requerido | Comportamiento |
|---|---|---|---|
| `date` | string `YYYY-MM-DD` | No | Filtra `fecha` |
| `status` | string | No | Filtra `estado_comparacion`, valores debajo |
| `modis_overpass` | string | No | Igualdad exacta sobre `modis_sobrevuelo` |
| `viirs_overpass` | string | No | Igualdad exacta sobre `viirs_sobrevuelo` |
| `limit` | integer | No | 1–500; por defecto 100 |
| `offset` | integer | No | >= 0; por defecto 0 |

Estados permitidos de `status`:

- `candidata_experimental`
- `fuera_de_umbrales`
- `sin_observacion_util_compartida`
- `pendiente_medicion`

**Forma de respuesta del endpoint:**

```json
{
  "methodology_status": "experimental",
  "filters": {
    "date": null,
    "status": null,
    "modis_overpass": null,
    "viirs_overpass": null
  },
  "summary": {
    "total_records": 585,
    "experimental_candidates": 180,
    "validated_records": 0,
    "modis_fire_pixels": 2,
    "viirs_fire_pixels": 18,
    "by_status": {
      "candidata_experimental": 180,
      "fuera_de_umbrales": 187,
      "pendiente_medicion": 3,
      "sin_observacion_util_compartida": 215
    }
  },
  "pagination": {
    "limit": 100,
    "offset": 0,
    "total": 585,
    "has_more": true
  }
}
```

**Importante:** el fragmento omite intencionalmente la propiedad `data`: la respuesta completa sin filtros devuelve hasta 100 **objetos de 41 propiedades**. Los valores de `summary` se derivaron del archivo consolidado suministrado y de la implementación del resumen.

**Una fila real del consolidado**, ilustrativa del estado `candidata_experimental` (selección de campos):

```json
{
  "fecha": "2024-04-06",
  "modis_sobrevuelo": "A2024097.0925",
  "viirs_sobrevuelo": "A2024097.0918",
  "celda_h3": "874985008ffffff",
  "resolucion_h3": 7,
  "modis_pixeles": 2,
  "viirs_pixeles": 17,
  "observacion_util_ambos": true,
  "cobertura_compartida_pct": 99.68,
  "diferencia_min": 4.099,
  "modis_utc": "2024-04-06 09:27:21.115 UTC",
  "viirs_utc": "2024-04-06 09:23:15.190 UTC",
  "comparacion_candidata": true,
  "estado_comparacion": "candidata_experimental",
  "metodologia_validada": false
}
```

**Grupos de campos disponibles (41 columnas del CSV):**

- **Identidad (5):** `fecha`, `modis_sobrevuelo`, `viirs_sobrevuelo`, `celda_h3`, `resolucion_h3`.
- **Conteos y calidad MODIS (6):** `modis_pixeles`, `modis_utiles`, `modis_nubes`, `modis_otros`, `modis_fuego`, `modis_util_pct`.
- **Conteos y calidad VIIRS (9):** `viirs_pixeles`, `viirs_utiles`, `viirs_nubes`, `viirs_reflejo_solar`, `viirs_reflejo_solar_pct`, `viirs_otros`, `viirs_fuego`, `viirs_util_pct`, `observacion_util_ambos`.
- **Indicadores de coincidencia/detección (6):** `fuego_ambos`, `deteccion_solo_modis`, `deteccion_solo_viirs`, `fuego_solo_modis`, `fuego_solo_viirs`, `supera_umbral_exploratorio`.
- **Medición espacial-temporal (4):** `cobertura_compartida_pct`, `diferencia_min`, `modis_utc`, `viirs_utc`.
- **Clasificación y procedencia (6):** `comparacion_candidata`, `estado_comparacion`, `region`, `metodologia_validada`, `viirs_detecta`, `modis_detecta`.
- **Auditoría VIIRS (5):** `qa_originales`, `viirs_bowtie_residual`, `viirs_geo_no_nominal`, `viirs_fuego_sin_bowtie`, `viirs_detecta_sin_bowtie`.

**Valores nulos:** métricas espaciales, temporales y de calidad pueden ser `null` si no hubo medición o auditoría. `null` **no equivale a 0**. Las banderas como `viirs_detecta_sin_bowtie` pueden ser `true`, `false` o `null`.

**Recuento por pareja:**

| Fecha | MODIS | VIIRS | Filas | Candidatas experimentales |
|---|---|---|---:|---:|
| 2024-04-06 | `A2024097.0925` | `A2024097.0918` | 193 | 180 |
| 2024-04-06 | `A2024097.2020` | `A2024097.2030` | 195 | 0 |
| 2024-04-08 | `A2024099.2000` | `A2024099.1954` | 197 | 0 |
| **Total** | | | **585** | **180** |

**Criterios exploratorios del script de consolidación:** cobertura compartida `>= 80 %` y diferencia temporal `<= 5 minutos`, además de observación útil compartida y ambas mediciones disponibles. **No son umbrales validados.** En el CSV, las 585 filas marcan `metodologia_validada=false`.

**Errores del endpoint implementado:** fecha o estado inválido → 400; límites de paginación inválidos → 400; CSV faltante → 404; estructura/datos del CSV inválidos → 422. Confirmar los textos exactos contra el código desplegado.

## 6. Otros endpoints: qué se conoce y qué debe verificarse

Estas rutas existen y tienen pruebas, pero **no se dispone aquí del código final íntegro de sus serializaciones**. Evitar copiar esquemas JSON especulativos al frontend. Para cerrar el contrato hay que capturar una respuesta real por endpoint y confirmar su forma en `backend/analysis/views.py` y los servicios correspondientes.

### 6.1 `GET /api/available-dates/`

- Sin parámetros documentados.
- Basado en los CSV de análisis existentes con fecha en su nombre, **no** en la presencia garantizada de todos los tipos de datos.
- En una versión anterior se observaron fechas como `2024-04-08`, `2024-04-16` y `2024-04-19`; no fijarlas como catálogo permanente.
- **Pendiente:** forma JSON exacta y orden de fechas.

### 6.2 `GET /api/cells/?date=2024-04-19`

- Lee CSV de análisis por celda H3 de la fecha seleccionada.
- **Estructura anteriormente observada:** `{ "date": "...", "total": 195, "data": [ ... ] }` para `2024-04-19`.
- **Pendiente:** documentar cada columna y tipos de las filas en la versión final del backend.

### 6.3 `GET /api/statistics/?date=2024-04-19`

- Resumen descriptivo de celdas y detecciones agregadas del archivo espacial.
- El análisis previo de ese día reportó 169 celdas con observación MODIS, 195 con VIIRS y 169 con observación útil de ambos, pero las cifras solo corresponden a ese procesamiento.
- **Pendiente:** claves JSON exactas y tratamiento de ausencia de cobertura.

### 6.4 `GET /api/geojson/?date=2024-04-19`

- Devuelve `FeatureCollection` GeoJSON; las entidades representan polígonos de celdas H3, **no perímetros de fuego**.
- El orden de coordenadas GeoJSON es **`[longitude, latitude]`**, distinto de muchas funciones científicas que reciben `(lat, lon)`.
- Cesium debe consumir la geometría real; no convertir un centro H3 en detección puntual.
- **Pendiente:** propiedades de cada `Feature` y semántica de filtros.

### 6.5 `GET /api/coverage/?date=2024-04-19`

- Informa cobertura/observación útil de ambos sensores y conteos por celda.
- La comparabilidad temporal anteriormente se exponía como `temporal_comparability: {"status":"not_evaluated"}`; verificar forma vigente.
- **Regla:** cobertura no observada ≠ ausencia de incendio.

### 6.6 `GET /api/temporal/?date=2024-04-19`

- Mediciones de diferencia temporal por H3 del procesamiento científico.
- Un resultado anterior tenía 169 celdas y diferencia cercana a 7.7 minutos; su estado era `measured_not_validated`.
- La medición representaba una aproximación temporal del sobrevuelo por celda, **no necesariamente la hora exacta de cada píxel de fuego**.
- **Pendiente:** confirmar claves de resumen, registros y origen de los tiempos en la versión final.

### 6.7 `GET /api/audit/?date=2024-04-19`

**Ejemplo previamente comprobado (resultado estructural):**

```json
{
  "date": "2024-04-19",
  "spatial_cells": 195,
  "temporal_cells": 169,
  "shared_cells": 169,
  "temporal_cells_missing_in_spatial": 0,
  "spatial_cells_without_temporal": 26,
  "issues_count": 0,
  "issues": [],
  "structural_status": "passed",
  "scientific_validation": "pending"
}
```

`structural_status="passed"` únicamente significa que pasaron los controles estructurales aplicados; **no** certifica precisión, coincidencia científica ni validez metodológica.

### 6.8 `GET /api/comparison/?date=2024-04-19`

- Une datos espaciales y temporales por identificador de celda H3 en el conjunto individual de esa fecha.
- **Resumen anteriormente comprobado:** `total_cells=195`, `cells_with_temporal_data=169`, `cells_without_temporal_data=26`, `cells_with_both_usable=169`.
- Estado global `scientific_validation="pending"`.
- Las filas pueden incluir `has_temporal_data`, `temporal_validation` (`pending` o `not_available`) y `comparable: null`.
- **No equiparar esta ruta con el consolidado**: la clave compuesta por pareja de sobrevuelos se conserva explícitamente en `/api/pilot-comparisons/`.
- **Pendiente:** esquema íntegro de `data[]` en la versión final.

## 7. Integración React / Vite

### 7.1 Proxy de desarrollo (mismo equipo)

Agregar **solo** la propiedad `server.proxy` a la configuración Vite existente. No reemplazar otros plugins o configuraciones del frontend:

```ts
// Dentro de defineConfig({...})
server: {
  proxy: {
    "/api": {
      target: "http://127.0.0.1:8000",
      changeOrigin: true,
    },
  },
},
```

Con Vite y Django en el mismo equipo, usar solicitudes relativas `/api/...`. **Si trabajan en equipos distintos**, `127.0.0.1` en la computadora del frontend apunta a la computadora del frontend, no al backend remoto. Se requiere una dirección de red alcanzable y una configuración de acceso autorizada; no exponer `runserver` públicamente como servidor de producción.

### 7.2 Tipos TypeScript para detecciones

```ts
export type Sensor = "MODIS" | "VIIRS";

export interface FirmsDetection {
  id: string;
  sensor: Sensor;
  satellite: string;
  instrument: string;
  latitude: number;
  longitude: number;
  acq_date: string;
  acq_time: string;
  observed_at: string;
  confidence: string;
  frp: number | null;
  brightness: number | null;
  daynight: string | null;
  source_file: string;
  source_line: number;
}

export interface FirmsResponse {
  source: string;
  scientific_validation: "not_evaluated" | string;
  region: string;
  filters: {
    date: string | null;
    sensor: Sensor | null;
    satellite: string | null;
  };
  summary: {
    total_detections: number;
    by_sensor: Record<Sensor, number>;
  };
  pagination: {
    limit: number;
    offset: number;
    total: number;
    has_more: boolean;
  };
  data: FirmsDetection[];
}
```

### 7.3 Cliente mínimo con comprobación HTTP

```ts
export async function getDetections(date: string): Promise<FirmsResponse> {
  const params = new URLSearchParams({ date, limit: "100", offset: "0" });
  const response = await fetch(`/api/firms-detections/?${params.toString()}`);

  if (!response.ok) {
    throw new Error(`TerraFlare API: HTTP ${response.status}`);
  }

  return (await response.json()) as FirmsResponse;
}

// Prueba conocida en desarrollo:
const result = await getDetections("2024-04-06");
console.log(result.summary); // 22 registros; MODIS 4, VIIRS 18, con el CSV actual
```

Para obtener **todas** las páginas, incrementar `offset` por el número de elementos recibido mientras `has_more` sea `true`. En el conjunto piloto actual bastan 100 para los 22 registros del ejemplo; no extrapolar esta cifra a otros filtros o futuros datasets.

### 7.4 CesiumJS: representación de puntos

```ts
import { Cartesian3, Color } from "cesium";

function addDetections(viewer: any, detections: FirmsDetection[]) {
  for (const detection of detections) {
    viewer.entities.add({
      id: `firms-${detection.id}`,
      position: Cartesian3.fromDegrees(
        detection.longitude,
        detection.latitude,
      ),
      point: {
        pixelSize: 7,
        color: detection.sensor === "MODIS" ? Color.ORANGE : Color.RED,
      },
      properties: {
        sensor: detection.sensor,
        satellite: detection.satellite,
        observedAtUtc: detection.observed_at,
        frp: detection.frp,
        sourceFile: detection.source_file,
        scientificValidation: "not_evaluated",
      },
    });
  }
}
```

Este es un **fragmento orientativo**, no un componente React completo: el visor `viewer` debe existir y debe limpiarse/actualizarse al cambiar filtros. El código colorea por sensor para diferenciar fuentes, **no** por gravedad o confiabilidad. Mostrar un aviso visible sobre el estado de procedencia y validación.

### 7.5 Mensajes esperados en interfaz

- Sin elementos en `data`: **«No hay registros en esta fuente para los filtros seleccionados»**; nunca **«No hubo incendios»**.
- `scientific_validation="not_evaluated"`: **«Detecciones georreferenciadas de CSV con formato FIRMS; correspondencia y validación científica pendientes»**.
- `methodology_status="experimental"`: **«Comparaciones exploratorias; umbrales aún no validados»**.
- `structural_status="passed"` en auditoría: **«Consistencia estructural verificada; validación científica pendiente»**.
- Error HTTP: mostrar estado de fallo y permitir reintentar; no sustituir errores por un arreglo vacío silencioso.

## 8. Matriz de pruebas y aceptación

### 8.1 Comprobaciones de backend ya ejecutadas

```powershell
cd backend
python manage.py check
python manage.py test analysis -v 2
```

**[VERIFICADO]** Resultado comunicado: 42 pruebas, todas `OK`; `System check identified no issues (0 silenced)`.

Se probaron lógica y endpoints de auditoría, fechas, celdas, comparación, cobertura, FIRMS, GeoJSON, consolidado piloto, estadísticas y temporal. La prueba con CSV consolidado real verificó 585 registros, claves no duplicadas, 180 candidatas y metodología no validada. No equivale a cobertura exhaustiva de todos los errores ni a validación de la fuente FIRMS.

### 8.2 Smoke tests manuales recomendados

Desde una terminal con Django en ejecución:

```powershell
$base = "http://127.0.0.1:8000"

# HTTP + JSON + conteos de fecha
$r = Invoke-RestMethod "$base/api/firms-detections/?date=2024-04-06&limit=100"
if ($r.summary.total_detections -ne 22 -or $r.data.Count -ne 22) {
  throw "Resultado inesperado para datos piloto del 6 de abril"
}

# Paginación real
$p = Invoke-RestMethod "$base/api/firms-detections/?limit=10&offset=10"
if ($p.data.Count -ne 10 -or $p.pagination.total -ne 122) {
  throw "Paginacion inesperada"
}

# Consolidado experimental
$c = Invoke-RestMethod "$base/api/pilot-comparisons/?limit=10"
if ($c.summary.total_records -ne 585 -or $c.summary.experimental_candidates -ne 180) {
  throw "Consolidado inesperado"
}
```

Estos son **tests de regresión para los archivos piloto actuales**; actualizar expectativas deliberadamente si los datos cambian y se aprueba la nueva versión del dataset.

### 8.3 Checklist de aceptación frontend

- [ ] Vite consulta `/api/firms-detections/` sin error de red.
- [ ] El selector de fecha envía `YYYY-MM-DD` y el estado muestra **UTC**.
- [ ] Para `2024-04-06` se reciben 22 registros con los CSV actuales.
- [ ] Los puntos usan `[longitude, latitude]` en Cesium y se distinguen por sensor.
- [ ] La UI no confunde Terra con Aqua ni FIRMS con el análisis Level-2.
- [ ] La UI presenta las advertencias de `not_evaluated` y `experimental`.
- [ ] La paginación no oculta datos ni altera las estadísticas del conjunto filtrado.
- [ ] GeoJSON se muestra como celdas de análisis, no perímetros de fuego.
- [ ] Los estados vacío, error y carga se distinguen correctamente.

## 9. Limitaciones científicas y de producto

1. **Procedencia FIRMS pendiente:** antes de publicación formal, registrar URL/exportación, cobertura de fechas, versión, producto y fecha de descarga de `modis.csv` y `viirs.csv`. Los nombres y columnas son compatibles con FIRMS, pero no prueban por sí solos su procedencia exacta.
2. **Cobertura:** sin observación válida no se puede inferir ausencia de fuego. Tampoco comparar conteos crudos como medida de superioridad de sensor.
3. **Diferencia de fuentes:** `modis.csv` contiene detecciones Aqua **y Terra**; el flujo científico comparativo emplea MODIS Aqua frente a VIIRS SNPP. No unir ambos conjuntos fila a fila sin criterios científicos explícitos.
4. **Calidad de VIIRS:** el consolidado tiene métricas para bow-tie residual y geolocalización no nominal para sobrevuelos auditados; no implican que cada punto del CSV FIRMS haya pasado esa auditoría.
5. **Tiempos:** `observed_at` de detecciones está construido a partir de fecha y hora reportadas en CSV, a precisión de minuto; las métricas de `/api/temporal/` se generaron con otro procedimiento. No asumir equivalencia temporal exacta.
6. **Experimental:** el consolidado usa parámetros de investigación (80 % cobertura compartida, 5 min diferencia). `metodologia_validada=false` en todas las filas del piloto.
7. **Rendimiento:** la implementación inicial de FIRMS recorre los CSV de entrada en cada solicitud. Para crecer a otras regiones, se recomienda prefiltrado/almacenamiento indexado o Parquet/DuckDB y pruebas de carga, sin cambiar inadvertidamente el contrato.
8. **Identificadores:** `MODIS-<linea>` y `VIIRS-<linea>` dependen de la fila del CSV; no usarlos como claves permanentes en una base de datos entre versiones de archivo.
9. **Seguridad de operación:** `runserver` y el proxy de Vite son para desarrollo. Antes de exponer TerraFlare públicamente, revisar hosts autorizados, despliegue, CORS según topología, permisos, logs, tamaño de respuestas y políticas de distribución de datos.

## 10. Pendientes antes de considerar estable la API v1

1. **Congelar contratos:** extraer una respuesta JSON real de cada una de las ocho rutas con esquema incompleto y documentar campos, tipos, nulabilidad y códigos de error.
2. **Proveniencia:** confirmar y registrar los metadatos de los CSV FIRMS-format y de los archivos satelitales Level-2.
3. **Pruebas de integración:** ejecutar React/Vite y CesiumJS contra un Django accesible desde la misma red, comprobando filtros, paginación y dibujo de GeoJSON.
4. **Reproducibilidad:** documentar cómo se generan cada CSV y sus dependencias; evitar que rutas de archivos locales se conviertan en dependencias ocultas.
5. **Gestión de versiones:** determinar cómo se versionan dataset, algoritmo, documento y API antes de presentar resultados fuera del entorno piloto.

---

**Contacto técnico:** responsable del backend TerraFlare (completar en el repositorio).  
**Estado de publicación:** documento de integración para desarrollo; validación científica y despliegue de producción pendientes.
