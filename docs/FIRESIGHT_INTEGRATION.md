# FireSight: integracion local y validacion

## Estado de esta entrega

Se trabajo en `C:\Users\jesus\Downloads\Industrial_Systems`, rama `main`, inicialmente limpia. No se realizaron commits, push ni cambios de rama. La ruta original de Ivan no existe en este equipo.

La implementacion activa usa `frontend/src/main.tsx`, `Globe.tsx`, `data.ts` y `style.css`; `App.tsx` era una pantalla de reserva sin usar. Se conservaron navegacion, estilos, busqueda geografica, Vite, Tailwind 4 y Cesium 1.132. El backend tenia servicios de analisis que leen CSV y ningun modelo cientifico; se conservaron como endpoints heredados. La interfaz principal ahora consume exclusivamente `/api/v1/observations/` en PostgreSQL. Los CSV y GeoJSON siguen siendo fuentes y artefactos cientificos, no respuestas de la nueva API.

## Modelo y politica de versiones

- `Region`: identificador estable, nombre, bounding box WGS84 nullable. Las regiones conocidas reutilizan `src/regiones.py`; nuevas regiones se crean desde el CSV con bbox desconocido, sin inventarlo.
- `OverpassPair`: region protegida por FK, fecha indexada, identificadores MODIS y VIIRS, plataformas opcionales desconocidas. Unicidad por region, fecha y ambos sobrevuelos.
- `H3Observation`: pareja protegida por FK, celda y resolucion H3, todos los conteos, booleanos, QA, tiempos UTC por celda, areas, cobertura, clasificaciones, metodo, version y procedencia del CSV real. FK protegida a la importacion original. Indices en pareja, celda H3 y clasificacion original; indice de fecha en la pareja e indice de region mediante su FK.
- `DataImport`: nombre de archivo sin ruta privada, SHA-256, version, fecha con zona horaria, procesados, insertados, sin cambios, estado y tipo de error.

Unicidad de observacion: `(pair, celda_h3, version_armonizacion)`. La version forma parte de la identidad para conservar revisiones historicas. Reimportar los mismos valores no modifica registros. Cambiar valores dentro de una misma version produce error y rollback de toda la importacion. Para revisar resultados, el proceso cientifico debe producir una nueva `version_armonizacion`; ambas versiones quedan almacenadas. La API usa `v1_experimental` por defecto; `?version=...` selecciona otra expresamente. Nuevas fechas y regiones con el mismo esquema no requieren modelos adicionales.

Los campos desconocidos se guardan como NULL. En V1 hay 266 diferencias temporales nulas, 197 coberturas compartidas nulas y 585 valores QA nominales nulos. Las plataformas de los granulos no se deducen de identificadores incompletos. Los tiempos por celda no se trasladan a una pareja como si fueran iguales.

El comando `db_status` comprueba PostgreSQL y reporta disponibilidad e instalacion de PostGIS. Los poligonos se calculan con H3 y no requieren extension espacial ni GDAL. No se almacenan HDF, NetCDF ni matrices en PostgreSQL. El filtro bbox usa la interseccion H3 experimental y rechaza extensiones excesivas; no admite cajas que crucen el antimeridiano.

## Preparacion PostgreSQL

PostgreSQL 16 fue encontrado como servicio `postgresql-x64-16` activo. Es necesario configurar `backend/.env` localmente; nunca copiar las credenciales NASA del `.env` raiz.

Si faltan usuario y base, abrir psql como administrador PostgreSQL y ejecutar **solo para recursos inexistentes**:

```powershell
psql -h localhost -U postgres -d postgres
```

```sql
CREATE ROLE firesight_app LOGIN;
\password firesight_app
CREATE DATABASE firesight_db OWNER firesight_app;
```

`\password` solicita la clave de manera interactiva. No guardar contrasenas en SQL versionado. Si el rol ya existe, conservar sus credenciales. Para ejecutar tests, un administrador puede conceder temporalmente `ALTER ROLE firesight_app CREATEDB;` y revocarlo al terminar con `ALTER ROLE firesight_app NOCREATEDB;`. Los tests usan una base `test_firesight_db` separada y Django la elimina al finalizar; no otorgar privilegios de superusuario.

En `backend/.env`, configurar las claves descritas en `backend/.env.example`: `DJANGO_SECRET_KEY`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`. No hay fallback SQLite. El archivo se carga solamente desde backend. CORS permite los origenes Vite indicados en el ejemplo.

## Instalacion y base de datos

Desde la raiz del repositorio en PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe backend/manage.py db_status
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend/manage.py migrate
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py import_observations --file src/resultados_lotes/observaciones_h3_armonizadas_v1.csv
.\.venv\Scripts\python.exe backend/manage.py import_observations --file src/resultados_lotes/observaciones_h3_armonizadas_v1.csv
.\.venv\Scripts\python.exe backend/manage.py verify_observations --file src/resultados_lotes/observaciones_h3_armonizadas_v1.csv
.\.venv\Scripts\python.exe backend/manage.py db_status
```

Primera importacion esperada: 2179 insertados. Segunda: 0 insertados y 2179 sin cambios. Las importaciones administrativas no tienen endpoints publicos. Una importacion fallida revierte datos relacionados y observaciones, pero conserva el registro de fallo.

## API publica de solo lectura

- `GET /api/health/`: comprueba conexion; 503 si PostgreSQL no responde.
- `GET /api/v1/regions/`: regiones persistidas y bounding boxes.
- `GET /api/v1/dates/?region=guerrero`: fechas persistidas.
- `GET /api/v1/observations/`: lista paginada.
- `GET /api/v1/observations/{id}/`: detalle con pareja identificada.
- `GET /api/v1/summary/`: sumas originales y QA separadas, categorias y parejas identificadas.
- `GET /api/v1/map/`: FeatureCollection con poligonos H3 y propiedades cientificas.

Filtros combinables: `region`, `date`, `start`, `end`, `sensor=modis|viirs`, `fire_only=true|false`, `version`, `pair`, `classification`, `stratum`, `bbox=oeste,sur,este,norte`. `sensor` selecciona celdas observadas por ese sensor; `fire_only` se aplica a las detecciones **originales**. Los campos QA siempre permanecen separados. Una observacion que tiene cero pixeles no equivale a observada sin fuego.

Paginacion: `limit` entre 1 y 1000 (100 por defecto), `offset>=0`; errores invalidos devuelven 400. Listas: `{count,next,previous,results}`. Mapa: `{type,features,count,next,previous}`; exige region, fecha, inicio de rango o bbox. El cliente pagina hasta completar la seleccion; rechaza selecciones de mas de 20000 registros. No carga todo el historico al iniciar. `select_related` evita N+1 en serializacion. Errores de base devuelven 503 generico sin credenciales ni rutas.

Ejemplo vertical:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/summary/?region=guerrero&date=2024-04-16'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/map/?region=guerrero&date=2024-04-16&sensor=modis&limit=1000'
```

## Ejecucion simultanea

Terminal 1, desde la raiz:

```powershell
.\.venv\Scripts\python.exe backend/manage.py runserver 127.0.0.1:8000
```

Terminal 2, desde la raiz:

```powershell
cd frontend
corepack pnpm install --frozen-lockfile
corepack pnpm dev --host 127.0.0.1
```

Con pnpm instalado globalmente se puede usar `pnpm` directamente. El proxy Vite dirige `/api` a `http://127.0.0.1:8000`; `frontend/.env.example` describe `VITE_API_BASE_URL` para usar otro origen. El navegador no recibe secretos.

Abrir `http://127.0.0.1:5173`. Seleccionar Guerrero y 2024-04-16, alternar MODIS/VIIRS/Armonizacion y seleccionar un poligono. Hay una sola instancia Cesium, incluso en movil; cambiar sensor conserva camara, region y fecha. Cambiar datos centra sobre la region. El detalle identifica cada pareja si coinciden celdas de distintos sobrevuelos. Rojo: deteccion original; azul: observacion util sin deteccion; gris: pixeles sin observacion util. Los poligonos son **celdas H3, no perimetros de incendio ni coordenadas de pixeles de fuego**. Cartografia ArcGIS externa con alternativa NaturalEarth incluida en Cesium; no requiere token Ion. Requiere WebGL en el navegador.

## Validacion

```powershell
.\.venv\Scripts\python.exe backend/manage.py test analysis.test_persistence --verbosity 2
cd frontend
corepack pnpm build
```

Los tests de persistencia usan PostgreSQL y requieren permiso de crear una base de pruebas. Cubren conteos, nulos, unicidad, idempotencia, politica de versiones, rollback, serializers, filtros, errores, paginacion, resumen, GeoJSON y solo lectura. `SourceValidationTests` valida las 2179 filas sin usar base de datos; no sustituye las pruebas PostgreSQL.

Fuente V1 verificada: Michoacan 585, Guerrero 775, Tabasco-Chiapas 819. Guerrero: 16 MODIS, 10 VIIRS y 4 AMBOS originales. Tabasco-Chiapas: 8 MODIS, 32 VIIRS y 5 AMBOS. Estas cifras se verificaron tanto en el CSV como en PostgreSQL, comparando todos los campos con `verify_observations`.

Para comprobar persistencia: detener y reiniciar Django, volver a ejecutar `verify_observations` en un proceso nuevo y consultar de nuevo el resumen. No es necesario reimportar al arrancar.

La armonizacion V1 es experimental, historica de abril de 2024 y no constituye una correccion estadistica validada de sensibilidad entre sensores.

## Resultados ejecutados en esta sesion

- Conexion autenticada a PostgreSQL 16.10 comprobada con `backend/.env`, sin mostrar ni modificar credenciales.
- La base configurada `firesight_db` no existia; se creo con el rol configurado como propietario, utilizando su permiso existente de creacion de bases. No se borraron bases ni migraciones.
- `migrate`: todas las migraciones aplicadas, incluida `analysis/0001_initial.py`. Tablas verificadas: `analysis_region`, `analysis_overpasspair`, `analysis_h3observation`, `analysis_dataimport`.
- Primera importacion: 2179 procesados, 2179 insertados. Segunda: 2179 procesados, 0 insertados, 2179 sin cambios.
- Verificacion campo por campo contra PostgreSQL: 2179 coincidencias, incluidos todos los valores nulos, QA y categorias. Michoacan 585, Guerrero 775, Tabasco-Chiapas 819.
- PostgreSQL no dispone de la extension PostGIS. El almacenamiento y las consultas basicas funcionan con H3 sin instalar extensiones adicionales.
- `manage.py check`: sin errores con la configuracion real. `makemigrations --check --dry-run`: sin cambios pendientes.
- `manage.py test analysis --verbosity 1 --noinput`: **58 tests aprobados** en PostgreSQL. Incluye 12 pruebas nuevas de persistencia/API y la suite existente. La base de pruebas separada fue creada y eliminada por Django; los datos de FireSight permanecen en su base principal.
- Se detuvo Django y se inicio en otro proceso. Despues del reinicio, `verify_observations` volvio a confirmar las 2179 observaciones campo por campo, sin reimportacion.
- Pruebas HTTP con Django y Vite simultaneos: pagina, Cesium.js, health, regiones, resumen y mapa respondieron 200 a traves de `http://127.0.0.1:5173/api/`. El proxy alcanza Django y Django consulta PostgreSQL.
- Resumen de Guerrero (2024-04-16): 775 observaciones, 16 pixeles MODIS originales, 10 VIIRS originales y 7 VIIRS QA nominales. Tabasco-Chiapas (2024-04-19): 819 observaciones, 8 MODIS originales, 32 VIIRS originales y 26 VIIRS QA nominales. Celdas AMBOS originales: 4 y 5 respectivamente.
- Pruebas reales en Microsoft Edge headless con WebGL por SwiftShader: globo Cesium cargado, poligonos visibles, clic sobre poligono real y apertura del panel de atributos. MODIS renderizo 759 celdas observadas y VIIRS 773 para Guerrero; los registros sin pixeles del sensor no se presentan como celdas observadas. Cambio MODIS/VIIRS preservo la camara y una unica instancia Viewer.
- La vista Armonizacion muestra aviso experimental, clasificaciones originales y QA, estratos y parejas de sobrevuelos. Cambiar a Tabasco-Chiapas actualizo automaticamente la fecha a 2024-04-19 y cargo 819 registros.
- Vista movil 390 x 844: ancho de documento 390 px, sin desbordamiento horizontal y un solo canvas del globo. La camara encuadra la seleccion completa y la leyenda se separo de las coordenadas.
- TypeScript y `corepack pnpm build`: exitosos. Cesium.js, Assets, Widgets, ThirdParty y Workers incluidos. Advertencias no bloqueantes sobre script Cesium clasico, directivas use client de React Query y bundle principal mayor de 500 kB.
- `corepack pnpm install --frozen-lockfile`: exitoso tras sincronizar lockfile y permitir solamente scripts de esbuild y protobufjs en `pnpm-workspace.yaml`, siguiendo la [configuracion oficial de pnpm](https://pnpm.io/settings/build-settings#allowbuilds).

Limites: la prueba visual usa renderizado WebGL por software en Edge; no equivale a una validacion en todos los dispositivos fisicos. Las capas de imagen ArcGIS requieren red y tienen alternativa NaturalEarth. PostGIS no esta disponible; no bloquea este flujo.

Los endpoints heredados `/api/cells/`, `/api/comparison/` y los otros analisis anteriores conservan su comportamiento basado en archivos por compatibilidad. El frontend activo ya no los solicita. El contrato persistente es `/api/v1/`.

No se hicieron commits, push, merge ni cambios de rama. Los servidores temporales utilizados para pruebas se detienen al terminar; los datos permanecen en PostgreSQL. Para abrir el sistema nuevamente, usar los comandos de ejecucion simultanea de este documento.
