import { apiGet } from './data'
export type FirmsRow={id:number;latitude:number;longitude:number;observed_at:string;satellite:string;source:string;original:Record<string,unknown>;count?:number}
export type FirmsPage={revision?:string;status:string;count:number;results:FirmsRow[];next_offset?:number|null;mode?:string;cell_degrees?:number;missing_dates?:string[]}
export async function fetchFirmsComplete(params:URLSearchParams,signal:AbortSignal,onProgress:(count:number,total:number)=>void):Promise<FirmsPage>{
 const query=new URLSearchParams(params);query.set('compact','true');const requestSignal=AbortSignal.any([signal,AbortSignal.timeout(120000)])
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
  if(!page.results.length||page.count!==result.count||page.revision!==result.revision||(page.next_offset!=null&&page.next_offset<=offset))throw new Error('La colección cambió durante la consulta; vuelve a intentarlo.')
  result.results.push(...page.results);result.next_offset=page.next_offset;onProgress(result.results.length,result.count)
 }
 if(result.results.length!==result.count||new Set(result.results.map(r=>r.id)).size!==result.count)throw new Error('Respuesta incompleta o duplicada; vuelve a consultar.')
 return result
}

const daysCache=new Map<string,{page:FirmsPage;expires:number}>()
export type DayProgress={done:number;days:number;count:number;missing:string[];errors:Record<string,string>}
export async function fetchFirmsDays(params:URLSearchParams,signal:AbortSignal,publish:(day:string,key:string,page:FirmsPage,progress:DayProgress)=>void,notify:(p:DayProgress)=>void){
 const days:string[]=[];for(let t=Date.parse(params.get('start_date')+'T00:00:00Z');t<=Date.parse(params.get('end_date')+'T00:00:00Z');t+=86400000)days.push(new Date(t).toISOString().slice(0,10))
 const done=new Set<string>(),counts=new Map<string,number>(),errors:Record<string,string>={}
 const progress=():DayProgress=>({done:done.size,days:days.length,count:Array.from(counts.values()).reduce((a,b)=>a+b,0),missing:days.filter(d=>!done.has(d)),errors:{...errors}})
 const queue:{day:string;key:string;q:URLSearchParams}[]=[]
 for(const day of days){
  const q=new URLSearchParams(params);q.set('start_date',day);q.set('end_date',day);q.set('compact','true')
  const key=JSON.stringify(['FIRMS','SP_PREFERRED',...Array.from(q.entries()).sort()]),cached=daysCache.get(key)
  if(cached&&cached.expires>Date.now()){done.add(day);counts.set(day,cached.page.count);publish(day,key,cached.page,progress())}else queue.push({day,key,q})
 }
 // A fully stored regional range is cheaper as one compact query than 15 HTTP round trips.
 if(queue.length>=3 && params.get('bbox')!=='world' && params.get('aggregate')!=='true'){
  const bulk=new URLSearchParams(params);bulk.set('retrieve','false')
  try{
   const page=await fetchFirmsComplete(bulk,signal,()=>{})
   for(const item of [...queue]){
    if(signal.aborted)throw new DOMException('Cancelada','AbortError')
    const results=page.results.filter(r=>r.observed_at.slice(0,10)===item.day)
    const dayPage:FirmsPage={...page,results,count:results.length,next_offset:null}
    daysCache.set(item.key,{page:dayPage,expires:Date.now()+(results.some(r=>r.source?.endsWith('_NRT'))?60000:21600000)})
    done.add(item.day);counts.set(item.day,results.length);publish(item.day,item.key,dayPage,progress())
   }
   queue.splice(0,queue.length,...queue.filter(item=>!done.has(item.day)))
  }catch(error){if(signal.aborted)throw error}
 }
 let cursor=0
 await Promise.all(Array.from({length:2},async()=>{while(cursor<queue.length&&!signal.aborted){const {day,key,q}=queue[cursor++];try{
  // Read PostgreSQL first. Only this missing day can trigger NASA retrieval.
  q.set('retrieve','false');let page:FirmsPage
  for(let attempt=0;;attempt++){
   try{page=await fetchFirmsComplete(q,signal,()=>{});break}
   catch(error){
    if(signal.aborted)throw error
    if(q.get('retrieve')==='false'){q.set('retrieve','true');continue}
    if(!(error instanceof Error)||!error.message.includes('EN CURSO')||attempt>=30)throw error
    await new Promise<void>((resolve,reject)=>{const cancel=()=>{clearTimeout(timer);reject(new DOMException('Cancelada','AbortError'))};const timer=setTimeout(()=>{signal.removeEventListener('abort',cancel);resolve()},1000);signal.addEventListener('abort',cancel,{once:true})})
   }
  }
  if(signal.aborted)return
  daysCache.set(key,{page,expires:Date.now()+((!page.results.length||page.results.some(r=>r.source?.endsWith('_NRT')))?60000:21600000)})
  if(daysCache.size>64)daysCache.delete(daysCache.keys().next().value!)
  done.add(day);counts.set(day,page.count);publish(day,key,page,progress())
 }catch(error){if(!signal.aborted)errors[day]=error instanceof Error?error.message:'Error de consulta'}notify(progress())}}))
 if(signal.aborted)throw new DOMException('Cancelada','AbortError')
 notify(progress());return progress()
}
