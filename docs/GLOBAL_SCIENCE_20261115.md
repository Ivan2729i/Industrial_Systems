# TerraFlare: integracion cientifica regional y lotes mundiales - 2026-11-15

## Estado comprobado

Rama ivan-dev; sin commit/push/merge. Se reutilizaron analizar_celdas.py, omparar_tiempos.py, cobertura_espacial.py y generar_armonizacion_v1.py a traves de run_harmonization.py. No se sustituyeron por coincidencias FIRMS. Se preservaron los 2179 registros V1 campo por campo. Nuevas versiones separadas, sin tablas por fecha ni archivos binarios en PostgreSQL.

Resultados Level 2 reales, 2024-04-16:

| Extension WGS84 | Version | Registros | Evaluables | QA AMBOS | MODIS fuego | VIIRS fuego |
|---|---|---:|---:|---:|---:|---:|
| Zambia 31,-15,31.3,-14.7 | global_v2_experimental | 203 | 153 | 1 | 2 | 4 |
| Tailandia 101,14,101.2,14.2 | global_v2_experimental | 97 | 86 | 0 | 0 | 1 |
| Australia 131,-15,131.5,-14.5, dos parejas | world_batch_v2 | 1258 | 0 | 0 | 0 | 0 |
| Mexico -100,17,-99.5,17.5 | world_batch_v2 | 547 | 527 | 4 | 14 | 10 |
| Zambia, solicitud administrativa API | l2_regional_v2 | 203 | 153 | 1 | 2 | 4 |

PostgreSQL: 4487 observaciones versionadas en total, incluyendo el piloto. Las versiones representan ejecuciones cientificas diferenciadas, no incendios individuales sumables. Australia se proceso y conservo aun sin observaciones evaluables: no se sustituyeron resultados con datos inventados.

Productos descargados: MYD14/MYD03 061 y VNP14IMG/VNP03IMG 002. Pares nuevos: Zambia A2024107.1210 / A2024107.1206; Tailandia A2024107.0725 / A2024107.0712; Australia A2024107.1630 / A2024107.1630 y A2024107.0535 / A2024107.0524. Mexico A2024107.2035 / A2024107.2042 reutilizo cuatro archivos locales existentes. Inventario exacto de 20 archivos utilizados: scientific_products_20261115.csv (16 descargados en esta sesion, 4 reutilizados).

## Motor y procedencia

run_harmonization recibe fecha, bbox, granulos, resolucion, version y workdir; inyecta configuracion dinamica aislada en los algoritmos existentes. Ya no requiere editar diccionarios para nuevas fechas/regiones ni impone 2024. Conversion TAI93 con transiciones historicas de segundos intercalares, comprobada para 2005, 2013 y 2024. Los segundos intercalares exactos no representables en datetime se rechazan explicitamente. Mantener actualizada la tabla IERS si cambia en el futuro.

Descubrimiento mediante earthaccess/CMR, ventana +/-15 minutos para parejas que cruzan medianoche; la fecha se ancla al granulo MODIS. Productos de fuego filtrados por bbox; geolocalizacion asociada por producto/periodo y version en nombre real obtenido desde data_links. Se comprobo un defecto: exigir bbox/version de coleccion a las colecciones de geolocalizacion descartaba resultados validos. No se presupone que GranuleUR sea nombre descargable. La lectura real valida coordenadas y dimensiones; la seleccion previa de CMR es candidata, no prueba final de cobertura evaluable.

Los nuevos trabajos conservan archivos originales en src/datos/cache_level2, productos/versiones/bytes e identificadores CMR; nuevas descargas tambien registran SHA256. Se conservan QA, bow-tie residual, geolocalizacion no nominal, tiempos por escaneo y cobertura aproximada. No se ha validado equivalencia de sensibilidad ni conversion de conteos entre sensores. Las huellas son reconstrucciones experimentales, no footprints instrumentales exactos.

Fuentes: https://earthaccess.readthedocs.io/en/latest/user/howto/get-urls-for-granules/ ; https://earthaccess.readthedocs.io/en/latest/user/howto/download-to-local-machine/ ; https://caps.gsfc.nasa.gov/simpson/time/leapseconds.html .

## Cola y procesamiento progresivo

Se reutiliza HarmonizationRun; no nuevas tablas. POST /api/v1/harmonization/jobs/ solo encola. Cabecera X-Scientific-Key debe coincidir con SCIENTIFIC_ADMIN_KEY del backend. Si falta configuracion responde503; sin autorizacion403. Validacion de fecha/bbox/version/resolucion, area maxima .25 grados cuadrados, resoluciones5..8 y cola acotada16. Admision y worker coordinados con locks PostgreSQL. El endpoint no descarga ni procesa productos.

scientific_worker --watch ejecuta fuera de HTTP, un proceso secuencial con lock global, etapas de busqueda/parejas/proceso/error/completado, progreso por pareja, limites de tiempo y resultados parciales persistidos. --retry-errors reintenta fallidos; --recover-interrupted recupera trabajos interrumpidos. Los directorios completados se omiten; importacion cientifica es idempotente. Repetir dos solicitudes API iguales devolvio el mismo id8; el worker completo203 registros. Prueba administrativa con clave efimera en proceso, sin mostrarla ni escribir secretos reales.

plan_world_harmonization usa grilla de medio grado entre -85 y85, limitando a16 particiones por invocacion. El manifiesto world_batch_20240416.json registra dos particiones solicitadas y244798 no solicitadas; no significa cobertura mundial completa. Los jobs3 y4 terminaron tres parejas con1805 registros. Reejecutar el plan y el worker no duplico observaciones. Registros son por area/pareja/H3/version: no deben sumarse regiones solapadas como si fueran eventos independientes.

Limites actuales: no particiones polares, ni solicitud cientifica que cruce antimeridiano en una sola caja; debe dividirse. FIRMS si divide antimeridiano. La planificacion mundial es progresiva y requiere recursos/operacion explicita; no se declara procesado el mundo. Comparabilidad exploratoria A0..5min y B>5..15min.

## Web y API

GET /api/v1/harmonization/ conserva filtros date/start/end/version/bbox y paginacion. GET /api/v1/harmonization/availability/ informa cobertura persistida por region/fecha/version. GET /api/v1/harmonization/runs/ informa estado y productos, con parametros publicos permitidos; no expone rutas privadas ni credenciales.

Armonizacion usa las nuevas versiones igual que V1. Seleccionar version y fecha2024-04-16, o Ver resultados en un trabajo completado. Los indicadores de centros H3 estan identificados como agregados; positivos QA rojo/naranja/azul por defecto, demas en Todas las observaciones H3. No son coordenadas de pixeles individuales ni perimetros. Ver observaciones ajusta camara explicitamente.

Se agrego ScientificJobs.tsx: solicitud administrativa desde un rectangulo pequeno, clave solo en estado temporal, progreso cada10s y acceso a resultados. H3 se refresca desde PostgreSQL cada10s. El rectangulo sirve para consultas y preparacion cientifica; el calculo pesado requiere el worker activo. Periodos y capas MODIS/VIIRS/H3 permanecen separados y persistentes; respuestas obsoletas no sobrescriben capas actuales. No se modifico identidad TerraFlare.

## Geografia

249 paises ISO disponibles en menu con scroll y busqueda completa (retirado slice10), sin texto redundante Pais:codigo. 5046 subdivisiones ISO con carga diferida; Espana prioriza17 comunidades y2 ciudades autonomas. Conteos comprobados: Mexico32, Brasil27, India36, Argentina24; EEUU50estados+DC+6areas pertinentes. Nombres/codigos oficiales, coordenadas resueltas antes de seleccionar; no se inventan localidades.

Photon/OSM con bbox administrativo, respaldo Open-Meteo; cache cliente5min/100consultas, carga progresiva hasta50 localidades por busqueda y solicitudes con debounce. Identificadores OSM cuando estan disponibles. Pruebas reales Pais/Subdivision/Ciudad para Veracruz, Acapulco, Sao Paulo, Sevilla, Los Angeles y Mumbai con bbox del estado, pais correcto y coordenadas reales. No equivale a un censo exhaustivo de todos los municipios. Si el servicio no cubre una zona, permite seleccion directa de area. La flecha es SVG dentro de grid, sin posicion absoluta.

## Pruebas

77 pruebas Django aprobadas tras integrar la cola; check correcto; migraciones existentes aplicadas, ninguna nueva necesaria; verificacion V1 integra; reimportacion Zambia203 filas insertadas0/sin cambios203; reanudacion de lote sin duplicados. HTTP real localhost8000: health200, version global_v2 devuelve300, disponibilidad world_batch_v2 devuelve1805 y l2_regional_v2 devuelve203; FIRMS VIIRS devuelve45487. Frontend localhost5173 responde200. TypeScript y pnpm build correctos. Advertencias de tamano de bundle y script Cesium global permanecen.

Pendiente validacion visual de Cesium, diez alternancias en navegador, rectangulo, densidad y responsive: no se declara superada por compilar. Las pruebas de diez ciclos anteriores acreditan API, no navegacion visual.

## Ejecucion PowerShell (terminales separadas, desde la raiz)

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt -r backend/requirements-science.txt
.\.venv\Scripts\python.exe backend/manage.py migrate
.\.venv\Scripts\python.exe backend/manage.py runserver
```

```powershell
corepack pnpm --dir frontend install --frozen-lockfile
corepack pnpm --dir frontend dev
```

```powershell
.\.venv\Scripts\python.exe backend/manage.py scientific_worker --watch --limit 1
```

Configurar SCIENTIFIC_ADMIN_KEY con un valor privado largo en backend/.env para habilitar solicitudes de la web; no es una credencial NASA y no se publica en frontend. NASA_FIRMS_MAP_KEY y POSTGRES_* siguen en backend/.env; Earthdata permanece en .env raiz.

Reproducir/reanudar el lote controlado (las particiones ya completadas se reutilizan):

```powershell
.\.venv\Scripts\python.exe backend/manage.py plan_world_harmonization --date 2024-04-16 --science-version world_batch_v2 --start-index 101422 --limit 1 --manifest src/resultados_lotes/world_batch_20240416.json
.\.venv\Scripts\python.exe backend/manage.py plan_world_harmonization --date 2024-04-16 --science-version world_batch_v2 --start-index 147040 --limit 1 --manifest src/resultados_lotes/world_batch_20240416.json
.\.venv\Scripts\python.exe backend/manage.py scientific_worker --limit 2
```

No usar --version en el comando Django del planificador: es opcion reservada de Django; se utiliza --science-version.
