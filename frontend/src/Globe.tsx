import { useEffect, useRef, useState } from 'react'
import type { Viewer } from 'cesium'
import { cellToLatLng, cellToBoundary } from 'h3-js'
import { apiGet, type Cell, type Sensor } from './data'
import type { Place } from './LocationSearch'
import 'cesium/Build/Cesium/Widgets/widgets.css'

declare global { interface Window { Cesium: typeof import('cesium') } }
const Cesium = window.Cesium

type Props = { rows: Cell[]; active: Sensor[]; focusPoint: Place | null; firms?: { start: string; end: string; sensor: Sensor; satellite: string } }

export default function Globe({ rows, active, focusPoint, firms }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const viewer = useRef<Viewer | null>(null)
  const selection = useRef<import('cesium').ScreenSpaceEventHandler | null>(null)
  const [selected, setSelected] = useState<Cell | null>(null)
  const credits = useRef<HTMLDivElement>(null)
  const [error, setError] = useState('')
  const [firmsStatus, setFirmsStatus] = useState('')
  const [detection, setDetection] = useState<Record<string, unknown> | null>(null)
  const [pointerCoords, setPointerCoords] = useState<{lat:number;lon:number} | null>(null)
  useEffect(() => {
    try {
      const map = new Cesium.Viewer(container.current!, {
        baseLayer: false, baseLayerPicker: false, geocoder: false, animation: false,
        timeline: false, navigationHelpButton: false, fullscreenButton: false,
        sceneModePicker: false, infoBox: false, homeButton: false, selectionIndicator: false,
        requestRenderMode: true,
        maximumRenderTimeChange: Infinity,
        creditContainer: credits.current!,
      })
      viewer.current = map
      // Movimiento suave: ruedas menos agresivas y límite de acercamiento.
      const controller = map.scene.screenSpaceCameraController
      controller.inertiaSpin = 0.78
      controller.inertiaTranslate = 0.78
      controller.inertiaZoom = 0.68
      controller.maximumMovementRatio = 0.08
      controller.minimumZoomDistance = 950
      controller.maximumZoomDistance = 35_000_000
      controller.zoomFactor = 2.4
      map.camera.setView({ destination: Cesium.Cartesian3.fromDegrees(-102, 20, 17_000_000) })

      const handler = new Cesium.ScreenSpaceEventHandler(map.scene.canvas)
      handler.setInputAction((movement: {endPosition: import('cesium').Cartesian2}) => {
        const xyz = map.camera.pickEllipsoid(movement.endPosition, map.scene.globe.ellipsoid)
        if (!xyz) { setPointerCoords(null); return }
        const geo = Cesium.Cartographic.fromCartesian(xyz)
        setPointerCoords({lat:Cesium.Math.toDegrees(geo.latitude),lon:Cesium.Math.toDegrees(geo.longitude)})
      }, Cesium.ScreenSpaceEventType.MOUSE_MOVE)
      // Las imágenes NaturalEarthII están pensadas para una vista mundial y se pixelan al acercar.
      // World Imagery proporciona teselas de varios niveles de detalle que Cesium carga al hacer zoom.
      Cesium.ArcGisMapServerImageryProvider.fromUrl(
        'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer',
      ).then(provider => {
        if (map.isDestroyed()) return
        map.imageryLayers.add(new Cesium.ImageryLayer(provider))
        // Superponemos fronteras y divisiones administrativas en una capa transparente.
        Cesium.ArcGisMapServerImageryProvider.fromUrl(
          'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer',
        ).then(boundaries => {
          if (map.isDestroyed()) return
          const layer = new Cesium.ImageryLayer(boundaries)
          map.imageryLayers.add(layer)
          layer.alpha = 0.86
          map.scene.requestRender()
        }).catch(() => {
          if (!map.isDestroyed()) setError('No fue posible cargar la capa de fronteras; el mapa satelital sigue disponible.')
        })
        map.scene.requestRender()
      }).catch(() => {
        if (!map.isDestroyed()) {
          setError('No se pudo cargar la cartografía satelital de alta resolución; se usará la textura básica.')
          Cesium.TileMapServiceImageryProvider.fromUrl(Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII'))
            .then(provider => { if (!map.isDestroyed()) map.imageryLayers.add(new Cesium.ImageryLayer(provider)) })
            .catch(() => { if (!map.isDestroyed()) setError('No se pudo cargar la cartografía terrestre.') })
        }
      })
      return () => { handler.destroy(); selection.current?.destroy(); selection.current = null; viewer.current = null; map.destroy() }
    } catch {
      setError('El globo requiere un navegador con WebGL habilitado.')
    }
  }, [])
  useEffect(() => {
    const map = viewer.current
    if (!map || map.isDestroyed()) return
    selection.current?.destroy()
    map.entities.removeAll()
    setSelected(null)
    // Each pair has its own polygon and source identity. Coincident polygons remain
    // inspectable in the detail panel, without aggregating different overpasses.
    const lookup = new Map<string, Cell>()
    for (const row of rows) {
      if (!active.some(sensor => (row[`${sensor}_pixeles`] ?? 0) > 0)) continue
      const fire = active.some(sensor => (row[`${sensor}_fuego`] ?? 0) > 0)
      const observed = active.some(sensor => (row[`${sensor}_utiles`] ?? 0) > 0)
      const boundary = cellToBoundary(row.celda_h3, true).flat()
      const id = String(row.id)
      lookup.set(id, row)
      map.entities.add({
        id,
        polygon: {
          hierarchy: Cesium.Cartesian3.fromDegreesArray(boundary),
          material: Cesium.Color.fromCssColorString(({ AMBOS: '#ff514c', SOLO_MODIS: '#ffad75', SOLO_VIIRS: '#7ed8ff', NINGUNO: '#438a69', NO_EVALUABLE: '#89909f' }[row.coincidencia_original] || '#89909f')).withAlpha(fire ? .7 : .15),
          height: 100,
          outline: true,
          outlineColor: Cesium.Color.WHITE.withAlpha(.35),
        },
      })
    }
    const handler = new Cesium.ScreenSpaceEventHandler(map.scene.canvas)
    selection.current = handler
    handler.setInputAction((event: { position: import('cesium').Cartesian2 }) => {
      const picked = map.scene.pick(event.position)
      for (const entity of map.entities.values) if (entity.polygon) entity.polygon.outlineColor = new Cesium.ConstantProperty(entity.id === picked?.id?.id ? Cesium.Color.YELLOW : Cesium.Color.WHITE.withAlpha(.2))
      setSelected(lookup.get(picked?.id?.id) ?? null)
      map.scene.requestRender()
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK)
    map.scene.requestRender()
  }, [rows, active])
  useEffect(() => {
    if (!focusPoint || !viewer.current || viewer.current.isDestroyed()) return
    const height = focusPoint.kind === 'country' ? 2_200_000 : focusPoint.kind === 'state' ? 550_000 : 105_000
    viewer.current.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(focusPoint.lon, focusPoint.lat, height),
      duration: 1.7,
    })
  }, [focusPoint])
  useEffect(() => {
    if (!rows.length || !viewer.current) return
    const coordinates = [...new Set(rows.map(row => row.celda_h3))].map(id => {
      const [lat, lon] = cellToLatLng(id)
      return Cesium.Cartesian3.fromDegrees(lon, lat)
    })
    const rectangle = Cesium.Rectangle.fromCartesianArray(coordinates)
    const padding = Math.max(rectangle.width, rectangle.height, .002) * .1
    viewer.current.camera.flyTo({
      destination: new Cesium.Rectangle(rectangle.west - padding, rectangle.south - padding, rectangle.east + padding, rectangle.north + padding),
      duration: .8,
    })
  }, [rows])
  useEffect(() => {
    const map = viewer.current
    if (!map || !firms) return
    const layer = new Cesium.CustomDataSource('NASA FIRMS')
    void map.dataSources.add(layer)
    layer.clustering.enabled = true; layer.clustering.pixelRange = 35; layer.clustering.minimumClusterSize = 3
    let controller: AbortController | undefined
    let timer: ReturnType<typeof setTimeout>
    const load = () => {
      controller?.abort(); controller = new AbortController()
      const signal = controller.signal
      const rect = map.camera.computeViewRectangle()
      let bbox = 'world'
      if (rect && rect.west < rect.east) bbox = [rect.west, rect.south, rect.east, rect.north].map(Cesium.Math.toDegrees).join(',')
      setFirmsStatus('Consultando FIRMS almacenado...')
      const params = new URLSearchParams({ start_date: firms.start, end_date: firms.end, sensor: firms.sensor, bbox, limit: '5000', aggregate: String(map.camera.positionCartographic.height > 500000), cell_degrees: String(map.camera.positionCartographic.height > 5000000 ? 3 : .5) })
      if (firms.satellite) params.set('satellite', firms.satellite)
      layer.entities.removeAll(); setDetection(null); map.scene.requestRender()
      apiGet<{ mode?: string; status: string; count: number; results: { count?: number; id: number; latitude: number; longitude: number; original: Record<string, unknown>; source: string; satellite: string; observed_at: string }[] }>('/v1/detections/?' + params, signal).then(page => {
        if (signal.aborted || map.isDestroyed()) return
        layer.entities.removeAll()
        for (const [index, row] of page.results.entries()) layer.entities.add({ id: (page.mode === 'aggregated' ? 'aggregate-' + index : 'firms-' + row.id), position: Cesium.Cartesian3.fromDegrees(row.longitude, row.latitude), point: { pixelSize: page.mode === 'aggregated' ? Math.min(22, 5 + Math.log2(row.count ?? 1)) : 7, color: firms.sensor === 'modis' ? Cesium.Color.ORANGERED : Cesium.Color.CYAN }, properties: { ...row.original, source: row.source, observed_at: row.observed_at, count: row.count ?? 1, latitude: row.latitude, longitude: row.longitude } })
        setFirmsStatus(page.status + ' / ' + page.results.length + (page.mode === 'aggregated' ? ' grupos / ' : ' puntos / ') + page.count + ' detecciones' + (page.count > 5000 ? '. Acerca el mapa para consultar mas detalle.' : ''))
        map.scene.requestRender()
      }).catch(e => { if (e.name !== 'AbortError') setFirmsStatus('Error consultando FIRMS: ' + e.message) })
    }
    const moved = () => { clearTimeout(timer); timer = setTimeout(load, 350) }
    map.camera.moveEnd.addEventListener(moved)
    const handler = new Cesium.ScreenSpaceEventHandler(map.scene.canvas)
    handler.setInputAction((event: { position: import('cesium').Cartesian2 }) => {
      const entity = map.scene.pick(event.position)?.id
      setDetection((entity?.id?.startsWith('firms-') || entity?.id?.startsWith('aggregate-')) ? entity.properties.getValue(Cesium.JulianDate.now()) : null)
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK)
    load()
    return () => { clearTimeout(timer); controller?.abort(); handler.destroy(); map.camera.moveEnd.removeEventListener(moved); if (!map.isDestroyed()) map.dataSources.remove(layer, true) }
  }, [firms?.start, firms?.end, firms?.sensor, firms?.satellite])
  function focus() {
    const coordinates = [...new Set(rows.map(row => row.celda_h3))].map(id => cellToLatLng(id))
    if (!coordinates.length) return
    const rectangle = Cesium.Rectangle.fromCartesianArray(coordinates.map(([lat, lon]) => Cesium.Cartesian3.fromDegrees(lon, lat)))
    if (rectangle.width < .02 && rectangle.height < .02) {
      const [lat, lon] = coordinates[0]
      viewer.current?.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(lon, lat, 120000) })
    } else viewer.current?.camera.flyTo({ destination: rectangle })
  }
  return <section className="map" aria-label="Globo terrestre interactivo">
    {firms && <div className="map-actions" style={{ top: 65 }}>{firmsStatus}</div>}
    {firms && detection && <aside className="cell-detail"><button onClick={() => setDetection(null)}>Cerrar</button><h3>Deteccion NASA FIRMS</h3><dl>{Object.entries(detection).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value ?? 'Desconocido')}</dd></div>)}</dl></aside>}
    <div ref={container} className="globe" />
    <div className="map-credits" ref={credits} aria-label="Créditos de los proveedores cartográficos" />
    <div className="map-actions">
      <button onClick={() => viewer.current?.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(-102, 20, 17_000_000) })}>Vista mundial</button>
      <button disabled={!rows.length || !!error} onClick={focus}>Centrar observaciones</button>
    </div>
    {error && <p className="map-error" role="status">{error}</p>}
    <div className="map-coordinate-display" aria-live="off">
      <span>COORDENADAS</span>
      <strong>{(pointerCoords ?? (focusPoint ? {lat:focusPoint.lat,lon:focusPoint.lon} : null))
        ? `Lat ${(pointerCoords?.lat ?? focusPoint!.lat).toFixed(5)}°  ·  Lon ${(pointerCoords?.lon ?? focusPoint!.lon).toFixed(5)}°`
        : 'Mueve el cursor sobre el mapa'}</strong>
      <small>{pointerCoords ? 'Posición del cursor · WGS84' : focusPoint ? `Centro de ${focusPoint.name} · WGS84` : 'Sistema WGS84'}</small>
    </div>
    <div className="legend">{firms ? 'MODIS naranja / VIIRS azul. Grupos al alejar; puntos reales al acercar.' : 'AMBOS rojo / SOLO_MODIS naranja / SOLO_VIIRS azul / NINGUNO verde / NO_EVALUABLE gris'}</div>
    {selected && <aside className="cell-detail" aria-label="Detalle de celda H3">
      <button onClick={() => setSelected(null)} aria-label="Cerrar detalle">Cerrar</button>
      <h3>{selected.celda_h3}</h3>
      <p>{selected.region_nombre} / {selected.fecha} / {selected.version_armonizacion}</p>
      {rows.filter(row => row.celda_h3 === selected.celda_h3).map(row => <div key={row.id}>
        <p>MODIS {row.modis_sobrevuelo} / VIIRS {row.viirs_sobrevuelo}</p>
        <dl><dt>MODIS fuego original / utiles</dt><dd>{row.modis_fuego ?? 'Desconocido'} / {row.modis_utiles ?? 'Desconocido'}</dd>
        <dt>VIIRS fuego original / utiles</dt><dd>{row.viirs_fuego ?? 'Desconocido'} / {row.viirs_utiles ?? 'Desconocido'}</dd>
        <dt>VIIRS sin bow-tie / QA nominal</dt><dd>{row.viirs_fuego_sin_bowtie ?? 'Desconocido'} / {row.viirs_fuego_qa_nominal ?? 'Desconocido'}</dd>
        <dt>Bow-tie residual / geolocalizacion no nominal</dt><dd>{row.viirs_bowtie_residual ?? 'Desconocido'} / {row.viirs_geo_no_nominal ?? 'Desconocido'}</dd>
        <dt>Cobertura compartida estimada</dt><dd>{row.cobertura_compartida_pct ?? 'Desconocida'} %</dd>
        <dt>Diferencia temporal</dt><dd>{row.diferencia_min ?? 'Desconocida'} min / {row.estrato_temporal}</dd>
        <dt>Original / despues de QA</dt><dd>{row.coincidencia_original} / {row.coincidencia_qa}</dd></dl>
      </div>)}
    </aside>}
  </section>
}
