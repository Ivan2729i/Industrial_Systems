import { getResolution, isValidCell } from 'h3-js'

export const sensors = ['modis', 'viirs'] as const
export type Sensor = typeof sensors[number]
type Count = 'pixeles' | 'utiles' | 'fuego' | 'nubes'
const flags = ['observacion_util_ambos', 'supera_umbral_exploratorio', 'fuego_ambos', 'fuego_solo_modis', 'fuego_solo_viirs'] as const
export type Cell = Record<`${Sensor}_${Count}`, number> & Record<typeof flags[number], boolean> & {
  fecha: string; celda_h3: string; resolucion_h3: number
  modis_sobrevuelo: string; viirs_sobrevuelo: string
  pais?: string; estado?: string; viirs_reflejo_solar?: number
}

function validCell(value: unknown, date: string): value is Cell {
  if (!value || typeof value !== 'object') return false
  const row = value as Cell
  return row.fecha === date && typeof row.celda_h3 === 'string' &&
    isValidCell(row.celda_h3) && getResolution(row.celda_h3) === 7 && row.resolucion_h3 === 7 &&
    sensors.every(sensor => typeof row[`${sensor}_sobrevuelo`] === 'string' &&
      (['pixeles', 'utiles', 'fuego', 'nubes'] as const).every(key => {
        const count = row[`${sensor}_${key}`]
        return Number.isSafeInteger(count) && count >= 0 && count <= row[`${sensor}_pixeles`]
      })) && flags.every(flag => typeof row[flag] === 'boolean') &&
    [row.pais, row.estado].every(field => field === undefined || typeof field === 'string')
}

export async function fetchCells(date: string, signal: AbortSignal): Promise<Cell[] | null> {
  const response = await fetch('/api/cells/?' + new URLSearchParams({ date }), { signal })
  if (response.status === 404) return null
  if (!response.ok) throw new Error('La consulta falló (HTTP ' + response.status + '). Verifica el servidor Django.')
  const body = await response.json()
  if (body.date !== date || !Array.isArray(body.data) || body.total !== body.data.length ||
      !body.data.every((row: unknown) => validCell(row, date))) {
    throw new Error('La API devolvió un lote con campos inválidos o incompletos.')
  }
  return body.data
}

export const comparable = (cell: Cell) => cell.observacion_util_ambos && cell.supera_umbral_exploratorio

export function summarize(rows: Cell[], sensor: Sensor) {
  const pixels = rows.reduce((sum, row) => sum + row[`${sensor}_pixeles`], 0)
  const useful = rows.reduce((sum, row) => sum + row[`${sensor}_utiles`], 0)
  return {
    observed: new Set(rows.filter(row => row[`${sensor}_pixeles`] > 0).map(row => row.celda_h3)).size,
    fire: rows.reduce((sum, row) => sum + row[`${sensor}_fuego`], 0),
    usefulPct: pixels ? useful / pixels * 100 : null,
  }
}

// El backend actual recibe una sola fecha en /api/cells/?date=AAAA-MM-DD.
// Para un rango consultamos cada día sin alterar el contrato existente.
// Se agrupan hasta cuatro solicitudes simultáneas para reducir carga al servidor.
export async function fetchCellsRange(start: string, end: string, signal: AbortSignal): Promise<Cell[] | null> {
  const first = Date.parse(start + 'T00:00:00Z')
  const last = Date.parse(end + 'T00:00:00Z')
  if (!Number.isFinite(first) || !Number.isFinite(last) || first > last || last - first >= 31 * 86400000) {
    throw new Error('El rango de fechas no es válido (máximo 31 días).')
  }
  const dates: string[] = []
  for (let ms = first; ms <= last; ms += 86400000) dates.push(new Date(ms).toISOString().slice(0, 10))
  const result: Cell[] = []
  let found = false
  for (let offset = 0; offset < dates.length; offset += 4) {
    const batches = await Promise.all(dates.slice(offset, offset + 4).map(date => fetchCells(date, signal)))
    for (const batch of batches) {
      if (batch !== null) { found = true; result.push(...batch) }
    }
  }
  return found ? result : null
}
