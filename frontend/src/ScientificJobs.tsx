import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet } from './data'

type Run={id:number;date:string;version:string;status:string;records:number;error_type:string;parameters:{pairs_total?:number;pairs_completed?:number}}
export default function ScientificJobs({date,bbox,onResults}:{date:string;bbox:string;onResults:(date:string,version:string)=>void}) {
  const [key,setKey]=useState(''), [message,setMessage]=useState(''), [busy,setBusy]=useState(false)
  const jobs=useQuery({queryKey:['scientific-jobs'],queryFn:({signal})=>apiGet<Run[]>('/v1/harmonization/runs/',signal),refetchInterval:10000})
  async function submit() {
    setBusy(true)
    try {
      const base=(import.meta as ImportMeta & {env:Record<string,string>}).env.VITE_API_BASE_URL || '/api'
      const response=await fetch(base.replace(/\/$/,'')+'/v1/harmonization/jobs/',{method:'POST',headers:{'Content-Type':'application/json','X-Scientific-Key':key},body:JSON.stringify({date,bbox,version:'l2_regional_v2',resolution:7})})
      const result=await response.json()
      if(!response.ok)throw new Error(JSON.stringify(result))
      setKey('');setMessage('Solicitud registrada. El worker científico ejecutará el trabajo fuera de HTTP.');void jobs.refetch()
    }catch(error){setMessage(error instanceof Error?error.message:'Error de solicitud')}finally{setBusy(false)}
  }
  return <section className="below-map" aria-label="Procesamiento científico">
    <details><summary>Procesar una nueva área Level 2</summary><p className="note">Selecciona un rectángulo pequeño. Fecha UTC: {date}. Área: {bbox || 'No seleccionada'}. Requiere autorización administrativa; no convierte puntos FIRMS en armonización.</p>
      <label>Clave administrativa <input type="password" value={key} onChange={e=>setKey(e.target.value)} autoComplete="off" /></label>
      <button disabled={busy || !bbox || !key} onClick={()=>void submit()}>{busy?'Registrando…':'Solicitar procesamiento'}</button>
    </details>
    {message && <p role="status">{message}</p>}
    {jobs.isError && <p role="alert">No fue posible consultar los trabajos científicos.</p>}
    {(jobs.data??[]).filter(r=>r.date===date).slice(0,8).map(run=><p key={run.id}>#{run.id} · {run.status} · {run.parameters.pairs_completed??0}/{run.parameters.pairs_total??'?'} parejas · {run.records} observaciones {run.status==='COMPLETADO' && <button onClick={()=>onResults(run.date,run.version)}>Ver resultados</button>}</p>)}
  </section>
}
