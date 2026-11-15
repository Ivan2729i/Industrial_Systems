import { useEffect, useRef, useState } from 'react'
import DetectionCard from './DetectionCard'
import { fetchFirmsComplete } from './firmsData'
import type { Viewer } from 'cesium'
import { cellToLatLng, cellToBoundary } from 'h3-js'
import { setLayerVisibility } from './layerVisibility'
import { densityImage } from './density'
import { apiGet, type Cell, type Sensor, type HarmonizedPoint } from './data'
import type { Place } from './LocationSearch'
import 'cesium/Build/Cesium/Widgets/widgets.css'

declare global { interface Window { Cesium: typeof import('cesium') } }
const Cesium = window.Cesium

type Props = { harmonizedReady?:boolean; onWorld?:()=>void; operational?:boolean; harmonized?:HarmonizedPoint[]; showH3?:boolean; onShowH3?:(value:boolean)=>void; onAreaSelected?: (bbox:string)=>void; rows: Cell[]; active: Sensor[]; focusPoint: Place | null; firms?: { start: string; end: string; sensor: Sensor; satellite: string; region: string; valid: boolean } }

export default function Globe({ rows, active, focusPoint, firms, onAreaSelected, harmonized=[], showH3=false, onShowH3, operational=false, onWorld, harmonizedReady=true }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const viewer = useRef<Viewer | null>(null)
  const densityLayers=useRef<Partial<Record<Sensor,import('cesium').ImageryLayer>>>({})
  const firmsLayers = useRef<Partial<Record<Sensor, import('cesium').CustomDataSource>>>({})
  const firmsPrimitives=useRef<Partial<Record<Sensor,import('cesium').PointPrimitiveCollection>>>({})
  const responseCache = useRef(new Map<string, {data:any;expires:number}>())
  const harmonicPoints=useRef<import('cesium').CustomDataSource | null>(null)
  const [selectedProduct,setSelectedProduct]=useState<HarmonizedPoint|null>(null)
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
        requestRenderMode: true,msaaSamples:4,contextOptions:{webgl:{antialias:true}},
        maximumRenderTimeChange: 60,
        creditContainer: credits.current!,
      })
      viewer.current = map
      map.useBrowserRecommendedResolution=false;map.resolutionScale=Math.min(1,2/(window.devicePixelRatio||1))
      const ellipsoidTerrain=new Cesium.EllipsoidTerrainProvider()
      let regionalTerrain:import('cesium').TerrainProvider|undefined
      const regionalImagery:import('cesium').ImageryLayer[]=[]
      const updateSurface=()=>{
        if(map.isDestroyed())return
        const regional=map.camera.positionCartographic.height<3_000_000 && Math.abs(Cesium.Math.toDegrees(map.camera.positionCartographic.latitude))<75
        let changed=false
        for(const layer of regionalImagery)if(layer.show!==regional){layer.show=regional;changed=true}
        const terrain=regional && regionalTerrain ? regionalTerrain : ellipsoidTerrain
        if(map.terrainProvider!==terrain){map.terrainProvider=terrain;changed=true}
        if(changed)map.scene.requestRender()
      }
      const stopSurfaceChanged=map.camera.changed.addEventListener(updateSurface)
      const stopSurfaceEnd=map.camera.moveEnd.addEventListener(updateSurface)
      const globalBase=new Cesium.WebMapServiceImageryProvider({url:'https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi',layers:'BlueMarble_ShadedRelief_Bathymetry',parameters:{format:'image/jpeg',transparent:false},tilingScheme:new Cesium.GeographicTilingScheme(),tileWidth:512,tileHeight:512,maximumLevel:8,credit:'NASA GIBS Blue Marble'})
      map.imageryLayers.add(new Cesium.ImageryLayer(globalBase))
      updateSurface()
      map.scene.globe.enableLighting=false
      map.scene.globe.dynamicAtmosphereLighting=false
      map.scene.globe.dynamicAtmosphereLightingFromSun=false
      map.scene.globe.showGroundAtmosphere=true
      map.scene.globe.depthTestAgainstTerrain=false
      map.scene.globe.maximumScreenSpaceError=1.5
      if(map.scene.skyAtmosphere)map.scene.skyAtmosphere.show=true
      if(map.scene.skyBox)map.scene.skyBox.show=false
      if(map.scene.skyAtmosphere){map.scene.skyAtmosphere.brightnessShift=-.15;map.scene.skyAtmosphere.saturationShift=-.1}
      // Cartographic daylight keeps both hemispheres legible; no artificial night mask.
      Cesium.TileMapServiceImageryProvider.fromUrl(Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII')).then(provider=>{if(!map.isDestroyed()){map.imageryLayers.add(new Cesium.ImageryLayer(provider),0);map.scene.requestRender()}}).catch(()=>{})
      if(map.scene.moon)map.scene.moon.show=false
      map.scene.backgroundColor=Cesium.Color.fromCssColorString('#02040a')
      Cesium.ArcGISTiledElevationTerrainProvider.fromUrl('https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer').then(terrain=>{if(!map.isDestroyed()){regionalTerrain=terrain;updateSurface();map.scene.requestRender()}}).catch(()=>{if(!map.isDestroyed())setError('El terreno 3D no está disponible; se conserva el globo elipsoidal.')})
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
        const detailLayer=new Cesium.ImageryLayer(provider);regionalImagery.push(detailLayer);map.imageryLayers.add(detailLayer);updateSurface()
        // Superponemos fronteras y divisiones administrativas en una capa transparente.
        Cesium.ArcGisMapServerImageryProvider.fromUrl(
          'https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer',
        ).then(boundaries => {
          if (map.isDestroyed()) return
          const layer = new Cesium.ImageryLayer(boundaries)
          map.imageryLayers.add(layer)
          layer.alpha = .95
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
      return () => { stopSurfaceChanged();stopSurfaceEnd();handler.destroy(); selection.current?.destroy(); selection.current = null; viewer.current = null; firmsLayers.current={}; densityLayers.current={}; h3Layer.current=null; harmonicPoints.current=null; map.destroy() }
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
    h3Layer.current.show=!firms && showH3
    if (firms || !showH3) {map.scene.requestRender(); return}
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
  }, [rows, active.join(','), allH3, !!firms, showH3])
  useEffect(()=>{
    const map=viewer.current
    if(!map)return
    if(!harmonicPoints.current){harmonicPoints.current=new Cesium.CustomDataSource('harmonized-Level2-points');void map.dataSources.add(harmonicPoints.current)}
    const layer=harmonicPoints.current
    layer.show=!firms && !showH3 && harmonizedReady
    setSelectedProduct(null)
    if(!layer.show){map.scene.requestRender();return}
    layer.entities.removeAll()
    const lookup=new Map<string,HarmonizedPoint>()
    for(const product of harmonized){lookup.set(product.id,product);layer.entities.add({id:'harmonized-'+product.id,position:Cesium.Cartesian3.fromDegrees(product.longitude,product.latitude,150),point:{pixelSize:7,color:Cesium.Color.RED,outlineColor:Cesium.Color.WHITE.withAlpha(.65),outlineWidth:1}})}
    const handler=new Cesium.ScreenSpaceEventHandler(map.scene.canvas)
    handler.setInputAction((e:{position:import('cesium').Cartesian2})=>{const id=map.scene.pick(e.position)?.id?.id;setSelectedProduct(typeof id==='string'?lookup.get(id.replace('harmonized-',''))??null:null)},Cesium.ScreenSpaceEventType.LEFT_CLICK)
    map.scene.requestRender()
    return()=>handler.destroy()
  },[harmonized,!!firms,showH3,harmonizedReady])
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
    for(const points of Object.values(firmsPrimitives.current))if(points)points.show=false
    for(const [sensor,layer] of Object.entries(densityLayers.current))if(layer)layer.show=!!firms && firms.sensor===sensor && displayMode==='density'
    setLayerVisibility({...firmsLayers.current,h3:h3Layer.current??undefined,harmonized:harmonicPoints.current??undefined},firms?firms.sensor:showH3?'h3':'harmonized')
    if(harmonicPoints.current && !firms && !showH3)harmonicPoints.current.show=harmonizedReady
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
      const request=cached && cached.expires>Date.now() ? Promise.resolve(cached.data) : fetchFirmsComplete(params,signal,(loaded,total)=>{if(!signal.aborted)setFirmsStatus(`Cargando ${loaded} / ${total} detecciones…`)})
      request.then(async page => {
        if (signal.aborted || map.isDestroyed()) return
        if (!page.status.includes('ERROR')) responseCache.current.set(cacheKey,{data:page,expires:Date.now()+120000})
        if(responseCache.current.size>12) responseCache.current.delete(responseCache.current.keys().next().value!)
        layer!.show=true
        layer!.entities.removeAll()
        if (density) {
          const raster=densityImage(page.results,page.cell_degrees??1,bbox)
          const provider=await Cesium.SingleTileImageryProvider.fromUrl(raster.image,{rectangle:Cesium.Rectangle.fromDegrees(...raster.rectangle)})
          if(signal.aborted || map.isDestroyed())return
          const previous=densityLayers.current[firms.sensor]
          if(previous)map.imageryLayers.remove(previous,true)
          const overlay=new Cesium.ImageryLayer(provider);overlay.alpha=.85
          densityLayers.current[firms.sensor]=overlay;map.imageryLayers.add(overlay)
        }
        if(!density){
          const points=new Cesium.PointPrimitiveCollection()
          for(const row of page.results)points.add({position:Cesium.Cartesian3.fromDegrees(row.longitude,row.latitude,150),pixelSize:5,color:Cesium.Color.RED,outlineColor:Cesium.Color.WHITE,outlineWidth:1,id:{kind:'firms',attributes:{...row.original,id:row.id,sensor:firms.sensor,satellite:row.satellite,source:row.source,observed_at:row.observed_at,latitude:row.latitude,longitude:row.longitude}}})
          const previous=firmsPrimitives.current[firms.sensor];firmsPrimitives.current[firms.sensor]=points;map.scene.primitives.add(points);if(previous)map.scene.primitives.remove(previous)
        }

        setFirmsStatus(page.status.replaceAll('_',' ') + ' / ' + page.results.length + (page.mode === 'aggregated' ? ' grupos / ' : ' puntos / ') + page.count + ' detecciones')
        map.scene.requestRender()
      }).catch(e => { if (e.name !== 'AbortError') setFirmsStatus('Error consultando FIRMS: ' + e.message) })
    }
    const handler = new Cesium.ScreenSpaceEventHandler(map.scene.canvas)
    handler.setInputAction((event: { position: import('cesium').Cartesian2 }) => {
      const picked=map.scene.pick(event.position);setDetection(picked?.id?.kind==='firms'?picked.id.attributes:null)
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK)
    load()
    return () => { controller?.abort(); handler.destroy(); /* Layers persist across tabs; Viewer owns their destruction. */ }
  }, [firms?.start, firms?.end, firms?.sensor, firms?.satellite, firms?.region, focusPoint, searchArea, searchId, displayMode, firms?.valid, showH3,harmonizedReady])
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
      if(!shape) shape=map.entities.add({rectangle:{height:0,coordinates:new Cesium.CallbackProperty(()=>bounds,false),material:Cesium.Color.CYAN.withAlpha(.15),outline:true,outlineColor:Cesium.Color.CYAN}})
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
    {firms && detection && <DetectionCard record={detection} onClose={()=>setDetection(null)}/>}
    {!firms && !showH3 && selectedProduct && <DetectionCard product={selectedProduct} onClose={()=>setSelectedProduct(null)}/>}
    <div ref={container} className="globe" />
    <div className="map-credits" ref={credits} aria-label="Créditos de los proveedores cartográficos" />
    <div className="map-actions">
      {!firms && <label>Visualización <select value={showH3?'h3':'points'} onChange={e=>onShowH3?.(e.target.value==='h3')}><option value="points">Detecciones armonizadas</option><option value="h3">Análisis H3</option></select></label>}
      {!firms && showH3 && <><label>Observaciones <select value={allH3?'all':'fire'} onChange={e=>setAllH3(e.target.value==='all')}><option value="fire">Detecciones con fuego</option><option value="all">Todas las observaciones H3</option></select></label><button disabled={!rows.length} onClick={()=>{const positions=rows.filter(r=>allH3 || ['AMBOS','SOLO_MODIS','SOLO_VIIRS'].includes(r.coincidencia_qa)).map(r=>{const [lat,lon]=cellToLatLng(r.celda_h3);return Cesium.Cartesian3.fromDegrees(lon,lat)});if(positions.length)viewer.current?.camera.flyTo({destination:Cesium.Rectangle.fromCartesianArray(positions)})}}>Ver observaciones</button></>}

      {firms && <><label>Vista <select aria-label="Representación FIRMS" value={displayMode} onChange={e=>setDisplayMode(e.target.value)}><option value="density">Densidad</option><option value="points">Detecciones individuales</option></select></label></>}
      {<><button aria-pressed={drawing} onClick={()=>setDrawing(v=>!v)}>{drawing?'Cancelar selección':'Seleccionar área'}</button>{searchArea && <button onClick={()=>{setSearchArea(null);onAreaSelected?.('');setSearchId(n=>n+1)}}>Limpiar área</button>}</>}
      <button onClick={() => {setSearchArea(null);onWorld?.();viewer.current?.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(-102, 20, 17_000_000) })}}>Vista mundial</button>
      {<button onClick={() => { const r = viewer.current?.camera.computeViewRectangle(); if (r) { const bbox=[r.west,r.south,r.east,r.north].map(Cesium.Math.toDegrees).join(',');setSearchArea(bbox);onAreaSelected?.(bbox); setSearchId(n => n+1) } }}>Buscar en esta área</button>}

    </div>

    <div className="map-coordinate-display" aria-live="off">
      <span>COORDENADAS</span>
      <strong>{(pointerCoords ?? (focusPoint ? {lat:focusPoint.lat,lon:focusPoint.lon} : null))
        ? `Lat ${(pointerCoords?.lat ?? focusPoint!.lat).toFixed(5)}°  ·  Lon ${(pointerCoords?.lon ?? focusPoint!.lon).toFixed(5)}°`
        : 'Mueve el cursor sobre el mapa'}</strong>
      <small>{pointerCoords ? 'Posición del cursor · WGS84' : focusPoint ? `Centro de ${focusPoint.name} · WGS84` : 'Sistema WGS84'}</small>
    </div>

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
  </section>    {!(operational && !firms && !showH3) && <div className="map-legend">{firms ? displayMode==='density' ? 'FIRMS · amarillo–rojo: cantidad por celda, intensidad relativa. No representa área quemada ni temperatura.' : 'Detecciones térmicas FIRMS individuales; consulta atributos al seleccionar.' : !showH3 ? 'Rojo: producto Level 2 unificado, con asociaciones y detecciones exclusivas. Procedencia al seleccionar.' : 'QA · AMBOS rojo / SOLO_MODIS naranja / SOLO_VIIRS azul / NINGUNO verde / NO_EVALUABLE gris'}</div>}{error && <p className="firms-status" role="status">{error}</p>}{firms && <div className="firms-status" role="status">{firms.sensor.toUpperCase()} · {firms.start} — {firms.end} UTC · Área: {searchArea || focusPoint?.name || 'Mundo'} · {firmsStatus}</div>}</div>
}
