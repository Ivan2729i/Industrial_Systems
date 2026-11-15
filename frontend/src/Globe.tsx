import { useEffect, useRef, useState } from 'react'
import type { Viewer } from 'cesium'
import { cellToLatLng, cellToBoundary } from 'h3-js'
import { densityImage } from './density'
import { apiGet, type Cell, type Sensor } from './data'
import type { Place } from './LocationSearch'
import 'cesium/Build/Cesium/Widgets/widgets.css'

declare global { interface Window { Cesium: typeof import('cesium') } }
const Cesium = window.Cesium

type Props = { onAreaSelected?: (bbox:string)=>void; rows: Cell[]; active: Sensor[]; focusPoint: Place | null; firms?: { start: string; end: string; sensor: Sensor; satellite: string; region: string; valid: boolean } }

export default function Globe({ rows, active, focusPoint, firms, onAreaSelected }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const viewer = useRef<Viewer | null>(null)
  const firmsLayers = useRef<Partial<Record<Sensor, import('cesium').CustomDataSource>>>({})
  const responseCache = useRef(new Map<string, {data:any;expires:number}>())
  const h3Layer = useRef<import('cesium').CustomDataSource | null>(null)
  const [allH3, setAllH3] = useState(false)
  const selection = useRef<import('cesium').ScreenSpaceEventHandler | null>(null)
  const [selected, setSelected] = useState<Cell | null>(null)
  const credits = useRef<HTMLDivElement>(null)
  const [error, setError] = useState('')
  const [displayMode, setDisplayMode] = useState('points')
  const [drawing, setDrawing] = useState(false)
  const [searchArea, setSearchArea] = useState<string | null>(null)
  const [searchId, setSearchId] = useState(0)
  useEffect(() => { setSearchArea(null) }, [focusPoint])
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
      return () => { handler.destroy(); selection.current?.destroy(); selection.current = null; viewer.current = null; firmsLayers.current={}; h3Layer.current=null; map.destroy() }
    } catch {
      setError('El globo requiere un navegador con WebGL habilitado.')
    }
  }, [])
  useEffect(() => {
    const map = viewer.current
    if (!map || map.isDestroyed()) return
    selection.current?.destroy(); selection.current=null
    if (!h3Layer.current) { h3Layer.current=new Cesium.CustomDataSource('harmonization-h3'); void map.dataSources.add(h3Layer.current) }
    const entities=h3Layer.current.entities
    h3Layer.current.show=!firms
    if (firms) {map.scene.requestRender(); return}
    entities.removeAll()
    setSelected(null)
    // Each pair has its own polygon and source identity. Coincident polygons remain
    // inspectable in the detail panel, without aggregating different overpasses.
    const lookup = new Map<string, Cell>()
    for (const row of rows) {
      const fire = active.some(sensor => (row[`${sensor}_fuego`] ?? 0) > 0)
      if (!allH3 && !['AMBOS','SOLO_MODIS','SOLO_VIIRS'].includes(row.coincidencia_qa)) continue
      const boundary = cellToBoundary(row.celda_h3, true).flat()
      const id = String(row.id)
      const [centerLat,centerLon]=cellToLatLng(row.celda_h3)
      const cellColor=Cesium.Color.fromCssColorString(({AMBOS:'#ff514c',SOLO_MODIS:'#ffad75',SOLO_VIIRS:'#7ed8ff',NINGUNO:'#438a69',NO_EVALUABLE:'#89909f'}[row.coincidencia_qa] || '#89909f'))
      lookup.set(id, row)
      entities.add({
        id,
        position:fire?Cesium.Cartesian3.fromDegrees(centerLon,centerLat,150):undefined,
        point:fire?{pixelSize:7,color:cellColor,outlineColor:Cesium.Color.WHITE.withAlpha(.5),outlineWidth:1}:undefined,
        polygon: {
          hierarchy: Cesium.Cartesian3.fromDegreesArray(boundary),
          material: cellColor.withAlpha(fire ? .65 : .06),
          height: 100,
          outline: false,
          outlineColor: Cesium.Color.WHITE.withAlpha(.35),
        },
      })
    }
    const handler = new Cesium.ScreenSpaceEventHandler(map.scene.canvas)
    selection.current = handler
    handler.setInputAction((event: { position: import('cesium').Cartesian2 }) => {
      const picked = map.scene.pick(event.position)
      for (const entity of entities.values) if (entity.polygon) entity.polygon.outlineColor = new Cesium.ConstantProperty(entity.id === picked?.id?.id ? Cesium.Color.YELLOW : Cesium.Color.WHITE.withAlpha(.2))
      setSelected(lookup.get(picked?.id?.id) ?? null)
      map.scene.requestRender()
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK)
    map.scene.requestRender()
  }, [rows, active.join(','), allH3, !!firms])
  useEffect(() => {
    if (!focusPoint || !viewer.current || viewer.current.isDestroyed()) return
    const height = focusPoint.kind === 'country' ? 2_200_000 : focusPoint.kind === 'state' ? 550_000 : 105_000
    viewer.current.camera.flyTo({
      destination: focusPoint.bbox ? Cesium.Rectangle.fromDegrees(...focusPoint.bbox) : Cesium.Cartesian3.fromDegrees(focusPoint.lon, focusPoint.lat, height),
      duration: 1.7,
    })
  }, [focusPoint])
  useEffect(() => {
    const map = viewer.current
    if (!map) return
    for(const [sensor,layer] of Object.entries(firmsLayers.current)) layer!.show=!!firms && sensor===firms.sensor
    if(h3Layer.current) h3Layer.current.show=!firms
    map.scene.requestRender()
    if (!firms) return
    if (!firms.valid || !firms.start || !firms.end || firms.start > firms.end || (Date.parse(firms.end)-Date.parse(firms.start))/86400000 > 30) { if(firmsLayers.current[firms.sensor])firmsLayers.current[firms.sensor]!.show=false;map.scene.requestRender();setFirmsStatus('Selecciona un rango válido de hasta 31 días.'); return }
    let layer=firmsLayers.current[firms.sensor]
    if(!layer) { layer=new Cesium.CustomDataSource('firms-'+firms.sensor);firmsLayers.current[firms.sensor]=layer;void map.dataSources.add(layer) }
    layer.show=true
    // Numeric cluster labels are disabled. Aggregations come from PostgreSQL.
    layer.clustering.enabled = false
    let controller: AbortController | undefined
    const load = (retrieve = true) => {
      controller?.abort(); controller = new AbortController()
      const signal = controller.signal
      const rect = map.camera.computeViewRectangle()
      let bbox = 'world'
      if (focusPoint?.bbox) bbox=focusPoint.bbox.join(',')
      else if (focusPoint) bbox = [focusPoint.lon-.5,focusPoint.lat-.5,focusPoint.lon+.5,focusPoint.lat+.5].join(',')

      setFirmsStatus('Consultando FIRMS almacenado...')
      if (searchArea) bbox = searchArea
      if (!retrieve) bbox = rect && map.camera.positionCartographic.height < 5000000 ? [rect.west,rect.south,rect.east,rect.north].map(Cesium.Math.toDegrees).join(',') : 'world'
      const density = displayMode === 'density'
      const params = new URLSearchParams({ start_date: firms.start, end_date: firms.end, sensor: firms.sensor, bbox, limit: '5000', aggregate: String(density), detail: String(!density), cell_degrees: bbox==='world' ? '1' : '.1' })
      params.set('retrieve', String(retrieve))
      if (retrieve && firms.region && !searchArea) params.set('region', firms.region)
      if (firms.satellite) params.set('satellite', firms.satellite)
      setDetection(null)
      const cacheKey=params.toString()
      layer!.show=false
      map.scene.requestRender()
      const cached=responseCache.current.get(cacheKey)
      const request=cached && cached.expires>Date.now() ? Promise.resolve(cached.data) : apiGet<{ retrieval?: string[]; mode?: string; status: string; count: number; results: { count?: number; id: number; latitude: number; longitude: number; original: Record<string, unknown>; source: string; satellite: string; observed_at: string }[] }>('/v1/detections/?' + params, signal)
      request.then(page => {
        if (signal.aborted || map.isDestroyed()) return
        if (!page.status.includes('ERROR')) responseCache.current.set(cacheKey,{data:page,expires:Date.now()+120000})
        if(responseCache.current.size>12) responseCache.current.delete(responseCache.current.keys().next().value!)
        layer!.show=true
        layer!.entities.removeAll()
        if (density) layer!.entities.add({id:'density',rectangle:{coordinates:Cesium.Rectangle.MAX_VALUE,material:new Cesium.ImageMaterialProperty({image:densityImage(page.results,page.cell_degrees ?? 1),transparent:true}),height:50}})
        for (const [index, row] of (density ? [] : page.results).entries()) {
          const grouped=page.mode==='aggregated'
          const entity=layer!.entities.add({id:(grouped?'aggregate-':'firms-')+(grouped?index:row.id),position:Cesium.Cartesian3.fromDegrees(row.longitude,row.latitude),properties:{...row.original,sensor:firms.sensor,satellite:row.satellite,source:row.source,observed_at:row.observed_at,count:row.count??1,latitude:row.latitude,longitude:row.longitude,magnitude:grouped?'Cantidad de detecciones por celda geográfica':'Detección térmica individual'}})
          entity.point=new Cesium.PointGraphics({pixelSize:grouped?10:6,color:firms.sensor==='modis'?Cesium.Color.ORANGERED:Cesium.Color.CRIMSON,outlineColor:Cesium.Color.WHITE,outlineWidth:1})
        }
        setFirmsStatus(page.status.replaceAll('_',' ') + ' / ' + page.results.length + (page.mode === 'aggregated' ? ' grupos / ' : ' puntos / ') + page.count + ' detecciones' + (page.count > 5000 ? '. Vista parcial: busca en un área menor para consultar más detalle.' : ''))
        map.scene.requestRender()
      }).catch(e => { if (e.name !== 'AbortError') setFirmsStatus('Error consultando FIRMS: ' + e.message) })
    }
    const handler = new Cesium.ScreenSpaceEventHandler(map.scene.canvas)
    handler.setInputAction((event: { position: import('cesium').Cartesian2 }) => {
      const entity = map.scene.pick(event.position)?.id
      setDetection((entity?.id?.startsWith('firms-') || entity?.id?.startsWith('aggregate-')) ? entity.properties.getValue(Cesium.JulianDate.now()) : null)
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK)
    load()
    return () => { controller?.abort(); handler.destroy(); /* Layers persist across tabs; Viewer owns their destruction. */ }
  }, [firms?.start, firms?.end, firms?.sensor, firms?.satellite, firms?.region, focusPoint, searchArea, searchId, displayMode, firms?.valid])
  useEffect(() => {
    const map=viewer.current
    if(!map || !drawing) return
    const handler=new Cesium.ScreenSpaceEventHandler(map.scene.canvas)
    let origin: import('cesium').Cartographic | null=null
    let bounds: import('cesium').Rectangle | null=null
    let shape: import('cesium').Entity | undefined
    const pick=(position:import('cesium').Cartesian2) => {
      const point=map.camera.pickEllipsoid(position,map.scene.globe.ellipsoid)
      return point ? Cesium.Cartographic.fromCartesian(point) : null
    }
    const stop=()=>{map.scene.screenSpaceCameraController.enableInputs=true;setDrawing(false)}
    handler.setInputAction((e:{position:import('cesium').Cartesian2})=>{
      origin=pick(e.position)
      if(!origin) return
      map.scene.screenSpaceCameraController.enableInputs=false
    },Cesium.ScreenSpaceEventType.LEFT_DOWN)
    handler.setInputAction((e:{endPosition:import('cesium').Cartesian2})=>{
      const end=pick(e.endPosition)
      if(!origin || !end) return
      bounds=Cesium.Rectangle.fromCartographicArray([origin,end])
      if(!shape) shape=map.entities.add({rectangle:{coordinates:new Cesium.CallbackProperty(()=>bounds,false),material:Cesium.Color.CYAN.withAlpha(.15),outline:true,outlineColor:Cesium.Color.CYAN,height:100}})
      map.scene.requestRender()
    },Cesium.ScreenSpaceEventType.MOUSE_MOVE)
    handler.setInputAction(()=>{
      if(bounds && bounds.width>0.000001 && bounds.height>0.000001) {
        const bbox=[bounds.west,bounds.south,bounds.east,bounds.north].map(Cesium.Math.toDegrees).join(',');setSearchArea(bbox);onAreaSelected?.(bbox);setSearchId(n=>n+1)
      }
      stop()
    },Cesium.ScreenSpaceEventType.LEFT_UP)
    const escape=(e:KeyboardEvent)=>{if(e.key==='Escape')stop()}
    window.addEventListener('keydown',escape)
    return ()=>{handler.destroy();window.removeEventListener('keydown',escape);if(!map.isDestroyed()){map.scene.screenSpaceCameraController.enableInputs=true;if(shape)map.entities.remove(shape);map.scene.requestRender()}}
  },[drawing, !!firms])
  return <div className="globe-shell"><section className="map" aria-label="Globo terrestre interactivo">
    {firms && detection && <aside className="cell-detail"><button onClick={() => setDetection(null)}>Cerrar</button><h3>Detección NASA FIRMS</h3><dl>{Object.entries(detection).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value ?? 'Desconocido')}</dd></div>)}</dl></aside>}
    <div ref={container} className="globe" />
    <div className="map-credits" ref={credits} aria-label="Créditos de los proveedores cartográficos" />
    <div className="map-actions">
      {!firms && <><label>Observaciones <select value={allH3?'all':'fire'} onChange={e=>setAllH3(e.target.value==='all')}><option value="fire">Detecciones con fuego</option><option value="all">Todas las observaciones H3</option></select></label><button disabled={!rows.length} onClick={()=>{const positions=rows.filter(r=>allH3 || ['AMBOS','SOLO_MODIS','SOLO_VIIRS'].includes(r.coincidencia_qa)).map(r=>{const [lat,lon]=cellToLatLng(r.celda_h3);return Cesium.Cartesian3.fromDegrees(lon,lat)});if(positions.length)viewer.current?.camera.flyTo({destination:Cesium.Rectangle.fromCartesianArray(positions)})}}>Ver observaciones</button></>}

      {firms && <><label>Vista <select aria-label="Representación FIRMS" value={displayMode} onChange={e=>setDisplayMode(e.target.value)}><option value="density">Densidad</option><option value="points">Detecciones individuales</option></select></label></>}
      {<><button aria-pressed={drawing} onClick={()=>setDrawing(v=>!v)}>{drawing?'Cancelar selección':'Seleccionar área'}</button>{searchArea && <button onClick={()=>{setSearchArea(null);onAreaSelected?.('');setSearchId(n=>n+1)}}>Limpiar área</button>}</>}
      <button onClick={() => viewer.current?.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(-102, 20, 17_000_000) })}>Vista mundial</button>
      {firms && <button onClick={() => { const r = viewer.current?.camera.computeViewRectangle(); if (r) { const bbox=[r.west,r.south,r.east,r.north].map(Cesium.Math.toDegrees).join(',');setSearchArea(bbox);onAreaSelected?.(bbox); setSearchId(n => n+1) } }}>Buscar en esta área</button>}

    </div>
    {error && <p className="map-error" role="status">{error}</p>}
    <div className="map-coordinate-display" aria-live="off">
      <span>COORDENADAS</span>
      <strong>{(pointerCoords ?? (focusPoint ? {lat:focusPoint.lat,lon:focusPoint.lon} : null))
        ? `Lat ${(pointerCoords?.lat ?? focusPoint!.lat).toFixed(5)}°  ·  Lon ${(pointerCoords?.lon ?? focusPoint!.lon).toFixed(5)}°`
        : 'Mueve el cursor sobre el mapa'}</strong>
      <small>{pointerCoords ? 'Posición del cursor · WGS84' : focusPoint ? `Centro de ${focusPoint.name} · WGS84` : 'Sistema WGS84'}</small>
    </div>
    <div className="legend">{firms ? 'FIRMS · amarillo–rojo: cantidad por celda, intensidad relativa. No representa área quemada ni temperatura.' : 'QA ? AMBOS rojo / SOLO_MODIS naranja / SOLO_VIIRS azul / NINGUNO verde / NO_EVALUABLE gris'}</div>
    {!firms && selected && <aside className="cell-detail" aria-label="Detalle de celda H3">
      <button onClick={() => setSelected(null)} aria-label="Cerrar detalle">Cerrar</button>
      <h3>{selected.celda_h3}</h3><p>Indicador del centro de una celda H3 agregada; no es una coordenada individual de incendio.</p>
      <p>{selected.region_nombre} / {selected.fecha} / {selected.version_armonizacion}</p>
      {rows.filter(row => row.celda_h3 === selected.celda_h3).map(row => <div key={row.id}>
        <p>MODIS {row.modis_sobrevuelo} / VIIRS {row.viirs_sobrevuelo}</p>
        <dl><dt>MODIS fuego original / útiles</dt><dd>{row.modis_fuego ?? 'Desconocido'} / {row.modis_utiles ?? 'Desconocido'}</dd>
        <dt>VIIRS fuego original / útiles</dt><dd>{row.viirs_fuego ?? 'Desconocido'} / {row.viirs_utiles ?? 'Desconocido'}</dd>
        <dt>VIIRS sin bow-tie / QA nominal</dt><dd>{row.viirs_fuego_sin_bowtie ?? 'Desconocido'} / {row.viirs_fuego_qa_nominal ?? 'Desconocido'}</dd>
        <dt>Bow-tie residual / geolocalización no nominal</dt><dd>{row.viirs_bowtie_residual ?? 'Desconocido'} / {row.viirs_geo_no_nominal ?? 'Desconocido'}</dd>
        <dt>Cobertura compartida estimada</dt><dd>{row.cobertura_compartida_pct ?? 'Desconocida'} %</dd>
        <dt>Diferencia temporal</dt><dd>{row.diferencia_min ?? 'Desconocida'} min / {row.estrato_temporal}</dd>
        <dt>Original / después de QA</dt><dd>{row.coincidencia_original} / {row.coincidencia_qa}</dd></dl>
      </div>)}
    </aside>}
  </section>{firms && <div className="firms-status" role="status">{firms.sensor.toUpperCase()} · {firms.start} — {firms.end} UTC · Área: {searchArea || focusPoint?.name || 'Mundo'} · {firmsStatus}</div>}</div>
}
