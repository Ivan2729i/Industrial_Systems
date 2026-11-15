# Integración operativa mundial FIRMS

Esta extensión responde a la autorización de utilizar una aproximación operativa FIRMS mundial. No reemplaza ni renombra los resultados científicos Level 2. El producto predeterminado de Armonización es ahora **Integración mundial FIRMS**; el selector conserva **Armonización científica Level 2**. El análisis H3 sigue como vista secundaria. Ningún resultado mundial procede del CSV piloto.

## Causa de la limitación anterior

El endpoint y frontend anteriores consultaban exclusivamente el producto de píxeles Level 2 de las pocas áreas efectivamente procesadas. Su alcance parcial era real, no un error de coordenadas en Cesium. Cambiar colores o representar centros H3 no podía crear cobertura mundial. Ahora un servicio independiente consume las colecciones FIRMS mundiales, las integra y persiste una salida propia con trazabilidad.

## Regla operativa V1

`analysis/firms_harmonization.py` reutiliza las detecciones e importaciones FIRMS existentes. Solo acepta importaciones mundiales completadas de ambos sensores. Selecciona SP por sensor y día cuando está guardado; usa NRT cuando SP no está disponible. No mezcla ambas revisiones. Conserva Terra/Aqua y S-NPP en la procedencia.

El índice H3 resolución 5 reduce candidatos; no determina equivalencias. Se exige distancia geodésica <=1.500 m y diferencia temporal <=15 minutos, dentro del mismo día UTC. Cada VIIRS elige como máximo un MODIS por distancia, diferencia temporal e identificador estable. Un MODIS puede anclar varios VIIRS. El centro original MODIS representa la asociación; los exclusivos usan su propia coordenada. No se promedian posiciones ni FRP.

Todas las observaciones se conservan como miembros. Duplicados exactos de sensor/plataforma/hora/coordenadas se consideran una observación, pero mantienen referencias a todas las filas originales. Las fuentes no asociadas quedan como SOLO_MODIS o SOLO_VIIRS; no prueban ausencia de fuego en el otro sensor. H3, proximidad y tiempo son criterios exploratorios, no identificación de incendios confirmados. Este producto no aplica QA Level 2, huellas científicas ni cobertura compartida y no sustituye ese procesamiento.

Se implementa como trabajo diario transaccional y reanudable, con bloqueo PostgreSQL para un worker local. Errores e importaciones incompletas nunca se convierten en éxito vacío. GET no ejecuta procesamiento pesado. La cola POST requiere X-Scientific-Key, admite como máximo ocho trabajos pendientes y usa el mismo secreto administrativo existente; no expone NASA_FIRMS_MAP_KEY.

## Datos verificados

| Fecha UTC | MODIS | VIIRS S-NPP | Unificadas | Asociadas | Solo MODIS | Solo VIIRS |
|---|---:|---:|---:|---:|---:|---:|
| 2024-04-16 | 7.411 | 45.487 | 47.164 | 2.157 | 5.254 | 39.753 |
| 2024-04-17 | 8.562 | 44.705 | 53.197 | 29 | 8.533 | 44.635 |

El 16 reutilizó importaciones NASA mundiales ya persistidas. El 17 ejecutó `--retrieve`, recuperó datos con el servicio NASA real y generó el producto. La repetición de ambos días reutilizó los resultados sin duplicarlos. La diferencia de asociaciones entre días se conserva; no se fuerza una tasa de coincidencia esperada.

Consultas bbox del 16: África -20,-35,55,38 =15.037; Asia 65,0,145,55 =16.082; Oceanía 110,-45,155,-10 =4.610; América -125,-55,-35,50 =9.740; Europa -15,35,45,70 =825. Son rectángulos de prueba, no polígonos administrativos ni particiones continentales exclusivas.

La consulta mundial agrupa todas las 47.164 unidades en 3.101 puntos representativos. La suma de `represented_count` coincide con el total. Cada posición pertenece a una detección real representativa de la agrupación. Al solicitar un bbox se recuperan unidades individuales paginadas. No se interpreta cada marcador global agrupado como una sola detección ni se inventan coordenadas.

## Modelos y endpoints

Migración 0007: FIRMSHarmonizationJob, FIRMSUnifiedDetection y su relación de miembros con FireDetection. Reutiliza SatelliteSource, DetectionImport y FireDetection; no crea tablas crudas MODIS/VIIRS duplicadas. Índice de ubicación y fecha UTC, clave diaria de versión y coordenadas originales persistidas.

- GET `/api/v1/harmonized-detections/?start=2024-04-16&end=2024-04-16&aggregate=true`
- GET `/api/v1/harmonized-detections/?start=2024-04-16&end=2024-04-16&bbox=20,-20,35,-10&limit=1000&offset=0`
- GET `/api/v1/harmonized-detections/<id>/`
- GET/POST `/api/v1/harmonized-detections/jobs/`

Filtros: start/end hasta 31 días, bbox incluido antimeridiano, status, limit y offset. País/estado/ciudad se resuelven con los controles geográficos existentes y se envía su bbox real; los nombres por sí solos no se interpretan como fronteras y sin bbox devuelven validación clara. No se asignan nombres administrativos inventados a cada registro ni se afirma selección exacta por polígonos. La resolución en línea depende del geocodificador; cuando falla, queda disponible seleccionar el área en el globo.

El frontend agrega la consulta mundial con un máximo de 5.000 grupos, ajustando el tamaño espacial sin truncar el total. Para áreas individuales sigue páginas hasta 20.000 registros y solicita reducir el área cuando se excede. Los resultados completados se cachean en el cliente y no se consultan en cada movimiento de cámara. La vista incluye conteos totales y estados pendientes por fecha.

## Globo y UX

La prueba visual aisló el agujero polar: al retirar el terreno ArcGIS desaparecía el círculo negro, pero la cartografía Mercator aún dejaba una unión circular. La vista mundial utiliza ahora NASA GIBS Blue Marble mediante WMS EPSG:4326, verificado contra el servicio real y con cobertura polar. NaturalEarthII queda debajo como respaldo local. World Imagery y terreno ArcGIS se activan para vistas regionales a menos de 3.000 km de altura y entre 75° S/N; el mundo y los polos usan superficie elipsoidal continua. El cambio de detalle es local a Cesium y no consulta detecciones NASA. Se retiraron el oscurecimiento solar agresivo, el fondo estrellado excesivo y la Luna decorativa, con luz diurna cartográfica constante y atmósfera suave. No se afirma estar mostrando una simulación día/noche en tiempo real ni imágenes de la Tierra adquiridas en la fecha seleccionada para incendios: Blue Marble es una base compuesta.

La densidad dejó de ser un rectángulo geométrico mundial pegado al terreno: ahora es un overlay raster SingleTileImageryProvider, oculto y restaurado por sensor/modo. Esto evita depender de una malla mundial en los polos. Los marcadores son rojos, mantienen latitud/longitud y la elevación exclusivamente cartográfica previa de 150 m, con profundidad de terreno desactivada para evitar desapariciones.

Se conserva un Viewer y capas persistentes; cancelar peticiones impide respuestas antiguas. Cambiar país/estado/ciudad limpia el rectángulo previo; Vista mundial limpia los filtros geográficos; Buscar en esta área funciona también en Armonización. La edición manual de fecha impide que la inicialización asíncrona la sobrescriba. Se corrigió el texto Cargar más localidades. No se reintrodujeron Región científica, Fecha disponible ni Automático.

## Verificación

90 pruebas Django aprobadas, check correcto, migración 0007 aplicada y makemigrations --check sin cambios. Verificación campo por campo del piloto V1: 2.179 observaciones intactas. Pruebas nuevas: conservación, idempotencia, uno-a-varios controlado, límite temporal/espacial, antimeridiano y polos, duplicados exactos, importación parcial, cero válido, paginación, agregación, filtros y autorización de cola.

Verificación final PostgreSQL: dos trabajos completados, 100.361 unidades operativas persistidas y 106.165 referencias a observaciones fuente. TypeScript y pnpm build aprobados; permanecen las advertencias conocidas del script Cesium global, directivas de dependencias y tamaño del bundle. No hubo errores ni advertencias en la consola del navegador durante la ejecución final.

La validación Chrome/WebGL2 local autorizada con `frontend/scripts/check-operational.mjs` aprobó diez ciclos / treinta transiciones entre MODIS, VIIRS y Armonización con un único Viewer y cámara conservada; 3.101 grupos mundiales que representan 47.164 unidades; selección real de una detección de África; consulta del viewport, retorno mundial, cambio de fecha 16/17, cambio de producto operativo/Level 2, densidad raster y regreso a puntos, vista polar y móvil de 390 px sin desbordamiento. Cero errores, advertencias o HTTP fallidos. Se inspeccionaron las capturas, no solo los conteos internos, y se corrigió el agujero polar antes de concluir.

`check-geography.mjs` comprobó México → Guerrero → Acapulco en el navegador con geocodificación real: cámara 16,85°, -99,91°, altura cartográfica 105.000 m; Vista mundial limpió los campos y deshabilitó estado/ciudad. Sin errores, advertencias ni HTTP fallidos. El catálogo desplegado de país contiene 249 opciones. Las localidades con coordenadas y sin bbox propio usan una ventana de consulta ±0,5° alrededor del punto, sin confundirla con un límite municipal. Resultados y capturas en `frontend/test-results/operational/`.

## Comandos PowerShell

Desde `C:\Users\ivanp\PycharmProjects\Nasa`:

```powershell
.\.venv\Scripts\python.exe backend/manage.py migrate
.\.venv\Scripts\python.exe backend/manage.py harmonize_firms --start 2024-04-16 --end 2024-04-17 --retrieve
```

Terminales separadas:

```powershell
.\.venv\Scripts\python.exe backend/manage.py runserver
```

```powershell
corepack pnpm --dir frontend dev
```

Worker para solicitudes mundiales hechas desde la web:

```powershell
.\.venv\Scripts\python.exe backend/manage.py harmonize_firms --watch --limit 3
```

Pruebas reproducibles, con Django y Vite iniciados para las de navegador:

```powershell
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py test analysis --keepdb --noinput
corepack pnpm --dir frontend build
Push-Location frontend
node scripts/check-operational.mjs
node scripts/check-geography.mjs
Pop-Location
```

El worker científico Level 2 sigue independiente:

```powershell
.\.venv\Scripts\python.exe backend/manage.py scientific_worker --watch --limit 1
```

Variables existentes: POSTGRES_* y NASA_FIRMS_MAP_KEY en backend/.env; SCIENTIFIC_ADMIN_KEY para solicitar trabajos; credenciales Earthdata en .env raíz para Level 2. No se reescribieron secretos.

## Límites reales

Solo las fechas sincronizadas tienen producto mundial almacenado; las demás se indican pendientes. Consulta mundial NASA completada no garantiza cobertura satelital completa. La V1 operativa no asocia a través de medianoche UTC, no calibra sensibilidades y puede producir falsos emparejamientos o no emparejar observaciones del mismo fenómeno. Debe validarse antes de interpretar asociaciones como eventos. Los snapshots diarios completados son estables; aún no hay política automática de sustitución de NRT por SP ni actualización incremental de un día NRT en curso. La cobertura Level 2 sigue parcial, disponible como producto distinto.

Archivos de esta extensión: models.py y migración 0007; firms_harmonization.py; operational_api.py; comando harmonize_firms.py; test_operational.py; urls.py; main.tsx, Globe.tsx, data.ts, ScientificJobs.tsx y LocationSearch.tsx; check-operational.mjs; este informe. No se hicieron commit, push ni cambios de rama.
