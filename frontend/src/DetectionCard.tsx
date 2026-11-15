import { useEffect, useRef } from 'react'
import type { HarmonizedPoint } from './data'

export function confidenceLabel(sensor:string,value:unknown){
  if(value==null || value==='')return 'No informada'
  if(sensor.toUpperCase()==='MODIS'){
    const number=Number(value)
    return Number.isFinite(number)&&number>=0&&number<=100 ? `${number}% · escala MODIS` : String(value)
  }
  if(sensor.toUpperCase()==='VIIRS')return ({l:'Baja',n:'Nominal',h:'Alta'}[String(value).toLowerCase()] || String(value))+' · escala VIIRS'
  return String(value)
}
export default function DetectionCard({record,product,onClose}:{record?:Record<string,unknown>;product?:HarmonizedPoint;onClose:()=>void}){
  const close=useRef(onClose);close.current=onClose
  useEffect(()=>{const escape=(e:KeyboardEvent)=>{if(e.key==='Escape')close.current()};document.addEventListener('keydown',escape);return()=>document.removeEventListener('keydown',escape)},[])
  const representative=product?.members.find(({pixel})=>pixel.latitude===product.latitude&&pixel.longitude===product.longitude)?.pixel
  const data=record ?? (representative ? {...representative.qa,...representative,sensor:representative.sensor,source:representative.granule} : {})
  const sensor=String(data.sensor??'').toUpperCase(),stamp=String(product?.observed_at??data.observed_at??'')
  const date=new Date(stamp),valid=Number.isFinite(date.getTime())
  const latitude=Number(product?.latitude??data.latitude),longitude=Number(product?.longitude??data.longitude)
  const frp=data.frp==null || data.frp==='' ? NaN : Number(data.frp)
  const source=product ? product.product==='FIRMS_OPERATIONAL'?'NASA FIRMS · integración operativa':'NASA Earthdata · Level 2' : String(data.source??'NASA FIRMS')
  return <aside className="cell-detail detection-card" aria-label="Detalle de detección térmica">
    <div className="detection-heading"><h3>Detección térmica satelital</h3><button onClick={onClose} aria-label="Cerrar detalle de detección">Cerrar</button></div>
    <dl className="detection-facts">
      <div><dt>Sensor</dt><dd>{product?'Armonizado · MODIS–VIIRS':sensor || 'No informado'}</dd></div>
      <div><dt>Fecha de observación</dt><dd>{valid?date.toLocaleDateString('es-MX',{timeZone:'UTC',year:'numeric',month:'long',day:'numeric'}):'No informada'}</dd></div>
      <div><dt>Hora UTC</dt><dd>{valid?date.toISOString().slice(11,19)+' UTC':'No informada'}</dd></div>
      <div><dt>Ubicación</dt><dd>{Number.isFinite(latitude)&&Number.isFinite(longitude)?`${latitude.toFixed(5)}°, ${longitude.toFixed(5)}°`:'No informada'}</dd></div>
      <div><dt>Confianza{product?' de la observación representativa':''}</dt><dd>{confidenceLabel(sensor,data.confidence)}</dd></div>
      <div><dt>Potencia radiativa del fuego{product?' representativa':''}</dt><dd>{Number.isFinite(frp)&&frp>=0?new Intl.NumberFormat('es-MX',{maximumFractionDigits:2}).format(frp)+' MW':'No disponible'}</dd></div>
      <div><dt>Fuente de datos</dt><dd>{source}</dd></div>
    </dl>
    {product && <p className="detection-context">{({ASOCIADA:'Asociación entre sensores',SOLO_MODIS:'Exclusiva MODIS',SOLO_VIIRS:'Exclusiva VIIRS',SIN_COMPARABILIDAD:'Sin comparabilidad suficiente'} as Record<string,string>)[product.status]??product.status} · {product.modis_count} MODIS / {product.viirs_count} VIIRS{(product.represented_count??1)>1?` · ${product.represented_count} resultados en la agrupación`:''}</p>}
    <details><summary>Ver detalles técnicos</summary><pre>{JSON.stringify(product??record,null,2)}</pre></details>
  </aside>
}
