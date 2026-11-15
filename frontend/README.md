# TerraFlare

Frontend del visor satelital para el NASA Space Apps Challenge. Usa React, TypeScript, Vite, Tailwind CSS, CesiumJS, Recharts y TanStack Query. El ZIP contiene el frontend. El backend Django del equipo se ejecuta en su propia carpeta.

## Arranque en VS Code (Windows)

Usa Node.js 22.12 o posterior. Abre dos terminales de PowerShell.

1. En la carpeta del backend que contiene `manage.py`, con el entorno Python del equipo activado, ejecuta:

   ```powershell
   python manage.py runserver 127.0.0.1:8000
   ```

2. En la carpeta `TerraFlare`, que contiene `package.json`, ejecuta:

   ```powershell
   npm ci
   npm run dev
   ```

3. Abre http://localhost:5173. Si Django usa otro puerto, copia `.env.example` a `.env.local`, ajusta `DJANGO_URL` y reinicia Vite.

Usa `npm run build` para validar TypeScript y generar `dist`. En un despliegue, sirve `dist` en la raíz del sitio y dirige `/api/` a Django en el mismo origen. No coloques credenciales de Earthdata en el frontend.

## Qué muestra cada vista

| Vista | Resultados |
| --- | --- |
| Mapa | Globo 3D con rotación y zoom, capas MODIS y VIIRS, fecha y opción para centrar las observaciones. Los marcadores representan centros H3 con registros de fuego, con independencia del total de píxeles detectados en cada celda. |
| Sensores | Productos satelitales, píxeles de fuego, celdas observadas y porcentaje ponderado de píxeles útiles por sensor. |
| Análisis | Conteos y gráfica de coincidencias y detecciones exclusivas dentro de los registros candidatos. Las banderas de observación útil en ambos sensores y del umbral exploratorio se leen de la API. |

El 80 % pertenece al criterio exploratorio del procesamiento. El frontend no valida la comparabilidad temporal ni vuelve a clasificar los píxeles. Si faltan registros, muestra el estado correspondiente. Seleccionar una fecha sin archivo produce un 404 de datos ausentes.

## Contrato actual

`GET /api/cells/?date=YYYY-MM-DD` devuelve `{ date, total, data }`. La API del equipo lee los CSV con nombres `analisis_celdas_YYYY-MM-DD.csv` ubicados en `Industrial_Systems/src`. El visor abre el lote del 19 de abril de 2024. El filtro es por día. La API actual no admite periodos ni identifica regiones en las filas. Los filtros de país y estado se habilitan cuando la respuesta incluye `pais` y `estado`. La aplicación tampoco asigna nombres de regiones basándose únicamente en la fecha. La exportación CSV y los resultados armonizados certificados quedan pendientes.

El mapa base local Natural Earth II se incluye con Cesium. Las coordenadas se calculan desde los identificadores H3 publicados por Django. Los conteos y los identificadores de sobrevuelo se muestran exclusivamente con datos del lote. El archivo `src/data.ts` concentra el contrato y las reglas de interpretación del frontend.

## Búsqueda de estados, ciudades y coordenadas

- El campo **País** usa un catálogo local y sugiere resultados desde la primera letra.
- Al elegir México, **Estado / provincia** ofrece sus 32 entidades federativas y **Ciudad / municipio** ofrece una selección de localidades conocidas sin conexión. El catálogo local de municipios no es exhaustivo.
- Para otras localidades y países, el frontend consulta Photon y, si falla, Open-Meteo Geocoding. Requiere conexión y depende de la disponibilidad y cobertura de servicios públicos.
- Las **coordenadas WGS84** se visualizan dentro del globo: al mover el cursor muestran la posición geográfica bajo este; fuera de él muestran el centro del lugar seleccionado.
- Seleccionar un lugar centra el mapa; **no equivale a aplicar un filtro espacial exacto** a los datos H3 si la API Django no incluye geometrías de ciudades y municipios.
