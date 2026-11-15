# Correccion UX y armonizacion, 2026-11-15

Causa de cero registros: main.tsx deshabilitaba React Query sin region y data.ts rechazaba consultas sin region. Django ya admite start/end sin region. Se retiro esa exigencia y el selector principal; la fecha consulta todas las regiones procesadas. No se alteraron modelos ni algoritmos cientificos.

PostgreSQL: 2179 observaciones V1 verificadas campo por campo. Consulta de fecha sin region 2024-04-16: 775/746 evaluables/4 AMBOS. 2024-04-19: 819/718/5. Regresion agregada a PersistenceTests. Suite previa de 71 pruebas aprobada; prueba adicional por fecha aprobada separadamente. manage.py check correcto.

UTF-8: meta charset ya era correcto. Se repararon palabras con signos de interrogacion literales y secuencias de mojibake detectadas en main.tsx; escrituras explicitas UTF-8. No se reemplazaron operadores TypeScript.

Cesium: se retiro listener moveEnd que vaciaba capas y consultaba datos al navegar. Los puntos persisten hasta cambiar filtros o buscar explicitamente. Respuestas canceladas no actualizan capas. Efecto H3 depende de sensores por valor, evitando reconstrucciones al mover cursor. Se muestran tambien celdas NO_EVALUABLE sin pixeles. Una instancia Viewer.

Controles: individuales predeterminado, densidad opcional; retirados automatico, checkbox capa, centrar observaciones y region cientifica. Se conserva modo al alternar sensor. Herramienta rectangular con pickEllipsoid, Rectangle.fromCartographicArray, control de camara deshabilitado durante arrastre y restaurado al finalizar/cancelar/limpiar efecto. Escape cancela. Bbox antimeridiano se divide en backend. Requiere prueba manual del gesto, no acreditada.

Densidad: nueva density.ts, textura 720x360 con convolucion gaussiana truncada, sigma 2 celdas de medio grado, radio 5 celdas; bordes longitudinales periodicos. Normalizacion log(1+conteo)/log(1+max), alpha maxima .65, naranja/rojo moderado. Se proyecta como Rectangle sobre el globo. Intensidad relativa de conteos suavizados; no normalizada por km2 y no es temperatura ni area quemada. Sin bibliotecas nuevas.

Panel FIRMS compacto con sensor, rango UTC, area y conteo real de API; sin tablas H3 o metricas QA inexistentes. Detalles de deteccion al seleccionar. Armonizacion conserva resumen cientifico y panel por celda con QA, tiempo, cobertura y pareja. Footer TerraFlare con atribucion y aclaracion de independencia.

API detail=true permite obtener hasta 5000 puntos originales sin transformarlos en agregaciones. Si el total excede 5000 se indica vista parcial y se debe buscar una zona menor; next_offset sigue disponible. No se afirma renderizado simultaneo de todos los puntos mundiales.

Archivos de esta correccion: frontend/src/main.tsx, data.ts, Globe.tsx, density.ts (nuevo), style.css; backend/analysis/detections_api.py y test_persistence.py. No dependencias nuevas. pnpm build y TypeScript aprobados. Advertencia Vite de bundle >500KB y script global Cesium permanece.

Pendiente: prueba visual de WebGL, densidad, arrastre rectangular, seleccion, alternancia repetida y responsive en navegador. No declarar validacion visual sin acceso real.
