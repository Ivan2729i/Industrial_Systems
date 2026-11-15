# Verificacion de integracion, 2026-11-14

Implementado read-through en GET /api/v1/detections/ con retrieve=true, region opcional y los parametros existentes start_date/end_date/sensor/bbox. Reutiliza import_firms y sus transacciones, fingerprint y lotes diarios persistidos. SP tiene prioridad; NRT solo se selecciona si su disponibilidad cubre la fecha. VIIRS de esta vista corresponde a S-NPP. Consultas nuevas limitadas a cinco dias y 100 grados cuadrados; world solo permite lectura persistida. Una consulta valida sin puntos conserva el lote completado. Cache corta de errores/disponibilidad y bloqueo local evitan repetir consultas en el proceso Django. El bloqueo local no es un limite global entre multiples workers; esta ejecucion se prepara para runserver local.

Cesium conserva sus capas y seleccion. Los filtros explicitos disparan recuperacion; rotar/zoom no consulta NASA. La region cientifica se puede elegir en ambas vistas, y los lugares seleccionados usan bbox de un grado. Las consultas mundiales requieren seleccionar region para recuperar datos nuevos. No se reinicia la fecha seleccionada al cambiar de vista.

Verificado: instalacion backend en .venv; manage.py check; ocho pruebas sin base (conector, validacion, cache read-through y fallo externo); pnpm install --frozen-lockfile; pnpm build y TypeScript. FIRMS real 2024-04-16 bbox -103,16,-98,19: MODIS_SP 163 (Terra y Aqua), VIIRS_SNPP_SP 372. Una region menor devolvio CSV valido con cero filas. No se almacenaron estas consultas directas porque PostgreSQL rechazo las credenciales configuradas. No se cambio ninguna contraseña ni archivo secreto.

CMR/Earthaccess real: bbox -100.2,17.3,-99.8,17.7, 2024-04-16; MYD14 1, VNP14IMG 3, con productos de geolocalizacion asociados; pareja candidata A2024107.2035 / A2024107.2042 (7 minutos). Manifiesto verification_20261114_cmr.csv. Sin descarga Level 2. El ejecutor src/run_harmonization.py sigue fuera de HTTP, limitado explicitamente a 2024. Su procesamiento completo no ha sido verificado en esta sesion.

CSV V1 comprobado: 2179 filas; Guerrero 16/10/4 y Tabasco-Chiapas 8/32/5. Pendiente comparar con PostgreSQL, migrar, probar deduplicacion y endpoints con base real, renderizado y seleccion en navegador. El servicio PostgreSQL 17 esta Running, pero devuelve fallo de autenticacion.

Comandos desde la raiz tras corregir credenciales en backend/.env:

```powershell
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py showmigrations
.\.venv\Scripts\python.exe backend/manage.py migrate
.\.venv\Scripts\python.exe backend/manage.py import_observations --file src/resultados_lotes/observaciones_h3_armonizadas_v1.csv
.\.venv\Scripts\python.exe backend/manage.py verify_observations --file src/resultados_lotes/observaciones_h3_armonizadas_v1.csv
.\.venv\Scripts\python.exe backend/manage.py test analysis --noinput
.\.venv\Scripts\python.exe backend/manage.py runserver
```

Otra terminal:

```powershell
corepack pnpm --dir frontend dev
```

Variables privadas: NASA_FIRMS_MAP_KEY y POSTGRES_* en backend/.env; Earthdata en .env raiz. package-lock.json preexistente se conserva; pnpm es el gestor utilizado. Sin cambios de modelos ni nuevas migraciones. Sin commit/push.
