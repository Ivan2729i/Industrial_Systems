import { getResolution, isValidCell } from 'h3-js'

export const sensors = ['modis', 'viirs'] as const
export type Sensor = typeof sensors[number]
type Count = 'pixeles' | 'utiles' | 'fuego' | 'nubes'
const flags = ['observacion_util_ambos', 'supera_umbral_exploratorio', 'fuego_ambos', 'fuego_solo_modis', 'fuego_solo_viirs'] as const
export type Cell = Record<`${Sensor}_${Count}`, number | null> & Record<typeof flags[number], boolean> & {
  id: number; region_id: string; region_nombre: string; pair: number
  coincidencia_original: string; coincidencia_qa: string; estrato_temporal: string
  cobertura_compartida_pct: number | null; diferencia_min: number | null
  viirs_fuego_sin_bowtie: number | null; viirs_fuego_qa_total: number | null; viirs_fuego_qa_nominal: number | null
  viirs_bowtie_residual: number | null; viirs_geo_no_nominal: number | null
  qa_viirs_disponible: boolean | null; version_armonizacion: string
  fecha: string; celda_h3: string; resolucion_h3: number
  modis_sobrevuelo: string; viirs_sobrevuelo: string
  pais?: string; estado?: string; viirs_reflejo_solar?: number
}

export type Region = { id: string; name: string; west: number | null; south: number | null; east: number | null; north: number | null }
const base = (import.meta as ImportMeta & { env: Record<string, string> }).env.VITE_API_BASE_URL || '/api'
export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(base.replace(/\/$/, '') + path, { signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error('HTTP ' + response.status + ': ' + (body ? JSON.stringify(body) : response.statusText))
  }
  return response.json() as Promise<T>
}
export const fetchRegions = (signal: AbortSignal) => apiGet<Region[]>('/v1/regions/', signal)
export const fetchDates = (region: string, signal: AbortSignal) => apiGet<{ dates: string[] }>('/v1/dates/?' + new URLSearchParams({ region }), signal)

export const comparable = (cell: Cell) => cell.observacion_util_ambos && cell.supera_umbral_exploratorio

export function summarize(rows: Cell[], sensor: Sensor) {
  const pixels = rows.reduce((sum, row) => sum + (row[`${sensor}_pixeles`] ?? 0), 0)
  const useful = rows.reduce((sum, row) => sum + (row[`${sensor}_utiles`] ?? 0), 0)
  return {
    observed: new Set(rows.filter(row => (row[`${sensor}_pixeles`] ?? 0) > 0).map(row => row.celda_h3)).size,
    fire: rows.some(row => row[`${sensor}_fuego`] === null) ? null : rows.reduce((sum, row) => sum + (row[`${sensor}_fuego`] ?? 0), 0),
    usefulPct: pixels && rows.every(row => row[`${sensor}_pixeles`] !== null && row[`${sensor}_utiles`] !== null) ? useful / pixels * 100 : null,
  }
}

// Queries are scoped on the server. Follow every bounded page; never silently truncate.
export async function fetchCellsRange(start: string, end: string, region: string, signal: AbortSignal, version = 'v1_experimental', bbox = ''): Promise<Cell[]> {
  if (!start || !end || start > end) throw new Error('Selecciona región y fechas válidas.')
  const result: Cell[] = []
  let offset = 0
  while (true) {
    const params = new URLSearchParams({ ...(region ? {region} : {}), start, end, version, limit: '1000', offset: String(offset) })
    if(bbox) params.set('bbox',bbox)
    const page = await apiGet<{ count: number; next: string | null; results: Cell[] }>('/v1/observations/?' + params, signal)
    if (!Array.isArray(page.results) || !page.results.every(row => isValidCell(row.celda_h3) && getResolution(row.celda_h3) === row.resolucion_h3)) throw new Error('Respuesta H3 inválida.')
    result.push(...page.results)
    if (!page.next) return result
    if (!page.results.length) throw new Error('Paginación inválida.')
    offset += page.results.length
    if (offset > 20000) throw new Error('Demasiadas observaciones: reduce el rango de fechas.')
  }
}


export type HarmonizedPoint={id:string;latitude:number;longitude:number;observed_at:string;status:string;version:string;method:string;h3:string;modis_count:number;viirs_count:number;product?:string;represented_count?:number;assessment:Record<string,unknown>;members:{pixel:{id:string;sensor:string;platform:string;granule:string;source_file:string;h3_r7:string;row:number;column:number;latitude:number;longitude:number;observed_at:string;fire_class:number;qa:Record<string,unknown>}}[]}
export type OperationalPage={product:string;count:number;counts:Record<string,number>;results:HarmonizedPoint[];status:string;missing_dates:string[];mode:string;next_offset:number|null;jobs:{date:string;modis_count:number;viirs_count:number;records:number;updated_at:string}[]}
export async function fetchOperationalPoints(start:string,end:string,bbox:string,signal:AbortSignal):Promise<OperationalPage>{
  const params=new URLSearchParams({start,end,bbox:bbox || 'world',aggregate:String(!bbox),limit:'1000'})
  const result=await apiGet<OperationalPage>('/v1/harmonized-detections/?'+params,signal)
  while(result.next_offset!==null){
    if(result.results.length>=20000)throw new Error('Reduce el área para consultar las detecciones individuales completas.')
    params.set('offset',String(result.next_offset))
    const next=await apiGet<OperationalPage>('/v1/harmonized-detections/?'+params,signal)
    result.results.push(...next.results);result.next_offset=next.next_offset
  }
  return result
}
export async function fetchHarmonizedPoints(start:string,end:string,bbox:string,version:string,signal:AbortSignal):Promise<HarmonizedPoint[]> {
  const result:HarmonizedPoint[]=[]
  let offset=0
  while(true){
    const params=new URLSearchParams({start,end,limit:'1000',offset:String(offset)})
    if(bbox)params.set('bbox',bbox)
    if(version)params.set('version',version)
    const page=await apiGet<{count:number;next:string|null;results:HarmonizedPoint[]}>('/v1/harmonization/detections/?'+params,signal)
    result.push(...page.results)
    if(!page.next)return result
    if(!page.results.length || result.length>=20000)throw new Error('Reduce el área para cargar el producto armonizado completo.')
    offset=result.length
  }
}

export type PixelCatalog={dates:string[];versions:{version:string;count:number}[];processed_scopes:{date:string;bbox:number[];h3_source_version:string;positive_source_pixels:number;unified_detections:number}[];global_coverage_complete:boolean}
