# TerraFlare — Documentación de API REST

## Descripción

El backend de TerraFlare está desarrollado con Python, Django y Django REST Framework.

Su función es proporcionar al frontend los resultados procesados del análisis satelital MODIS-VIIRS, incluyendo celdas H3, estadísticas y geometrías GeoJSON.

**URL base de desarrollo:** `http://127.0.0.1:8000/api/`

## 1. Consultar celdas H3

**GET** `/api/cells/?date=2024-04-19`

Devuelve los registros procesados correspondientes a la fecha solicitada.

Respuesta:

```json
{
  "date": "2024-04-19",
  "total": 195,
  "data": []
}
```

`data` contiene las celdas H3 y sus métricas originales de MODIS y VIIRS. El arreglo vacío mostrado es únicamente una abreviación del ejemplo.

## 2. Consultar estadísticas

**GET** `/api/statistics/?date=2024-04-19`

Devuelve un resumen de observaciones, cobertura y píxeles clasificados como fuego.

Ejemplo:

```json
{
  "date": "2024-04-19",
  "statistics": {
    "total_cells": 195,
    "modis_observed_cells": 169,
    "viirs_observed_cells": 195,
    "both_observed_cells": 169,
    "modis_fire_pixels": 0,
    "viirs_fire_pixels": 0
  }
}
```

Los campos adicionales de comparación dependerán de la versión implementada del backend.

## 3. Consultar geometrías GeoJSON

**GET** `/api/geojson/?date=2024-04-19`

Devuelve una colección de polígonos geográficos correspondientes a las celdas H3.

Formato de respuesta: `FeatureCollection` de GeoJSON.

Cada elemento contiene:

- `geometry`: polígono de una celda H3.
- `properties`: métricas asociadas a la celda.
- `id`: identificador geográfico H3.

Las coordenadas utilizan el orden `[longitud, latitud]`.

CesiumJS puede consumir este formato utilizando `GeoJsonDataSource`.

## 4. Manejo de errores

Los endpoints contemplan las siguientes respuestas:

- `200 OK`: consulta exitosa.
- `400 Bad Request`: fecha ausente o inválida.
- `404 Not Found`: no existe un CSV para la fecha solicitada.
- `500 Internal Server Error`: error al procesar los datos.

## 5. Consideraciones científicas

- Las celdas H3 representan áreas de análisis, no ubicaciones exactas de incendios.
- No se debe interpretar la ausencia de detecciones como ausencia de incendios sin cobertura válida.
- Los conteos de píxeles MODIS y VIIRS no son directamente comparables debido a sus diferencias de resolución.
- El umbral exploratorio del 80 % de píxeles útiles no debe presentarse como un estándar científico universal.
- Las estadísticas deben provenir de los resultados procesados, no de datos inventados en el frontend.

## 6. Estado de implementación

Los tres endpoints principales han respondido correctamente con datos del 19 de abril de 2024.

La integración con React, las consultas optimizadas y las pruebas completas de validación siguen en desarrollo.