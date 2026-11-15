# FireSight global: estado comprobado

Credenciales FIRMS y Earthdata autenticadas sin imprimir valores. Se preservaron las 2179 observaciones V1 campo por campo.

## Datos realmente importados

Cobertura solicitada: world. Fecha UTC: 2024-04-16.

| Fuente | Registros persistidos |
|---|---:|
| MODIS_SP | 7411 |
| VIIRS_SNPP_SP | 45487 |
| VIIRS_NOAA20_SP | 48278 |
| VIIRS_NOAA21_SP | 45034 |
| Total | 146210 |

La importacion consulta disponibilidad NASA, procesa un dia por transaccion, inserta en bloques de 1000, conserva atributos originales y registra cada unidad fecha/fuente/area. Las unidades completas se omiten al reanudar. El fingerprint incluye fuente y todos los atributos originales: revisiones distintas se conservan como registros distintos; no se deben sumar revisiones como si fueran detecciones independientes sin una politica adicional de seleccion de versiones. No se refrescan automaticamente lotes completos.

## Comandos Windows

Desde la raiz:

```powershell
.\.venv\Scripts\python.exe backend/manage.py import_firms --source MODIS_SP --start 2024-04-16 --end 2024-04-16
.\.venv\Scripts\python.exe backend/manage.py import_firms --source VIIRS_SNPP_SP --start 2024-04-16 --end 2024-04-16
.\.venv\Scripts\python.exe backend/manage.py runserver
```

En otra terminal:

```powershell
cd frontend
corepack pnpm dev
```

Activar el control `Detecciones globales NASA FIRMS` debajo de los filtros. MODIS/VIIRS selecciona sensor. Buscar un lugar o mover el globo consulta el bbox visible; la fecha inicial es historica. Se dibujan coordenadas originales con agrupacion Cesium y panel de atributos al seleccionar. El limite es 5000 puntos por respuesta; el estado informa recorte y pide acercar el mapa. Todavia falta agregacion geoespacial en servidor y carga progresiva de todas las paginas: esta version no acredita capacidad de visualizar todos los puntos simultaneamente.

Endpoints nuevos: GET /api/v1/sensors/ y GET /api/v1/detections/?sensor=modis&start_date=2024-04-16&end_date=2024-04-16&bbox=world&limit=100&offset=0. satellite acepta el identificador original FIRMS. Respuestas incluyen imports, estado, count y next_offset. Sin puntos no significa ausencia de incendios; la procedencia enumera las areas realmente importadas. Falta selector de plataforma en la interfaz y estados de cobertura completa/parcial refinados.

## Ciencia

`src/preparar_lotes.py` ahora recibe --bbox, --start, --end y --output y rechaza sobrescribir manifiestos. Consulta real California bbox -122.5,38,-122,38.5 para 2024-04-16: dos granulos MYD14 y tres VNP14IMG con geolocalizacion asociada; una pareja candidata con diferencia de inicio de nueve minutos. Manifiesto: src/resultados_lotes/global_california_20240416_manifest.csv. Esto NO constituye armonizacion: falta descargar y procesar productos, evaluar cobertura, QA y tiempos por celda, generalizar los demas scripts y persistir la nueva ejecucion. Earthdata autentico correctamente; no se descargaron granulos en esta etapa.

Dependencias cientificas separadas en backend/requirements-science.txt. Variables: FIRMS_MAP_KEY en backend/.env; EARTHDATA_USERNAME y EARTHDATA_PASSWORD en .env raiz. Los secretos no se envian al navegador.

## Verificacion

61 pruebas existentes pasaron antes de agregar el test de parametros de detecciones. Cuatro pruebas del modulo NASA pasaron despues. TypeScript y pnpm build exitosos. API detecciones respondio 200 contra PostgreSQL; corregido filtro por fechas para usar limites UTC e indice temporal. Reimportacion MODIS omitio el lote completo. V1 verificado sin cambios. Pendiente prueba visual del nuevo modo FIRMS, paginacion/agregacion global completa y ejecucion cientifica fuera de pilotos. Sin commits ni push.
