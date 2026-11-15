import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { apiGet, type PixelCatalog } from './data'
import './Analytics.css'

type AnalyticsProps = {
  onBack: () => void
}

type SensorFilter = 'all' | 'modis' | 'viirs'
type ProductFilter = 'operational' | 'level2'
type ExportDataset = 'modis' | 'viirs' | 'harmonized'

type Availability = {
  min_date: string
  max_date: string
}

type AnalyticsSummary = {
  start_date: string
  end_date: string
  product: ProductFilter
  version: string | null
  modis: number
  viirs: number
  harmonized: number
  associated: number
  coverage_verified: boolean
  note: string
}

type TimelineResponse = {
  start_date: string
  end_date: string
  product: ProductFilter
  coverage_verified: boolean
  note: string
  results: {
    date: string
    modis: number | null
    viirs: number | null
    harmonized: number | null
  }[]
}

const MAX_RANGE_DAYS = 31
const formatNumber = (value: number) => value.toLocaleString('es-MX')
const utcDay = (value: string) => Date.parse(`${value}T00:00:00Z`)

export default function Analytics({ onBack }: AnalyticsProps) {
  const [sensor, setSensor] = useState<SensorFilter>('all')
  const [product, setProduct] = useState<ProductFilter>('operational')
  const [exportDataset, setExportDataset] = useState<ExportDataset>('modis')
  const [version, setVersion] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const todayUTC = new Date().toISOString().slice(0, 10)

  const modisQuery = useQuery({
    queryKey: ['analytics-availability', 'modis'],
    queryFn: ({ signal }) =>
      apiGet<Availability>('/v1/detections/availability/?sensor=modis', signal),
    staleTime: 60 * 60 * 1000,
    retry: false,
  })

  const viirsQuery = useQuery({
    queryKey: ['analytics-availability', 'viirs'],
    queryFn: ({ signal }) =>
      apiGet<Availability>('/v1/detections/availability/?sensor=viirs', signal),
    staleTime: 60 * 60 * 1000,
    retry: false,
  })

  const availabilityError =
    sensor === 'modis'
      ? modisQuery.isError
      : sensor === 'viirs'
        ? viirsQuery.isError
        : modisQuery.isError || viirsQuery.isError

  const dateBounds = useMemo(() => {
    const sources =
      sensor === 'modis'
        ? [modisQuery.data]
        : sensor === 'viirs'
          ? [viirsQuery.data]
          : [modisQuery.data, viirsQuery.data]

    if (sources.some(source => !source?.min_date || !source?.max_date)) {
      return null
    }

    const available = sources as Availability[]
    const min = available.map(source => source.min_date).sort()[0]
    const latest = available.map(source => source.max_date).sort().at(-1)!
    const max = latest < todayUTC ? latest : todayUTC

    return min <= max ? { min, max } : null
  }, [sensor, modisQuery.data, viirsQuery.data, todayUTC])

  useEffect(() => {
    if (!dateBounds) return

    const clamp = (value: string) => {
      if (!value) return dateBounds.max
      if (value < dateBounds.min) return dateBounds.min
      if (value > dateBounds.max) return dateBounds.max
      return value
    }

    setStartDate(previous => clamp(previous))
    setEndDate(previous => clamp(previous))
  }, [dateBounds])

  const rangeDays =
    startDate && endDate
      ? (utcDay(endDate) - utcDay(startDate)) / 86_400_000 + 1
      : 0

  const validRange = Boolean(
    dateBounds &&
      startDate &&
      endDate &&
      startDate >= dateBounds.min &&
      endDate <= dateBounds.max &&
      startDate <= endDate &&
      rangeDays <= MAX_RANGE_DAYS
  )

  const changeStartDate = (value: string) => {
    if (!dateBounds) return
    if (value && (value < dateBounds.min || value > dateBounds.max)) return

    setStartDate(value)
    if (value && endDate && value > endDate) setEndDate(value)
  }

  const changeEndDate = (value: string) => {
    if (!dateBounds) return
    if (value && (value < dateBounds.min || value > dateBounds.max)) return

    setEndDate(value)
    if (value && startDate && value < startDate) setStartDate(value)
  }

  const catalogQuery = useQuery({
    queryKey: ['analytics-level2-catalog'],
    queryFn: ({ signal }) =>
      apiGet<PixelCatalog>('/v1/harmonization/detections/catalog/', signal),
    enabled: product === 'level2',
    staleTime: 60_000,
    retry: false,
  })

  const params = useMemo(() => {
    const value = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
      product,
    })
    if (product === 'level2' && version) value.set('version', version)
    return value.toString()
  }, [startDate, endDate, product, version])

  const summaryQuery = useQuery({
    queryKey: ['analytics-summary', params],
    queryFn: ({ signal }) =>
      apiGet<AnalyticsSummary>(`/v1/analytics/summary/?${params}`, signal),
    enabled: validRange,
    staleTime: 60_000,
    retry: false,
  })

  const timelineQuery = useQuery({
    queryKey: ['analytics-timeline', params],
    queryFn: ({ signal }) =>
      apiGet<TimelineResponse>(`/v1/analytics/timeline/?${params}`, signal),
    enabled: validRange,
    staleTime: 60_000,
    retry: false,
  })

  const summary = validRange ? summaryQuery.data : undefined
  const timeline = validRange ? timelineQuery.data : undefined

  const stats = summary
    ? [
        {
          key: 'modis',
          title: 'Detecciones MODIS',
          value: summary.modis,
          description: 'Registros originales FIRMS',
        },
        {
          key: 'viirs',
          title: 'Detecciones VIIRS',
          value: summary.viirs,
          description: 'Registros originales FIRMS',
        },
        {
          key: 'harmonized',
          title: 'Resultados armonizados',
          value: summary.harmonized,
          description:
            product === 'operational'
              ? 'Integración operativa FIRMS'
              : 'Armonización científica Level 2',
        },
        {
          key: 'associated',
          title: 'Asociaciones MODIS–VIIRS',
          value: summary.associated,
          description: 'Resultados asociados entre sensores',
        },
      ].filter(item =>
        (sensor !== 'modis' || item.key !== 'viirs') &&
        (sensor !== 'viirs' || item.key !== 'modis')
      )
    : []

  const comparisonData = summary
    ? [
        { name: 'MODIS', registros: summary.modis, color: '#ffad75' },
        { name: 'VIIRS', registros: summary.viirs, color: '#7ed8ff' },
        { name: 'Armonización', registros: summary.harmonized, color: '#ff514c' },
      ].filter(item =>
        sensor === 'all' ||
        item.name === 'Armonización' ||
        item.name.toLowerCase() === sensor
      )
    : []

  const exportParams = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    dataset: exportDataset,
  })
  if (exportDataset === 'harmonized') {
    exportParams.set('product', product)
    if (product === 'level2' && version) exportParams.set('version', version)
  }


  const localBackend = ['localhost', '127.0.0.1'].includes(
    window.location.hostname
  )

  const exportApiBase = localBackend
    ? `http://${window.location.hostname}:8000/api`
    : '/api'
  const exportUrl = `${exportApiBase}/v1/analytics/export/?${exportParams}`

  return (
    <main className="analytics-page">
      <header className="analytics-header">
        <div>
          <p className="analytics-eyebrow">TERRAFLARE / ANALÍTICA</p>
          <h1>Analítica satelital</h1>
          <p>
            Explora y compara las observaciones MODIS, VIIRS y los resultados
            armonizados.
          </p>
        </div>
        <button type="button" className="analytics-back" onClick={onBack}>
          Volver al mapa
        </button>
      </header>

      <section className="analytics-panel">
        <h2>Período de análisis</h2>
        <div className="analytics-filters">
          <label>
            Sensor
            <select
              value={sensor}
              onChange={event => setSensor(event.target.value as SensorFilter)}
            >
              <option value="all">MODIS y VIIRS</option>
              <option value="modis">MODIS</option>
              <option value="viirs">VIIRS</option>
            </select>
          </label>

          <label>
            Producto armonizado
            <select
              value={product}
              onChange={event => {
                setProduct(event.target.value as ProductFilter)
                setVersion('')
              }}
            >
              <option value="operational">Integración mundial FIRMS</option>
              <option value="level2">Armonización científica Level 2</option>
            </select>
          </label>

          {product === 'level2' && (
            <label>
              Versión científica
              <select
                value={version}
                onChange={event => setVersion(event.target.value)}
              >
                <option value="">Todas las versiones</option>
                {catalogQuery.data?.versions.map(item => (
                  <option key={item.version} value={item.version}>
                    {item.version}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label>
            Desde (UTC)
            <input
              type="date"
              value={startDate}
              min={dateBounds?.min}
              max={dateBounds?.max}
              disabled={!dateBounds}
              onChange={event => changeStartDate(event.target.value)}
            />
          </label>

          <label>
            Hasta (UTC)
            <input
              type="date"
              value={endDate}
              min={dateBounds?.min}
              max={dateBounds?.max}
              disabled={!dateBounds}
              onChange={event => changeEndDate(event.target.value)}
            />
          </label>
        </div>

        {availabilityError ? (
          <p className="analytics-note" role="alert">
            No se pudo consultar la disponibilidad NASA. Comprueba Django.
          </p>
        ) : !dateBounds ? (
          <p className="analytics-note">Consultando fechas disponibles...</p>
        ) : (
          <>
            <p className="analytics-note">
              Disponibilidad NASA: {dateBounds.min} al {dateBounds.max} UTC.
            </p>
            <p className="analytics-note">
              Período seleccionado: {startDate || '—'} al {endDate || '—'} UTC.
            </p>
            {rangeDays > MAX_RANGE_DAYS && (
              <p className="analytics-note" role="alert">
                El intervalo máximo es de {MAX_RANGE_DAYS} días.
              </p>
            )}
            {startDate > endDate && (
              <p className="analytics-note" role="alert">
                La fecha inicial no puede ser posterior a la final.
              </p>
            )}
            {sensor === 'all' && (
              <p className="analytics-note">
                MODIS y VIIRS tienen diferentes períodos históricos de
                disponibilidad; algunas fechas pueden contener un solo sensor.
              </p>
            )}
            {sensor !== 'all' && (
              <p className="analytics-note">
                El sensor seleccionado limita los indicadores originales
                visibles. La armonización sigue representando ambos sensores.
              </p>
            )}
            {product === 'level2' && !version && (
              <p className="analytics-note">
                Todas las versiones Level 2 pueden incluir reprocesamientos
                repetidos. Selecciona una versión para comparaciones precisas.
              </p>
            )}
            {product === 'level2' && catalogQuery.isError && (
              <p className="analytics-note" role="alert">
                No se pudo cargar el catálogo de versiones científicas.
              </p>
            )}
          </>
        )}
      </section>

      <section className="analytics-panel">
        <h2>Resumen de observaciones</h2>
        <p className="analytics-note">
          {product === 'operational'
            ? 'Datos originales e integración operativa NASA FIRMS.'
            : 'Datos originales y armonización científica Level 2.'}
        </p>

        {!validRange && (
          <div className="analytics-empty">
            Selecciona un período válido de hasta 31 días.
          </div>
        )}
        {validRange && summaryQuery.isPending && (
          <div className="analytics-empty" role="status">
            Consultando estadísticas de PostgreSQL...
          </div>
        )}
        {validRange && summaryQuery.isError && (
          <div className="analytics-error" role="alert">
            <p>No se pudieron obtener las estadísticas.</p>
            <button type="button" onClick={() => void summaryQuery.refetch()}>
              Reintentar
            </button>
          </div>
        )}
        {summary && (
          <>
            <div className="analytics-summary-grid">
              {stats.map(item => (
                <article className="analytics-stat-card" key={item.key}>
                  <span>{item.title}</span>
                  <strong>{formatNumber(item.value)}</strong>
                  <small>{item.description}</small>
                </article>
              ))}
            </div>
            {summaryQuery.isFetching && (
              <p className="analytics-note" role="status">
                Actualizando estadísticas...
              </p>
            )}
            <p className="analytics-note">{summary.note}</p>
            {!summary.coverage_verified && (
              <p className="analytics-note">
                Los valores corresponden a registros almacenados en PostgreSQL.
                No garantizan cobertura completa del período.
              </p>
            )}
          </>
        )}
      </section>

      <section className="analytics-panel">
        <h2>Evolución temporal</h2>
        <p className="analytics-note">
          Detecciones originales y resultados armonizados por día UTC.
        </p>
        {!validRange && (
          <div className="analytics-empty">Selecciona un período válido.</div>
        )}
        {validRange && timelineQuery.isPending && (
          <div className="analytics-empty" role="status">
            Cargando evolución temporal...
          </div>
        )}
        {validRange && timelineQuery.isError && (
          <div className="analytics-error" role="alert">
            <p>No se pudieron cargar los datos temporales.</p>
            <button type="button" onClick={() => void timelineQuery.refetch()}>
              Reintentar
            </button>
          </div>
        )}
        {timeline && (
          <>
            <div className="analytics-chart">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={timeline.results}
                  margin={{ top: 12, right: 20, left: 0, bottom: 8 }}
                >
                  <CartesianGrid stroke="#294157" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(date: string) => date.slice(5)}
                    stroke="#9eb1c5"
                    minTickGap={25}
                  />
                  <YAxis stroke="#9eb1c5" allowDecimals={false} />
                  <Tooltip />
                  <Legend />
                  {(sensor === 'all' || sensor === 'modis') && (
                    <Line
                      type="linear"
                      dataKey="modis"
                      name="MODIS"
                      stroke="#ffad75"
                      strokeWidth={2}
                      connectNulls={false}
                    />
                  )}
                  {(sensor === 'all' || sensor === 'viirs') && (
                    <Line
                      type="linear"
                      dataKey="viirs"
                      name="VIIRS"
                      stroke="#7ed8ff"
                      strokeWidth={2}
                      connectNulls={false}
                    />
                  )}
                  <Line
                    type="linear"
                    dataKey="harmonized"
                    name="Armonización"
                    stroke="#ff514c"
                    strokeWidth={2}
                    connectNulls={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="analytics-note">{timeline.note}</p>
          </>
        )}
      </section>

      <section className="analytics-panel">
        <h2>Comparación de observaciones</h2>
        <p className="analytics-note">
          Conteos de registros almacenados para el período seleccionado.
        </p>
        {!validRange && (
          <div className="analytics-empty">Selecciona un período válido.</div>
        )}
        {validRange && summaryQuery.isPending && (
          <div className="analytics-empty" role="status">
            Cargando comparación...
          </div>
        )}
        {validRange && summaryQuery.isError && (
          <div className="analytics-error" role="alert">
            No fue posible cargar la comparación.
          </div>
        )}
        {summary && (
          <>
            <div className="analytics-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={comparisonData}
                  margin={{ top: 20, right: 20, left: 10, bottom: 10 }}
                >
                  <CartesianGrid
                    stroke="#294157"
                    strokeDasharray="3 3"
                    vertical={false}
                  />
                  <XAxis dataKey="name" stroke="#9eb1c5" tickLine={false} />
                  <YAxis stroke="#9eb1c5" allowDecimals={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      background: '#102235',
                      border: '1px solid #294157',
                      borderRadius: 8,
                      color: '#f0f7ff',
                    }}
                  />
                  <Bar
                    dataKey="registros"
                    name="Registros almacenados"
                    maxBarSize={90}
                    radius={[6, 6, 0, 0]}
                  >
                    {comparisonData.map(item => (
                      <Cell key={item.name} fill={item.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="analytics-note">
              MODIS y VIIRS son detecciones originales. Armonización representa
              resultados de integración o procesamiento. No sumes los tres
              conteos como si fueran incendios independientes.
            </p>
            {product === 'level2' && (
              <p className="analytics-note">
                La cobertura científica Level 2 puede ser parcial.
              </p>
            )}
          </>
        )}
      </section>

      <section className="analytics-panel">
        <h2>Exportación de datos</h2>
        <p className="analytics-note">
          Descarga registros reales almacenados en PostgreSQL para el período
          seleccionado. La exportación actual no aplica filtros geográficos.
        </p>
        <div className="analytics-export-controls">
          <label>
            Conjunto de datos
            <select
              value={exportDataset}
              onChange={event =>
                setExportDataset(event.target.value as ExportDataset)
              }
            >
              <option value="modis">Detecciones MODIS</option>
              <option value="viirs">Detecciones VIIRS</option>
              <option value="harmonized">Resultados armonizados</option>
            </select>
          </label>
          <a
            className={`analytics-export-button ${!validRange ? 'disabled' : ''}`}
            href={validRange ? exportUrl : undefined}
            aria-disabled={!validRange}
            onClick={event => {
              if (!validRange) event.preventDefault()
            }}
          >
            Descargar CSV
          </a>
        </div>
        <p className="analytics-note">
          Período: {startDate || '—'} al {endDate || '—'} UTC.
          {exportDataset === 'harmonized' && (
            <>
              {' '}Producto: {product === 'operational'
                ? 'Integración operativa FIRMS'
                : 'Armonización científica Level 2'}.
              {product === 'level2' && !version
                ? ' Se incluyen todas las versiones almacenadas.'
                : ''}
            </>
          )}
        </p>
      </section>
    </main>
  )
}
