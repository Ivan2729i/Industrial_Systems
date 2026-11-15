# Fase 1 — fechas, Cesium y presentación de detecciones

## Causas comprobadas y correcciones

- FIRMS solo consumía la primera página (5.000 filas), aunque el backend informaba totales mucho mayores. Ahora `firmsData.ts` sigue `next_offset`, valida conteo e identidad y cancela toda la secuencia al cambiar filtros. Máximo operativo: 200.000 puntos; superar el límite solicita reducir el área o utilizar densidad, nunca trunca silenciosamente.
- Las capas se ocultaban antes de terminar y Armonización recibía un arreglo vacío durante la carga, que destruía la colección anterior. Ahora se conserva el snapshot en memoria; mientras se actualiza, se oculta su visualización para no atribuir datos antiguos a fechas nuevas. Solo se sustituye cuando llega una respuesta válida del filtro actual. Un error conserva los datos almacenados y no se interpreta como cero.
- El estado de visibilidad y el contenido se distinguieron mediante claves de consulta, cancelación, snapshots por sensor y estado ready del producto armonizado. No se recrea Viewer ni se cambia la cámara al editar fechas. La caché recupera fechas consultadas y no guarda respuestas fallidas.
- El endpoint aceptaba un rango parcialmente importado como consulta vacía o completa. Ahora informa missing_dates y DATOS_PARCIALES/DATOS_NO_IMPORTADOS. Un rango mundial de más de tres días ya almacenado se puede consultar; la descarga de fechas nuevas sigue acotada y presenta una validación explícita.
- Para representar las colecciones completas se utilizan PointPrimitiveCollection de Cesium para FIRMS, en vez de decenas de miles de entidades o componentes React. El producto armonizado conserva su capa independiente y trazabilidad.

El motor científico no se modificó. Al descartar la línea de optimización se retiraron su servicio progresivo y sus cambios de serialización, caché y refresco NRT. Se conserva el campo aditivo is_current y la migración 0008, que ya habían sido aplicados: la fase 1 no utiliza ese campo para filtrar ni alterar observaciones. No se eliminó la columna ni sus datos. Se conserva PostgreSQL y el piloto V1 íntegro.

## Globo y densidad

Se mantiene NASA GIBS Blue Marble global, World Imagery regional, terreno regional y superficie elipsoidal en los polos. El canvas respeta DPR hasta 2, con MSAA y refinamiento de mosaicos más estricto; GIBS utiliza tiles de 512 px. La imagen de detalle se activa antes al acercarse (menos de 6.000 km, fuera de latitudes polares). No se añade oscurecimiento solar agresivo. La capa real World Boundaries and Places está disponible también a escala mundial, con topónimos según zoom.

La densidad anterior era poco perceptible por su alfa cuadrática baja, su raster mundial fijo y la posibilidad de quedar bajo imagery añadido asincrónicamente. Ahora la imagen se ajusta al bbox consultado y cruces del antimeridiano; se normaliza logarítmicamente respecto del percentil 98 de intensidades positivas, con un kernel suave compacto, gradiente rojo/naranja/amarillo y alfa visible. El suavizado se aplica a conteos reales, sin efectos de brillo aditivos. La capa se mantiene sobre la imagen y bajo las etiquetas.

Representa concentración relativa de conteos satelitales suavizados, no temperatura, superficie quemada ni propagación. El radio depende de la resolución y extensión de la consulta; al cambiar el área se recalcula. Mover la cámara no descarga datos FIRMS.

## Tarjetas y navegación

`DetectionCard.tsx` se reutiliza en MODIS, VIIRS y Armonización. Muestra sensor, fecha, UTC, coordenadas, confianza interpretada por producto, FRP en MW y fuente. MODIS numérico conserva su escala porcentual; VIIRS l/n/h se presenta como baja/nominal/alta en su propia escala. Los valores ausentes no se inventan. En productos armonizados se identifica que FRP/confianza pertenecen a la observación representativa, no a una suma o calibración conjunta. Todos los campos y contribuyentes originales permanecen en Ver detalles técnicos. Cierre con botón o Escape; expansión nativa accesible por teclado.

Se eliminó completamente la franja solicitada de Armonización, sin texto sustituto en su lugar. El menú tiene Pantalla principal, Analítica y Blockchain; las últimas dos están deshabilitadas y marcadas Fase 2/Fase 3, sin páginas vacías ni funcionalidades simuladas.

## Verificaciones reales

- Django check correcto; sin migraciones pendientes de generación; 90 pruebas aprobadas. Incluye consultas semanales ya almacenadas sin llamar NASA y ausencia de cobertura de un día que no se interpreta como cero.
- V1: 2.179 observaciones verificadas campo por campo en PostgreSQL; Guerrero 775/746 evaluables/4 ambos QA y Tabasco–Chiapas 819/718/5.
- TypeScript y pnpm build aprobados; advertencias conocidas de Cesium global/dependencias y bundle >500 kB permanecen.
- Chrome local headless/WebGL: cambios consecutivos y rápidos en cada sensor, regreso a fecha previa, intervalos, cámara conservada y único Viewer. MODIS 16/04 =7.411, 17/04 =8.562, intervalo =15.973; VIIRS =45.487, 44.705 e intervalo =90.192. Armonización operativa conserva 47.164/53.197 unidades diarias y 100.361 para ambos días, con representación mundial agrupada.
- Respuestas reales retrasadas deliberadamente: volver de fecha y cambiar pestaña durante una solicitud no deja que la respuesta antigua reemplace la nueva. Incluye Armonización. Inyección controlada de HTTP 503: conserva la colección anterior en memoria, informa error y recupera la fecha previa. Los errores 503 de consola en esa prueba son los provocados, no fallos inesperados.
- Prueba UI: selección real de MODIS, VIIRS y Armonizado; fecha/UTC/fuente, FRP, detalles expandibles, cierre por Escape; densidad y cambios de fecha/sensor, regreso a puntos, menú y móvil sin desbordamiento. Raster de densidad real: 28.053 píxeles con alfa >100 en la captura comprobada. Sin errores, advertencias o HTTP fallidos en esta ejecución normal.
- Chrome móvil emulado: selección táctil de un punto, tarjeta abierta, canvas de 714 px para 357 CSS px (DPR 2); sin errores o desbordamiento. No equivale a una prueba en dispositivo físico ni prueba multitáctil de pinza.
- Geografía: México → Guerrero → Acapulco mantiene cámara en 16,85°, -99,91° y limpia dependencias al volver al mundo; sin errores.

Capturas locales: `frontend/test-results/phase1/`: world-labels.png, world-density.png, viirs-density.png, modis-card.png, viirs-card.png, harmonized-card.png, mobile.png y touch-card.png. Fueron inspeccionadas; la nitidez de cada mosaico depende también de la cobertura y carga del proveedor, no se afirma resolución ilimitada.

## Archivos

Backend: `analysis/detections_api.py`, `analysis/test_readthrough.py`.

Frontend: `Globe.tsx`, `main.tsx`, `density.ts`, `style.css`, nuevos `firmsData.ts` y `DetectionCard.tsx`.

Validación: `scripts/check-phase1-dates.mjs`, `check-phase1-races.mjs`, `check-phase1-ui.mjs`, `check-phase1-touch.mjs`; se reutiliza check-geography.mjs. Los scripts antiguos que esperaban solo 5.000 entidades FIRMS no son la prueba de esta versión: la capa usa primitivas y paginación completa.

## Reproducir

Con PostgreSQL y variables existentes configuradas, desde la raíz, terminales separadas:

```powershell
.\.venv\Scripts\python.exe backend/manage.py runserver
```

```powershell
corepack pnpm --dir frontend dev
```

```powershell
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py test analysis --keepdb --noinput
corepack pnpm --dir frontend build
Push-Location frontend
node scripts/check-phase1-dates.mjs
node scripts/check-phase1-races.mjs
node scripts/check-phase1-ui.mjs
node scripts/check-phase1-touch.mjs
node scripts/check-geography.mjs
Pop-Location
```

Las pruebas usan las importaciones reales persistidas del 16 y 17 de abril de 2024. El test de errores introduce únicamente fallos/demoras HTTP controlados, nunca detecciones inventadas. Las fechas armonizadas no procesadas siguen pendientes; esta fase no genera datos científicos para completarlas. Analítica y Blockchain se reservan para las siguientes fases. No se hicieron commit, push, merge ni cambios de rama.
