import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet } from './data'

type Run={id:number;date:string;version:string;status:string;records:number;error_type:string;parameters:{pairs_total?:number;pairs_completed?:number;pixel_detections_completed?:number;pixel_product?:{output_detections:number}}}
export default function ScientificJobs({date,bbox,onResults,operational=false}:{date:string;bbox:string;operational?:boolean;onResults:(date:string,version:string)=>void}) {
  const [key,setKey]=useState(''), [message,setMessage]=useState(''), [busy,setBusy]=useState(false)
  const jobs=useQuery({queryKey:['scientific-jobs',operational],queryFn:({signal})=>apiGet<Run[]>(operational?'/v1/harmonized-detections/jobs/':'/v1/harmonization/runs/',signal).then(rows=>rows.map(r=>({...r,parameters:r.parameters??{}}))),refetchInterval:10000})
  async function submit() {
    setBusy(true)
    try {
      const base=(import.meta as ImportMeta & {env:Record<string,string>}).env.VITE_API_BASE_URL || '/api'
      const response=await fetch(base.replace(/\/$/,'')+(operational?'/v1/harmonized-detections/jobs/':'/v1/harmonization/jobs/'),{method:'POST',headers:{'Content-Type':'application/json','X-Scientific-Key':key},body:JSON.stringify(operational?{date}:{date,bbox,version:'l2_regional_v2',resolution:7})})
      const result=await response.json()
      if(!response.ok)throw new Error(JSON.stringify(result))
      setKey('');setMessage('Solicitud registrada. El worker científico ejecutará el trabajo fuera de HTTP.');void jobs.refetch()
    }catch(error){setMessage(error instanceof Error?error.message:'Error de solicitud')}finally{setBusy(false)}
  }
  return <section className="below-map" aria-label="Procesamiento científico">
    <details><summary>{operational?'Sincronizar e integrar un d\u00eda mundial FIRMS':'Procesar una nueva \u00e1rea Level 2'}</summary><p className="note">{operational?'El worker harmonize_firms --watch integrar\u00e1 ambos sensores para el d\u00eda UTC completo.':'Selecciona un rect\u00e1ngulo peque\u00f1o.'} Fecha UTC: {date}. Área: {operational ? 'Mundo' : bbox || 'No seleccionada'}. Requiere autorización administrativa; {operational ? 'producto operativo distinto de Level 2.' : 'no convierte puntos FIRMS en armonización Level 2.'}</p>
      <label>Clave administrativa <input type="password" value={key} onChange={e=>setKey(e.target.value)} autoComplete="off" /></label>
      <button disabled={busy || (!operational && !bbox) || !key} onClick={()=>void submit()}>{busy?'Registrando…':'Solicitar procesamiento'}</button>
    </details>
    {message && <p role="status">{message}</p>}
    {jobs.isError && <p role="alert">No fue posible consultar los trabajos científicos.</p>}
    {(jobs.data??[]).filter(r=>r.date===date).slice(0,8).map(run=><p key={run.id}>#{run.id} · {run.status} · {run.parameters.pairs_total!==undefined ? `${run.parameters.pairs_completed??0}/${run.parameters.pairs_total} parejas \u00b7 ` : ''}{operational ? `${run.records} resultados operativos` : <>{run.records} observaciones H3 / {run.parameters.pixel_detections_completed ?? run.parameters.pixel_product?.output_detections ?? 'sin producto'} detecciones unificadas</>} {!operational && run.status==='COMPLETADO' && <button onClick={()=>onResults(run.date,run.version)}>Ver resultados</button>}</p>)}
  </section>
}
