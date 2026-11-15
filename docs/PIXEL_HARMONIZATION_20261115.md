# Producto georreferenciado Level 2 — 15 de noviembre de 2026

Se conserva TerraFlare, la rama ivan-dev, FIRMS y el piloto V1. No se hicieron commits ni push. Esta extensión genera puntos desde los píxeles científicos originales, no desde FIRMS ni desde centros H3.

## Método y procedencia

`src/pixel_harmonization.py` reutiliza los lectores por bloques, clasificación 7/8/9, geometría vecinal dentro del escaneo y límites de `cobertura_espacial.py`, conversión TAI93/UTC de `omparar_tiempos.py` y contexto H3 persistido del motor existente. La geometría común se extrajo como función pura sin cambiar sus criterios. MYD14/MYD03 colección 061 y VNP14IMG/VNP03IMG colección 002 se leen con sus coordenadas originales.

El método `L2_FOOTPRINT_ONE_TO_MANY_EXPLORATORY_V1` exige contexto H3 evaluable A/B, QA VIIRS nominal, geometrías reconstruidas válidas, diferencia de centros de escaneo de hasta 15 minutos e intersección de al menos 50% de la huella VIIRS reconstruida. Cada VIIRS se asigna como máximo a un MODIS: mayor fracción de intersección, menor distancia, identificador estable. Un MODIS puede tener varios VIIRS. Pertenecer al mismo H3 no basta para asociar; se permiten asociaciones entre H3 vecinos cuando satisfacen la geometría.

La representación usa el centro ORIGINAL del MODIS ancla o del píxel exclusivo. Nunca promedia coordenadas. Cada píxel positivo dentro del área aparece exactamente una vez como miembro del producto de esa pareja/versión. La salida distingue ASOCIADA, SOLO_MODIS, SOLO_VIIRS y SIN_COMPARABILIDAD. QA insuficiente, huella inválida o contexto no evaluable se conservan en la última categoría. SOLO no demuestra que el otro sensor no vio fuego: indica ausencia de contraparte aceptada/asignada.

Son asociaciones exploratorias, no eventos confirmados, sensibilidad calibrada ni correspondencia física validada. Las huellas son aproximadas; la incertidumbre geográfica cuantitativa permanece desconocida (`null`). La hora es el centro del escaneo, identificado explícitamente, no una hora individual inventada por píxel. MODIS conserva QA crudo y clasificación original; no se afirma aplicar un filtro MODIS equivalente al QA VIIRS.

## Resultados realmente persistidos

| Área | Fecha UTC | Píxeles originales | Producto unificado | Asociadas / solo M / solo V / sin comparabilidad |
|---|---|---:|---:|---|
| Zambia 31,-15,31.3,-14.7 | 2024-04-16 | 6 (2 M + 4 V) | 4 | 1 / 1 / 2 / 0 |
| Tailandia 101,14,101.2,14.2 | 2024-04-16 | 1 V | 1 | 0 / 0 / 1 / 0 |
| México -100,17,-99.5,17.5 | 2024-04-16 | 24 (14 M + 10 V) | 19 | 4 / 10 / 2 / 3 |
| Australia 131,-15,131.5,-14.5, dos parejas | 2024-04-16 | 0 | 0 | 0 / 0 / 0 / 0 |
| Tabasco–Chiapas -93.55,17.45,-92.95,18.05 | 2024-04-19 | 40 (8 M + 32 V) | 32 | 5 / 3 / 17 / 7 |

Total canónico: **56 resultados, 71 píxeles originales**, 10 asociaciones, 14 exclusivos MODIS, 22 exclusivos VIIRS y 10 sin comparabilidad. La base conserva además el historial: 64 productos versionados y 83 membresías. Reprocesamientos idénticos se deduplican por clave canónica al consultar, también con filtro de versión. Importar el mismo producto es idempotente; agrupaciones incompatibles sobre fuentes compartidas se rechazan atómicamente, no se fusionan arbitrariamente. En los bordes de áreas solapadas puede ser necesario reprocesar un ámbito coherente y declarar una revisión metodológica explícita.

Zambia se ejecutó otra vez por el flujo completo CMR → archivos descargados/caché verificada → H3/tiempo/cobertura/QA → píxeles → PostgreSQL. Manifiesto: `src/resultados_lotes/pixel_validation_zambia/run.json`. Gránulos MYD14/MYD03 A2024107.1210 y VNP14IMG/VNP03IMG A2024107.1206. Conserva nombres reales, conceptos CMR, bytes y SHA256. En esta repetición se reutilizaron archivos reales ya descargados; no se afirma una nueva transferencia de todos los bytes.

Tabasco repitió el mismo flujo con A2024110.0830 / A2024110.0836; manifiesto `src/resultados_lotes/pixel_validation_tabasco/run.json`. Los 40 píxeles se conservan como miembros de 32 resultados. H3 reprodujo 819 observaciones, 718 evaluables y 5 coincidencias QA. El piloto V1 completo sigue intacto: 2.179 filas verificadas campo por campo, Guerrero 775/746/4 y Tabasco 819/718/5. Las coincidencias H3 y las asociaciones de píxeles son productos diferentes.

## Persistencia y API

Migraciones 0004–0006 aplicadas en PostgreSQL. Nuevos modelos justificados por la salida individual: Level2FirePixel (fuente inmutable, fila/columna, coordenadas, UTC, QA, H3 r7), HarmonizedDetection (posición original representativa, pareja, versión, método y evaluación), HarmonizedDetectionMember (relación trazable y unicidad por fuente/pareja/versión). Se reutilizan regiones, sobrevuelos, H3 y trabajos existentes. Los HDF/NetCDF permanecen en archivos, no en campos binarios PostgreSQL.

- GET `/api/v1/harmonization/detections/?start=2024-04-16&end=2024-04-19` — producto paginado, filtros bbox, status, version y máximo 31 días.
- GET `/api/v1/harmonization/detections/<id>/` — miembros originales, QA, gránulos, UTC y evaluación.
- GET `/api/v1/harmonization/detections/catalog/` — fechas, versiones y ámbitos efectivamente procesados; cobertura mundial completa=false.
- GET `/api/v1/harmonization/source-pixels/?date=2024-04-19&sensor=MODIS` — originales individuales.

El frontend sigue páginas de 1.000 hasta 20.000 registros; si se excede, solicita reducir el área, sin truncamiento silencioso. La API aplica filtros espaciales incluyendo bbox que cruza el antimeridiano. El motor científico procesa extensiones regionales ordinarias; para cruzar el antimeridiano hay que dividir la solicitud en ámbitos válidos, no se declara una ejecución científica transmeridiana probada.

Los nuevos trabajos regionales y del planificador mundial generan H3 y puntos automáticamente fuera de HTTP. Los antiguos trabajos H3 pueden ampliarse con `build_pixel_product --run-id ID`. La cola administrativa y sus límites existentes se conservan; no se expone una clave en JavaScript. La cobertura es parcial: no está armonizado todo el planeta y Australia no generó puntos positivos en las dos parejas ensayadas.

## Cesium y comprobaciones

Una instancia Viewer, capas separadas persistentes, respuesta obsoleta cancelada y render explícito. Armonización abre el producto de puntos rojos; H3 queda como análisis secundario. Seleccionar un punto muestra las observaciones que realmente contribuyeron, incluidas las exclusivas. Se conserva World Imagery y se añadió terreno ArcGIS público, atmósfera y luz solar real; caída controlada a elipsoide si el proveedor falla. No se modificó la capa de densidad en esta extensión.

La prueba Chrome/WebGL2 detectó un bloqueo al ajustar miles de puntos individualmente al terreno. Se eliminó ese ajuste masivo: marcadores a altura cartográfica de 150 m, manteniendo latitud/longitud original y profundidad de terreno desactivada. Esa elevación es solo una ayuda visual; no es altitud medida del fuego.

83 pruebas Django aprobadas, check correcto, sin migraciones pendientes, V1 íntegro y TypeScript/pnpm build aprobados. Continúan advertencias de build sobre Cesium global, directivas de dependencias y bundle >500 kB.

Playwright local autorizado por el usuario; Chrome instalado, sin flags de evasión de seguridad. Prueba de navegador: diez ciclos / treinta transiciones entre pestañas, un Viewer, MODIS/VIIRS 5.000 puntos de la vista mundial limitada y 24 armonizados el 16 de abril, cámara conservada; selección real de la asociación de Zambia y comprobación de ambos gránulos; cambio a 32 resultados del 19 y regreso a 24; análisis H3 secundario; móvil 390 px sin desbordamiento horizontal. Sin errores de consola ni HTTP en esa ejecución. Los 5.000 FIRMS son un límite indicado por la interfaz, no el total mundial.

La repetición final también aprobó arrastre rectangular, restauración de la cámara, cambio Densidad → puntos y zoom por rueda. Resultado final: cero errores, cero advertencias de consola y cero HTTP fallidos; terreno ArcGIS y WebGL2 activos. Se revisaron las capturas de Zambia con textura satelital cargada y los puntos rojos reales. La densidad existente conserva intensidad discreta; esta tarea no incorpora una nueva validación cuantitativa de su escala.

Artefactos locales: `frontend/test-results/visual/results.json`, `zambia-associated-real-pixels.png`, `mobile-harmonized.png`, `firms-density.png`. Chrome local fue la alternativa expresamente autorizada tras fallar el navegador integrado. La fuente Inter se conservó como excepción acotada ya registrada para mantener la identidad visual; no se añadió una supresión global.

## Archivos de esta extensión

- Ciencia: `src/pixel_harmonization.py`, `src/cobertura_espacial.py`, `src/run_harmonization.py`.
- Backend: `analysis/models.py`, migraciones 0004–0006, `pixel_product.py`, `pixel_api.py`, `urls.py`, `serializers.py`, `api.py`, comandos `build_pixel_product.py` y `scientific_worker.py`, `test_pixel_product.py` y fixture real Zambia.
- Frontend: `Globe.tsx`, `main.tsx`, `data.ts`, `ScientificJobs.tsx`, `layerVisibility.ts`, `style.css`, scripts de verificación local, package.json/pnpm-lock para Playwright.
- Documentación y artefactos: este informe, manifiestos de Zambia/Tabasco, productos JSON auditables y `.gitignore` para capturas locales. Los archivos NASA grandes siguen excluidos de Git.

## Ejecución PowerShell

Desde la raíz, terminal backend:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt -r backend/requirements-science.txt
.\.venv\Scripts\python.exe backend/manage.py migrate
.\.venv\Scripts\python.exe backend/manage.py runserver
```

Terminal frontend:

```powershell
corepack pnpm --dir frontend install --frozen-lockfile
corepack pnpm --dir frontend dev
```

Terminal de procesamiento autorizado:

```powershell
.\.venv\Scripts\python.exe backend/manage.py scientific_worker --watch --limit 1
```

Variables: PostgreSQL, NASA_FIRMS_MAP_KEY y SCIENTIFIC_ADMIN_KEY en `backend/.env`; credenciales Earthdata en `.env` raíz. No se publicaron ni reescribieron secretos. Para solicitar un área en la web se requiere la clave administrativa, que no es la clave FIRMS.

Verificaciones reproducibles con ambos servicios activos y Chrome instalado:

```powershell
.\.venv\Scripts\python.exe backend/manage.py test analysis --keepdb --noinput
.\.venv\Scripts\python.exe backend/manage.py verify_observations --file src/resultados_lotes/observaciones_h3_armonizadas_v1.csv
corepack pnpm --dir frontend build
Push-Location frontend
node scripts/check-layer-state.mjs
node scripts/check-visual.mjs
Pop-Location
```

Los conteos esperados del script visual corresponden a este conjunto real persistido y deben actualizarse justificadamente cuando se amplíe la cobertura, nunca ajustando los datos científicos para satisfacer el test.
