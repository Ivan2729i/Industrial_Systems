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
  if (!response.ok) throw new Error('La API respondi? HTTP ' + response.status + '. Revisa Django y PostgreSQL.')
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
export async function fetchCellsRange(start: string, end: string, region: string, signal: AbortSignal, version = 'v1_experimental'): Promise<Cell[]> {
  if (!region || !start || !end || start > end) throw new Error('Selecciona regi?n y fechas v?lidas.')
  const result: Cell[] = []
  let offset = 0
  while (true) {
    const params = new URLSearchParams({ region, start, end, version, limit: '1000', offset: String(offset) })
    const page = await apiGet<{ count: number; next: string | null; results: Cell[] }>('/v1/observations/?' + params, signal)
    if (!Array.isArray(page.results) || !page.results.every(row => isValidCell(row.celda_h3) && getResolution(row.celda_h3) === row.resolucion_h3)) throw new Error('Respuesta H3 inv?lida.')
    result.push(...page.results)
    if (!page.next) return result
    if (!page.results.length) throw new Error('Paginaci?n inv?lida.')
    offset += page.results.length
    if (offset > 20000) throw new Error('Demasiadas observaciones: reduce el rango de fechas.')
  }
}
