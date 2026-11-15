import { apiGet } from './data'
export type FirmsRow={id:number;latitude:number;longitude:number;observed_at:string;satellite:string;source:string;original:Record<string,unknown>;count?:number}
export type FirmsPage={status:string;count:number;results:FirmsRow[];next_offset?:number|null;mode?:string;cell_degrees?:number;missing_dates?:string[]}
export async function fetchFirmsComplete(params:URLSearchParams,signal:AbortSignal,onProgress:(count:number,total:number)=>void):Promise<FirmsPage>{
 const query=new URLSearchParams(params),requestSignal=AbortSignal.any([signal,AbortSignal.timeout(120000)])
 const result=await apiGet<FirmsPage>('/v1/detections/?'+query,requestSignal)
 const validate=(page:FirmsPage)=>{if(!['DATOS_DISPONIBLES','SIN_DETECCIONES'].includes(page.status))throw new Error(page.status.replaceAll('_',' '));if(page.missing_dates?.length)throw new Error('Consulta incompleta: faltan fechas '+page.missing_dates.join(', '))}
 validate(result);onProgress(result.results.length,result.count)
 if(result.mode==='aggregated')return result
 if(result.count>200000)throw new Error('Más de 200.000 detecciones: reduce el área o utiliza Densidad.')
 query.set('retrieve','false')
 while(result.next_offset!=null){
  if(signal.aborted)throw new DOMException('Consulta cancelada','AbortError')
  const offset=result.next_offset;query.set('offset',String(offset))
  const page=await apiGet<FirmsPage>('/v1/detections/?'+query,requestSignal);validate(page)
  if(!page.results.length||page.count!==result.count||(page.next_offset!=null&&page.next_offset<=offset))throw new Error('La colección cambió durante la consulta; vuelve a intentarlo.')
  result.results.push(...page.results);result.next_offset=page.next_offset;onProgress(result.results.length,result.count)
 }
 if(result.results.length!==result.count||new Set(result.results.map(r=>r.id)).size!==result.count)throw new Error('Respuesta incompleta o duplicada; vuelve a consultar.')
 return result
}
