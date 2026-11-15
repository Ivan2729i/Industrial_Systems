import { useEffect, useRef, useState } from 'react'
import type { PointPrimitiveCollection, Viewer } from 'cesium'
import { cellToLatLng } from 'h3-js'
import type { Cell, Sensor } from './data'
import type { Place } from './LocationSearch'
import 'cesium/Build/Cesium/Widgets/widgets.css'

declare global { interface Window { Cesium: typeof import('cesium') } }
const Cesium = window.Cesium

type Props = { rows: Cell[]; active: Sensor[]; focusPoint: Place | null }

export default function Globe({ rows, active, focusPoint }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const viewer = useRef<Viewer | null>(null)
  const points = useRef<PointPrimitiveCollection | null>(null)
  const credits = useRef<HTMLDivElement>(null)
  const [error, setError] = useState('')
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
      points.current = map.scene.primitives.add(new Cesium.PointPrimitiveCollection())
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
          const layer = map.imageryLayers.add(new Cesium.ImageryLayer(boundaries))
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
      return () => { handler.destroy(); points.current = null; viewer.current = null; map.destroy() }
    } catch {
      setError('El globo requiere un navegador con WebGL habilitado.')
    }
  }, [])
  useEffect(() => {
    if (!points.current || !viewer.current) return
    points.current.removeAll()
    const ids = new Set(rows.filter(row => active.some(sensor => row[`${sensor}_fuego`] > 0)).map(row => row.celda_h3))
    for (const id of ids) {
      const [latitude, longitude] = cellToLatLng(id)
      points.current.add({
        position: Cesium.Cartesian3.fromDegrees(longitude, latitude, 100),
        pixelSize: 8, color: Cesium.Color.fromCssColorString('#ff514c'), outlineColor: Cesium.Color.WHITE, outlineWidth: 1,
      })
    }
    viewer.current.scene.requestRender()
  }, [rows, active])
  useEffect(() => {
    if (!focusPoint || !viewer.current || viewer.current.isDestroyed()) return
    const height = focusPoint.kind === 'country' ? 2_200_000 : focusPoint.kind === 'state' ? 550_000 : 105_000
    viewer.current.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(focusPoint.lon, focusPoint.lat, height),
      duration: 1.7,
    })
  }, [focusPoint])
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
    <div className="legend"><i /> Celda H3 con detección</div>
  </section>
}
