# FireSight: verificacion mundial 2026-11-15

Diagnostico: la base contenia 704 detecciones limitadas a California/Mexico. ensure_day impedia world y areas superiores a 100 grados cuadrados. La camara inicial estaba centrada en Mexico. No habia un filtro continental en los registros.

Cambios: recuperacion mundial limitada a 3 dias por consulta; regiones hasta 31 dias, con unidades diarias (cada solicitud NASA <=5 dias). Hasta 1000 grados cuadrados para nuevas consultas regionales. Los lotes completos y las areas que contienen la consulta se reutilizan desde PostgreSQL. No se cambia el algoritmo cientifico ni modelos.

GET /api/v1/detections/availability/?sensor=modis|viirs consulta disponibilidad NASA y cachea una hora; devuelve limites y ventanas SP/NRT por separado. Calendario min/max y accesos a ultimo dia/siete dias disponibles. SP primero, NRT si cubre el dia. Filtros UTC. El ultimo dia disponible puede diferir del dia actual.

Visualizacion: Automatico, Densidad, Individuales y control de capa. Sin etiquetas numericas de clustering Cesium. Las agrupaciones de PostgreSQL se representan como kernels radiales amarillo/naranja/rojo, intensidad relativa por cantidad de detecciones por celda angular. Es una representacion exploratoria de conteos, no densidad normalizada por km2, temperatura o area quemada. Zoom cercano usa puntos originales, con atributos al seleccionar. Si hay >5000 puntos el servidor mantiene agregacion y lo indica. Cada respuesta agregada tiene como maximo 2000 grupos. Zoom/movimiento con debounce de 700ms solo consulta PostgreSQL (retrieve=false); buscar en area y cambios explicitos recuperan NASA. Peticiones obsoletas se cancelan. Una sola instancia Cesium.

Resultados 2024-04-16, persistidos en PostgreSQL:

| Area | MODIS | VIIRS S-NPP |
|---|---:|---:|
| Mundo | 7411 | 45487 |
| Africa: 10,-15,35,10 | 482 | 2593 |
| Asia: 95,5,120,30 | 1588 | 5186 |
| Australia: 110,-45,155,-10 | 836 | 4504 |
| Europa: -10,35,40,65 | 90 | 493 |
| Pacifico: -150,-50,-149,-49 | 0 | 0 |

Relectura desde un proceso Python nuevo: MODIS 0.061s (743 grupos), VIIRS 0.237s (1466 grupos), CACHE_POSTGRESQL. La primera recuperacion VIIRS tomo 15.83s. No son mediciones del rendimiento WebGL.

NASA disponibilidad consultada: MODIS_SP 2000-11-01..2026-08-31, MODIS_NRT 2026-09-01..2026-11-15; VIIRS_SNPP_SP 2012-01-20..2026-07-31, VIIRS_SNPP_NRT 2026-08-01..2026-11-02. No se codifican estos limites en UI. Prueba 2005: MODIS consulta valida vacia en Pacifico, VIIRS FUERA_DE_DISPONIBILIDAD. Fecha 2099 fuera para ambos.

manage.py check correcto; 71 pruebas Django aprobadas; TypeScript y pnpm build correctos. V1 2179 observaciones verificadas campo por campo; endpoints H3 devuelven 775 Guerrero y 819 Tabasco-Chiapas, geometria Polygon. Sin nueva armonizacion.

Limitaciones: falta QA visual del navegador y medicion de fluidez WebGL; no se afirma verificada. No se integra tabla missing_data: pagina oficial no proporciono tabla consultable durante esta sesion. No se acredita ausencia de brechas de cobertura por recibir CSV vacio. Bloqueo/cache de coordinacion sigue siendo local al proceso, adecuado a runserver local; para varios workers requiere coordinacion compartida. No se implemento fecha compatible de ambos sensores simultaneos porque la navegacion selecciona un sensor a la vez. Densidad FIRMS y H3 permanecen en vistas independientes.

Ejecutar desde raiz:

```powershell
.\.venv\Scripts\python.exe backend/manage.py runserver
corepack pnpm --dir frontend dev
```

En terminales separadas. Credenciales privadas en backend/.env. Sin commit ni push.
