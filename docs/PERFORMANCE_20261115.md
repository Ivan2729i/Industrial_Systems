# Fechas, carga por día y rendimiento

## Diagnóstico medido

La implementación anterior descargaba todas las páginas de un intervalo antes de dibujar; su caché estaba ligada al intervalo completo y reconstruía la colección FIRMS al volver a fechas ya cargadas. Armonización transfería miembros, QA y procedencia completos para cada marcador, aunque solo se necesitaban posición e identidad. El cambio de fechas podía dejar una consulta marcada como «en curso» sin reintento: cambiar de pestaña disparaba otra solicitud y parecía reparar la vista.

Mediciones locales iniciales, separando consulta y renderización JSON con CaptureQueriesContext y perf_counter:

| Consulta | Preparación Django antes | SQL incluido | JSON antes | Tamaño JSON antes |
|---|---:|---:|---:|---:|
| Página VIIRS, 5.000 filas, 16–17 abril | 401 ms | 325 ms | 24 ms | 2.062.801 bytes |
| Armonización operativa mundial, mismo intervalo | 1.017 ms | 633 ms | 58 ms | 6.140.133 bytes |

Después, dos muestras con compact=true: VIIRS 159–195 ms de preparación (117–155 ms SQL) y 24–26 ms JSON, 1.000.309 bytes; Armonización 190–394 ms de preparación (169–370 ms SQL), 18–20 ms JSON, 1.673.674 bytes. Son muestras de esta máquina, con caché de páginas PostgreSQL y carga variable; no una garantía de latencia ni un ensayo de carga aislado. Las reducciones de tamaño sin compresión son aproximadamente 52% y 73%. GZip está habilitado para la transferencia HTTP, pero estos tamaños son JSON decodificado, no bytes comprimidos en la red.

Archivos: perf_baseline.json, perf_after.json y perf_explain.txt. EXPLAIN ANALYZE de la selección estrecha por fuente y UTC usó el índice primario existente y ejecutó la página en 3,115 ms. No equivale al tiempo completo del endpoint, que incluye conteos y metadatos. No se añadieron índices ni migraciones.

NASA real: consulta regional nueva del 01/04/2024, bbox 31,-15,31.15,-14.85: MODIS 2.251 ms y VIIRS 1.635 ms, ambos NASA_RECUPERADO. Repetición: CACHE_POSTGRESQL en 6,91 y 5,99 ms. Registro perf_nasa.json. Una respuesta válida sin detecciones no demuestra ausencia de incendios ni cobertura continua del instrumento.

## Implementación

- FIRMS se solicita por días UTC inclusivos en la selección y extremo final exclusivo en SQL. Cada día tiene clave con producto, política de fuente, sensor, fechas del día, bbox, región, satélite y representación. Se conserva la revisión de la importación al construir la colección y se comprueba que no cambie durante la paginación.
- La caché en memoria reutiliza días entre intervalos. SP positivo se conserva seis horas; NRT y días vacíos se revalidan al minuto. Las respuestas fallidas no se guardan como éxitos. Límite de 64 entradas; la representación nativa mantiene hasta 32 colecciones inactivas/activas según disponibilidad y elimina solamente caché visual inactiva, no datos PostgreSQL.
- Para un intervalo regional ya almacenado se intenta primero una consulta compacta conjunta: permite llenar la caché diaria sin quince viajes HTTP. Si no está completo, se continúa por días. Dos trabajadores del cliente cargan los días. Primero leen PostgreSQL; solo un día faltante o caducado activa retrieve=true. Se publica cada día completado inmediatamente, con contador de observaciones, días completos, pendientes y errores. Un fallo conserva los días válidos del intervalo actual. Los resultados se descartan si su AbortSignal quedó cancelado.
- Si un trabajo ya está en curso, se reintenta de forma cancelable y acotada; no hace falta cambiar de pestaña. Dos slots PostgreSQL de descarga limitan la concurrencia NASA entre procesos, y otro advisory lock por consulta evita descargas idénticas simultáneas. Los locks se liberan también en errores.
- SP completado permanece persistido y no se vuelve a descargar. NRT se considera caducado a los 30 minutos. El refresco transaccional mantiene las filas anteriores con is_current=false, reactiva las observaciones presentes en la nueva instantánea y conserva todas las referencias originales. No se borra ningún HDF, CSV ni observación. Una importación fallida revierte la instantánea. SP no admite --refresh.
- El endpoint prefiere SP sobre la revisión NRT del mismo día cuando SP tiene una importación completa del área, evitando contabilizar ambas. Armonización operativa futura utiliza las filas vigentes; no se reejecutó ni modificó el algoritmo Level 2.
- compact=true omite atributos enormes de dibujo. El endpoint original sigue devolviendo todos los campos por defecto. GET /api/v1/detections/<id>/ devuelve la procedencia FIRMS al seleccionar; Armonización conserva su endpoint de detalle con todos los contribuyentes.
- Cesium conserva un Viewer y colecciones por día y revisión. Ampliar un intervalo activa colecciones existentes y añade solo las faltantes. Las construcciones grandes ceden periódicamente al siguiente animation frame, comprobando cancelación antes de publicar. Armonización actualiza entidades por identificador, sin removeAll indiscriminado al cambiar pestañas. La cámara permanece igual.
- Para períodos mundiales de cuatro días o más en modo puntos se usa agregación visual diaria. Se conserva el conteo completo; la tarjeta identifica la agrupación y el área menor permite consultar los originales. No representa ubicación individual exacta ni sacrifica registros del almacenamiento. La densidad reúne los días publicados y agrupa actualizaciones de raster en una ventana de 40 ms, cancelable.

## Pruebas de navegador y tiempos

check-performance.mjs ejecutó diez ciclos MODIS → VIIRS → Armonización → MODIS con un solo Viewer; después dibujó un rectángulo geográfico real dentro de Guerrero y consultó 1, 3, 7 y 15 días de ambos sensores. Los conteos se comparan contra el endpoint real con ese bbox, no contra valores inventados. Los resultados están en frontend/test-results/perf/after-browser.json.

Muestras obtenidas en las ejecuciones locales: volver al día MODIS almacenado 47–170 ms, combinar sus dos días ya cargados 25–62 ms, volver al intervalo VIIRS cargado 36–120 ms. En todos esos casos se transfirieron cero bytes nuevos de detecciones. La primera carga de un día MODIS midió entre 702 y 2.475 ms según la ejecución: no se promete que una carga fría sea inmediata.

Tras añadir la lectura conjunta regional, la ejecución final midió MODIS siete días **198 ms** y quince días **249 ms**, y VIIRS siete días **292 ms** y quince días **221 ms**, con una solicitud para cada intervalo. En ejecuciones anteriores al ajuste conjunto se midieron los siguientes intervalos regionales almacenados, fotograma completo: MODIS siete días 526–928 ms y quince días 770–830 ms; VIIRS siete días 203–477 ms y quince días 473–645 ms en las muestras. Son pruebas regionales; no se afirma haber descargado quince días mundiales completos. Un sondeo anterior a esta optimización midió 1.268 ms para volver a combinar dos días MODIS y 162 ms para el intervalo VIIRS en caché; la comparación es orientativa, no un benchmark aislado con idéntica carga de máquina.

Los resource timings registran tiempo hasta primer byte, transferencia y tamaño decodificado. Las medidas TerraFlare:json-parse, TerraFlare:build y TerraFlare:first-render separan parseo, construcción y evento postRender; la construcción por lotes incluye el tiempo cedido entre fotogramas. El evento postRender no es un temporizador de ejecución física GPU. Los archivos registran las muestras; no se confunden estas etapas con la latencia NASA.

Prueba de fallo parcial: al provocar 503 solo el 05/04 en un intervalo de siete días, quedaron 22 observaciones reales de los demás días visibles, con 6/7 días completos y la fecha fallida explícita. Se comprobó que no hubiera fechas exteriores al intervalo. No se fabricaron detecciones para la prueba.

Prueba de consulta en curso: dos respuestas controladas CONSULTA_EN_CURSO y posterior respuesta real se recuperaron sin cambiar pestaña. Las pruebas de carrera fuerzan demoras y 503; esos errores HTTP son deliberados y no respuestas vacías válidas. La prueba normal de rendimiento terminó sin errores de consola, advertencias ni HTTP fallidos.

94 pruebas Django aprobadas; check correcto y sin migraciones pendientes. TypeScript y pnpm build aprobados. Pruebas Django: contrato compacto/detalle, UTC al inicio y final del día, paginación sin duplicar identificadores, refresco NRT conservando histórico y solo una revisión vigente; además de la suite existente. El piloto V1 de 2.179 observaciones fue verificado campo por campo. El refresco NRT se validó con cliente NASA controlado en la base de pruebas; las consultas reales cronometradas fueron SP.

## Archivos y ejecución

Backend: detections_api.py, firms_service.py, import_firms.py, firms_harmonization.py (selección de snapshot vigente), operational_api.py, urls.py, settings.py (GZip), test_readthrough.py y test_map_performance.py.

Frontend: firmsData.ts, Globe.tsx, data.ts, DetectionCard.tsx; scripts check-performance.mjs, check-partial-period.mjs y check-pending-retry.mjs; adaptación del conteo de primitivas por día en los scripts de fechas/carreras. No se cambió el diseño.

Con PostgreSQL, Django y Vite activos:

```powershell
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py test analysis --keepdb --noinput
corepack pnpm --dir frontend build
Push-Location frontend
node scripts/check-performance.mjs
node scripts/check-partial-period.mjs
node scripts/check-pending-retry.mjs
node scripts/check-phase1-ui.mjs
node scripts/check-phase1-races.mjs
Pop-Location
```

## Límites

La caché cliente se pierde al recargar el navegador; PostgreSQL persiste. Los días no armonizados continúan pendientes y no activan el motor científico al consultar. Las cargas mundiales extensas dependen del volumen y NASA, con máximo 31 días por selección y concurrencia controlada. La escala NRT/QA y la cobertura física no se inventan a partir de respuestas vacías. Se conservan las advertencias conocidas del build sobre Cesium global, dependencias y tamaño de bundle. No se hicieron commits, push ni cambios de rama.
