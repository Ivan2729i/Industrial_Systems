import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import Globe from './Globe'
import LocationSearch, { type Place } from './LocationSearch'
import { apiGet, comparable, fetchCellsRange, fetchRegions, fetchDates, sensors, summarize, type Cell } from './data'
import './style.css'

const tabs = ['MODIS', 'VIIRS', 'Armonización'] as const
const empty: Cell[] = []
const labels = { modis: 'MODIS', viirs: 'VIIRS' }
const metadata = {
  modis: { platform: 'Plataforma no informada en V1', products: 'MYD14 + MYD03', color: '#ffad75' },
  viirs: { platform: 'Plataforma no informada en V1', products: 'VNP14IMG + VNP03IMG', color: '#7ed8ff' },
}
const number = Intl.NumberFormat('es-MX', { maximumFractionDigits: 1 })
const unique = (values: string[]) => [...new Set(values.filter(Boolean))].sort()

function App() {
  const [tab, setTab] = useState<typeof tabs[number]>('MODIS')
  const [startDate, setStartDate] = useState('2024-04-16')
  const [endDate, setEndDate] = useState('2024-04-16')
  const globalFirms: boolean = ![tabs[2]].includes(tab as typeof tabs[2])
  const [version, setVersion] = useState('v1_experimental')
  const runsQuery = useQuery({ queryKey: ['runs'], queryFn: ({ signal }) => apiGet<{version:string}[]>('/v1/harmonization/versions/', signal) })
  const [satellite, setSatellite] = useState('')
  const sensor = tab === 'VIIRS' ? 'viirs' : 'modis'
  const [menuOpen, setMenuOpen] = useState(false)
  const [country, setCountry] = useState('')
  const [region, setRegion] = useState('')
  const regionQuery = useQuery({ queryKey: ['regions'], queryFn: ({ signal }) => fetchRegions(signal), retry: false })
  const datesQuery = useQuery({ queryKey: ['dates', globalFirms, sensor, region], queryFn: ({ signal }) => globalFirms ? apiGet<{dates:string[]}>('/v1/detections/dates/?sensor=' + sensor, signal) : fetchDates(region, signal), enabled: globalFirms || !!region, retry: false })
  const [selectedCountry, setSelectedCountry] = useState<Place | null>(null)
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null)
  const [selectedCity, setSelectedCity] = useState<Place | null>(null)
  useEffect(() => {
    const available = datesQuery.data?.dates
    if (available?.length && !available.includes(startDate)) {
      setStartDate(available[0]); setEndDate(available[0])
    }
  }, [datesQuery.data])

  const dateRangeError = !startDate || !endDate ? 'Selecciona las dos fechas del rango.'
    : startDate > endDate ? 'La fecha inicial debe ser anterior o igual a la fecha final.'
    : (Date.parse(endDate + 'T00:00:00Z') - Date.parse(startDate + 'T00:00:00Z')) / 86400000 >= 31
      ? 'Selecciona un rango máximo de 31 días para evitar consultas excesivas a la API.' : ''
  const query = useQuery({
    queryKey: ['cells-range', startDate, endDate, region, version],
    queryFn: ({ signal }) => fetchCellsRange(startDate, endDate, region, signal, version),
    enabled: !globalFirms && !!region && !dateRangeError, retry: false, staleTime: 60_000,
  })
  const rows = globalFirms ? empty : query.data ?? empty
  const countries = useMemo(() => unique(rows.map(row => row.pais ?? '')), [rows])
  const regions = useMemo(() => unique(rows.filter(row => !country || row.pais === country).map(row => row.estado ?? '')), [rows, country])
  const selected = useMemo(() => rows.filter(row => (!country || row.pais === country) &&
    (!region || row.region_id === region)), [rows, country, region])
  const candidates = useMemo(() => selected.filter(comparable), [selected])
  const visible = selected
  const comparableCounts = ['AMBOS', 'SOLO_MODIS', 'SOLO_VIIRS', 'NINGUNO', 'NO_EVALUABLE'].map(label => ({ label, value: selected.filter(row => row.coincidencia_original === label).length }))
  useEffect(() => {
    if (!menuOpen) return
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenuOpen(false) }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [menuOpen])
  const hasObservations = visible.length > 0
  const status = dateRangeError || (globalFirms ? '' :
    (query.isFetching && !query.data ? 'Consultando el lote en Django…'
    : query.isError ? 'No se pudo cargar el lote. ' + (query.error instanceof Error ? query.error.message : '')
    : query.data === null ? 'La API no tiene lotes para el rango seleccionado.'
    : !hasObservations ? 'No hay resultados de armonizacion procesados para esta region y fecha.' : ''))
  const source = sensors.map(sensor => {
    const passes = unique(visible.map(row => row[`${sensor}_sobrevuelo`]))
    return passes.length ? labels[sensor] + ' ' + passes.join(', ') : ''
  }).filter(Boolean).join(' · ')

  return <div className="shell">
    <header className="top">
      <div className="header-left">
        <button type="button" className="menu-trigger" aria-label={menuOpen ? 'Cerrar menú de navegación' : 'Abrir menú de navegación'} aria-expanded={menuOpen} aria-controls="main-menu" onClick={() => setMenuOpen(open => !open)}>
          <span /><span /><span />
        </button>
        <button className="brand" onClick={() => { setTab('MODIS'); setMenuOpen(false) }}><img src="/terraflare.png" alt="" /><span>TerraFlare</span></button>
      </div>
      <span className="mission">NASA SPACE APPS CHALLENGE</span>
    </header>
    {menuOpen && <>
      <button type="button" className="menu-backdrop" aria-label="Cerrar menú" onClick={() => setMenuOpen(false)} />
      <aside id="main-menu" className="side-menu" aria-label="Menú principal">
        <div className="side-menu-heading"><span>MENÚ PRINCIPAL</span><button type="button" onClick={() => setMenuOpen(false)} aria-label="Cerrar menú">×</button></div>
        <nav aria-label="Navegación principal">
          <button type="button" className="side-menu-item active" aria-current="page" onClick={() => { setTab('MODIS'); setMenuOpen(false); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>
            <span className="menu-home-icon" aria-hidden="true">⌂</span><span>Pantalla principal</span><span className="menu-item-chevron" aria-hidden="true">›</span>
          </button>
        </nav>
        <div className="side-menu-footer">TerraFlare · NASA Space Apps Challenge</div>
      </aside>
    </>}
    <main className="content">
      <nav className="view-tabs" aria-label="Secciones de TerraFlare">{tabs.map((item, index) =>
        <button type="button" role="tab" aria-selected={tab === item} className={tab === item ? 'selected' : ''} key={item} onClick={() => { setTab(item); setSatellite(''); setSelectedCountry(null); setSelectedPlace(null); setSelectedCity(null) }}>
          <span className="tab-letter" aria-hidden="true">{index === 0 ? 'M' : index === 1 ? 'V' : 'A'}</span>
          <span>{item}</span>
        </button>
      )}</nav>
      <div className="heading"><div><h1>{tab === 'MODIS' ? 'Observación satelital' : tab === 'VIIRS' ? 'Observaciones VIIRS' : 'Armonización MODIS–VIIRS'}</h1>
      <p>{tab === 'MODIS' ? 'Explora detecciones de fuego y calidad de observación por celda H3 · Resolución 7' : tab === 'VIIRS' ? 'Detecciones mundiales NASA FIRMS / Suomi NPP, NOAA-20 y NOAA-21' : 'Comparación exploratoria de observaciones MODIS y VIIRS sobre celdas H3 · Resolución 7'}</p></div></div>
      <section aria-label="Filtros de observación" className="filters">
        {!globalFirms && <label>Version cientifica<select value={version} onChange={e => setVersion(e.target.value)}>{[...new Set((runsQuery.data ?? [{ version: 'v1_experimental' }]).map(r => r.version))].map(v => <option key={v}>{v}</option>)}</select></label>}
        {!globalFirms && <label>Region cientifica<select value={region} onChange={event => {
          const id = event.target.value; setRegion(id); setCountry(''); setSelectedPlace(null); setSelectedCity(null)
          const next = regionQuery.data?.find(item => item.id === id)
          if (next && next.west !== null && next.east !== null && next.south !== null && next.north !== null) setSelectedPlace({ name: next.name, lat: (next.south + next.north) / 2, lon: (next.west + next.east) / 2, kind: 'state' } as Place)
        }}><option value="">Selecciona una region procesada</option>{(regionQuery.data ?? []).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        {globalFirms && <label>Satelite<select value={satellite} onChange={e => setSatellite(e.target.value)}><option value="">Todos</option>{(sensor === 'modis' ? ['aqua','terra'] : ['snpp','noaa20','noaa21']).map(value => <option key={value} value={value}>{value.toUpperCase()}</option>)}</select></label>}
        <label>Fecha disponible<select value={startDate === endDate ? startDate : ''} onChange={event => { setStartDate(event.target.value); setEndDate(event.target.value) }}><option value="" disabled>Selecciona fecha</option>{(datesQuery.data?.dates ?? []).map(day => <option key={day}>{day}</option>)}</select></label>
        <div className="date-range" role="group" aria-label="Rango de fechas UTC">
          <label>Desde (UTC)<input type="date" value={startDate} max={endDate || undefined} onChange={event => { setStartDate(event.target.value); setCountry('') }} /></label>
          <label>Hasta (UTC)<input type="date" value={endDate} min={startDate || undefined} onChange={event => { setEndDate(event.target.value); setCountry('') }} /></label>
        </div>
        <LocationSearch kind="country" label="País" placeholder="Escribe un país…" value={selectedCountry} onSelect={place => {
          setSelectedCountry(place); setSelectedPlace(null); setSelectedCity(null)
          // Solo filtramos la tabla si la API conoce el país por ese nombre;
          // la búsqueda cartográfica funciona incluso si no hay lotes disponibles.
          const match = place && countries.find(name => name.toLocaleLowerCase('es').normalize('NFD').replace(/[\u0300-\u036f]/g, '') === place.name.toLocaleLowerCase('es').normalize('NFD').replace(/[\u0300-\u036f]/g, ''))
          void match; setCountry('')
        }} />
        <LocationSearch kind="state" label="Estado / provincia" placeholder={selectedCountry ? 'Elige o escribe un estado…' : 'Selecciona un país'}
          disabled={!selectedCountry?.countryCode} countryCode={selectedCountry?.countryCode} value={selectedPlace} onSelect={place => {
            setSelectedPlace(place); setSelectedCity(null)
            const match = place && regions.find(name => name.toLocaleLowerCase('es').normalize('NFD').replace(/[\u0300-\u036f]/g, '') === place.name.toLocaleLowerCase('es').normalize('NFD').replace(/[\u0300-\u036f]/g, ''))
            void match
          }} />
        <LocationSearch kind="city" label="Ciudad / municipio" placeholder={!selectedCountry ? 'Selecciona un país' : !selectedPlace ? 'Selecciona un estado' : 'Elige o escribe una ciudad…'}
          disabled={!selectedCountry?.countryCode || !selectedPlace} countryCode={selectedCountry?.countryCode} stateName={selectedPlace?.name} value={selectedCity} onSelect={setSelectedCity} />
      </section>
      {datesQuery.isError && <p role="alert">No se pudieron cargar las fechas de PostgreSQL.</p>}
      {regionQuery.isError && <p role="alert">No se pudieron cargar las regiones de PostgreSQL.</p>}
      {status && <div className="status" role="status">{status} {query.isError && <button onClick={() => void query.refetch()}>Reintentar</button>}</div>}

      <div className="dashboard map-view">
        <Globe firms={globalFirms ? { start: startDate, end: endDate, sensor, satellite } : undefined} focusPoint={selectedCity ?? selectedPlace ?? selectedCountry} rows={globalFirms ? empty : visible} active={tab === 'MODIS' ? ['modis'] : tab === 'VIIRS' ? ['viirs'] : [...sensors]} />
        {false && <aside className="sensor-panel" aria-label="Observaciones por sensor">
          <h2>{tab === 'MODIS' ? 'Resumen de observación' : 'Productos y calidad por sensor'}</h2>
          <div className="cards">{sensors.map(sensor => {
            const { observed, fire, usefulPct } = summarize(visible, sensor)
            const meta = metadata[sensor]
            return <article className="card" key={sensor} style={{ borderTopColor: meta.color }}>
              <h3 style={{ color: meta.color }}>{labels[sensor]} <span>{meta.platform}</span></h3>
              <p>{meta.products}</p>
              <dl><dt>Píxeles de fuego</dt><dd>{observed ? (fire === null ? 'Desconocido' : number.format(fire)) : '—'}</dd>
                <dt>Celdas con observación</dt><dd>{hasObservations ? number.format(observed) : '—'}</dd>
                <dt>Píxeles útiles</dt><dd>{usefulPct === null ? '—' : number.format(usefulPct) + ' %'}</dd></dl>
            </article>
          })}</div>
          <p className="note">Los poligonos representan celdas H3, no perimetros de incendios. Una celda puede contener varios píxeles de fuego.</p>
        </aside>}
      </div>
      {!globalFirms && <section className="below-map" aria-label="Datos de la selección">
        <div className="below-title"><div><h2>{tab === 'MODIS' ? 'Datos de observación' : tab === 'VIIRS' ? 'Datos del sensor VIIRS' : 'Resultados de armonización'}</h2><p>{tab === 'Armonización' ? 'Comparabilidad y detecciones en celdas H3 con observación útil en ambos sensores' : 'Resultados de los filtros y sobrevuelos seleccionados'}</p></div><span className="selection-pill">{number.format(visible.length)} registros</span></div>
        <p className="geo-note">La busqueda geografica navega por el mapa. La region cientifica y las fechas seleccionan los datos de PostgreSQL; no se inventan detecciones para ciudades.</p>
        <div className="selection-summary">
          <div><span>Rango UTC</span><strong>{startDate && endDate ? startDate + ' → ' + endDate : '—'}</strong></div>
          <div><span>País</span><strong>{selectedCountry?.name || (countries.length ? 'Todos' : 'No informado')}</strong></div>
          <div><span>Estado / ciudad</span><strong>{[selectedPlace?.name, selectedCity?.name].filter(Boolean).join(' · ') || (regions.length ? 'Todos' : 'No informado')}</strong></div>
          <div><span>Celdas candidatas</span><strong>{number.format(candidates.length)}</strong></div>
        </div>
        {tab === 'Armonización' && <div className="method-notice">Armonizacion V1 experimental. Datos historicos de abril de 2024. No existe una correccion estadistica validada de sensibilidad entre MODIS y VIIRS. Cada registro identifica sus sobrevuelos.</div>}
        <div className="observation-grid">{sensors.filter(sensor => tab === 'Armonización' || (tab === 'VIIRS' ? sensor === 'viirs' : sensor === 'modis')).map(sensor => {
          const { observed, fire, usefulPct } = summarize(visible, sensor)
          const meta = metadata[sensor]
          return <article className="card" key={sensor} style={{ borderTopColor: meta.color }}>
            <h3 style={{ color: meta.color }}>{labels[sensor]} <span>{meta.platform} · {meta.products}</span></h3>
            <dl><dt>Píxeles de fuego</dt><dd>{hasObservations ? (fire === null ? 'Desconocido' : number.format(fire)) : '—'}</dd>
              <dt>Celdas con observación</dt><dd>{hasObservations ? number.format(observed) : '—'}</dd>
              <dt>Píxeles útiles</dt><dd>{usefulPct === null ? '—' : number.format(usefulPct) + ' %'}</dd></dl>
          </article>
        })}</div>
        {tab === 'Armonización' && <div className="harmonization-summary"><h3>Clasificaciones originales almacenadas</h3><div className="metrics">{comparableCounts.map(item => <article className="card" key={item.label}><h3>{item.label}</h3><strong>{number.format(item.value)}</strong></article>)}</div><p className="note">Categorias cientificas originales. Consulta tambien la clasificacion QA y los tiempos de cada pareja en la tabla o seleccionando un hexagono.</p></div>}
        <h3 className="data-heading">{tab === 'VIIRS' ? 'Detalle de celdas H3 · VIIRS' : tab === 'Armonización' ? 'Detalle de comparación por celda H3' : 'Detalle de celdas H3 · MODIS'}</h3>
        {visible.length ? <div className="table-scroll"><table className="observations-table"><thead><tr><th>Fecha UTC</th><th>Celda H3</th><th>Sobrevuelos MODIS / VIIRS</th><th>País</th><th>Estado</th>{tab !== 'VIIRS' && <th>MODIS fuego</th>}{tab !== 'MODIS' && <th>VIIRS fuego</th>}{tab === 'VIIRS' ? <><th>VIIRS útiles</th><th>VIIRS nubes</th></> : <th>Candidata</th>}{tab === 'Armonización' && <><th>Original</th><th>Despues de QA</th><th>Estrato temporal</th></>}</tr></thead><tbody>{visible.slice(0, 100).map((row, index) => <tr key={row.id || index}><td>{row.fecha}</td><td>{row.celda_h3}</td><td>{row.modis_sobrevuelo} / {row.viirs_sobrevuelo}</td><td>{row.pais || '—'}</td><td>{row.region_nombre || row.estado || '—'}</td>{tab !== 'VIIRS' && <td>{row.modis_fuego ?? 'Desconocido'}</td>}{tab !== 'MODIS' && <td>{row.viirs_fuego ?? 'Desconocido'}</td>}{tab === 'VIIRS' ? <><td>{row.viirs_utiles}</td><td>{row.viirs_nubes}</td></> : <td>{comparable(row) ? 'Sí' : 'No'}</td>}{tab === 'Armonización' && <><td>{row.coincidencia_original}</td><td>{row.coincidencia_qa}</td><td>{row.estrato_temporal}</td></>}</tr>)}</tbody></table>{visible.length > 100 && <p className="note">Mostrando los primeros 100 de {number.format(visible.length)} registros.</p>}</div> : <p className="empty-table">No hay registros disponibles para esta selección. Comprueba la fecha y la conexión con Django.</p>}
      </section>}
      <footer><p><strong>Trazabilidad</strong> {source || 'Sin sobrevuelos informados para esta selección.'}</p>
      <p>Para interpretar los ceros, revisa si hubo cobertura válida. La falta de detecciones con cobertura insuficiente no permite concluir que no hubo incendios.</p></footer>
    </main>
  </div>
}

const client = new QueryClient()
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={client}><App /></QueryClientProvider>)
