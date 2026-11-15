import { useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import Globe from './Globe'
import ScientificJobs from './ScientificJobs'
import LocationSearch, { type Place } from './LocationSearch'
import { apiGet, fetchOperationalPoints, fetchHarmonizedPoints, comparable, fetchCellsRange, fetchRegions, fetchDates, sensors, summarize, type Cell, type PixelCatalog } from './data'
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
  const periods=useRef<Record<string,{start:string;end:string}>>({})
  const [showH3,setShowH3]=useState(false)
  const [operational,setOperational]=useState(true)
  const operationalJobs=useQuery({queryKey:['operational-jobs'],queryFn:({signal})=>apiGet<{date:string;status:string}[]>('/v1/harmonized-detections/jobs/',signal),refetchInterval:10000})
  const [productVersion,setProductVersion]=useState('')
  const pointCatalog=useQuery({queryKey:['pixel-catalog'],queryFn:({signal})=>apiGet<PixelCatalog>('/v1/harmonization/detections/catalog/',signal),refetchInterval:10000})
  const [scientificArea,setScientificArea]=useState('')
  const [tab, setTab] = useState<typeof tabs[number]>('MODIS')
  const [startDate, setStartDate] = useState('2024-04-16')
  const [endDate, setEndDate] = useState('2024-04-16')
  const globalFirms: boolean = ![tabs[2]].includes(tab as typeof tabs[2])
  const [version, setVersion] = useState('v1_experimental')
  const runsQuery = useQuery({ queryKey: ['runs'], queryFn: ({ signal }) => apiGet<{version:string}[]>('/v1/harmonization/versions/', signal) })
  const [satellite, setSatellite] = useState('')
  const sensor = tab === 'VIIRS' ? 'viirs' : 'modis'
  useEffect(() => { setSatellite('') }, [sensor])
  const availabilityQuery = useQuery({queryKey:['nasa-availability',sensor],queryFn:({signal}) => apiGet<{min_date:string;max_date:string;products:{source:string;min_date:string;max_date:string}[]}>('/v1/detections/availability/?sensor='+sensor,signal),staleTime:3600000,retry:false})
  const available = availabilityQuery.data
  const [menuOpen, setMenuOpen] = useState(false)
  const [country, setCountry] = useState('')
  const [region, setRegion] = useState('')
  const regionQuery = useQuery({ queryKey: ['regions'], queryFn: ({ signal }) => fetchRegions(signal), retry: false })
  const datesQuery = useQuery({ queryKey: ['dates', globalFirms, sensor, region], queryFn: ({ signal }) => globalFirms ? apiGet<{dates:string[]}>('/v1/detections/dates/?sensor=' + sensor, signal) : fetchDates(region, signal), enabled: true, retry: false })
  const processedDates=useQuery({queryKey:['processed-dates'],queryFn:({signal})=>fetchDates('',signal)})
  const harmonyInitialized=useRef(false)
  useEffect(()=>{const dates=operational ? operationalJobs.data?.filter(j=>j.status==='COMPLETADO').map(j=>j.date) : pointCatalog.data?.dates.length ? pointCatalog.data.dates : processedDates.data?.dates;if(!globalFirms && !harmonyInitialized.current && (operational?operationalJobs.data:pointCatalog.data) && dates?.length){const latest=[...dates].sort().at(-1)!;setStartDate(latest);setEndDate(latest);harmonyInitialized.current=true}},[globalFirms,processedDates.data,pointCatalog.data,operational,operationalJobs.data])
  const switchTab=(next:typeof tabs[number])=>{periods.current[tab]={start:startDate,end:endDate};const saved=periods.current[next] ?? (next!=='Armonización' ? periods.current['MODIS'] ?? periods.current['VIIRS'] : undefined);if(saved){setStartDate(saved.start);setEndDate(saved.end)}setTab(next);setSatellite('')}
  const [selectedCountry, setSelectedCountry] = useState<Place | null>(null)
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null)
  const [selectedCity, setSelectedCity] = useState<Place | null>(null)
  useEffect(() => {
    const available = datesQuery.data?.dates
    if (!startDate && available?.length) {
      setStartDate(available[0]); setEndDate(available[0])
    }
  }, [datesQuery.data])

  const dateRangeError = globalFirms && available && (startDate < available.min_date || endDate > available.max_date) ? 'Fuera de disponibilidad NASA para este sensor.' : !startDate || !endDate ? 'Selecciona las dos fechas del rango.'
    : startDate > endDate ? 'La fecha inicial debe ser anterior o igual a la fecha final.'
    : (Date.parse(endDate + 'T00:00:00Z') - Date.parse(startDate + 'T00:00:00Z')) / 86400000 >= 31
      ? 'Selecciona un rango máximo de 31 días para evitar consultas excesivas a la API.' : ''
  const selectedLocation=selectedCity ?? selectedPlace ?? selectedCountry
  const locationBounds=selectedLocation?.bbox ?? (selectedLocation ? [((selectedLocation.lon-.5+540)%360)-180,Math.max(-90,selectedLocation.lat-.5),((selectedLocation.lon+.5+540)%360)-180,Math.min(90,selectedLocation.lat+.5)] : undefined)
  const harmonyBBox=scientificArea || locationBounds?.join(',') || ''
  const query = useQuery({
    queryKey: ['cells-range', startDate, endDate, region, version, harmonyBBox],
    queryFn: ({ signal }) => fetchCellsRange(startDate, endDate, region, signal, version, harmonyBBox),
    enabled: !globalFirms && showH3 && !dateRangeError, refetchInterval: globalFirms || !showH3 ? false : 10000, retry: false, staleTime: 60_000,
  })
  const pointsQuery=useQuery({queryKey:['harmonized-points',startDate,endDate,harmonyBBox,productVersion],queryFn:({signal})=>fetchHarmonizedPoints(startDate,endDate,harmonyBBox,productVersion,signal),enabled:!globalFirms && !operational && !dateRangeError,refetchInterval:10000,retry:false})
  const operationalQuery=useQuery({queryKey:['operational-points',startDate,endDate,harmonyBBox],queryFn:({signal})=>fetchOperationalPoints(startDate,endDate,harmonyBBox,signal),enabled:!globalFirms && operational && !dateRangeError,refetchInterval:q=>q.state.data?.missing_dates.length ? 10000 : false,staleTime:120000,retry:false})
  const pointRows=operational ? operationalQuery.data?.results ?? [] : pointsQuery.data ?? []
  const rows = globalFirms || dateRangeError ? empty : query.data ?? empty
  const countries = useMemo(() => unique(rows.map(row => row.pais ?? '')), [rows])
  const regions = useMemo(() => unique(rows.filter(row => !country || row.pais === country).map(row => row.estado ?? '')), [rows, country])
  const selected = useMemo(() => rows.filter(row => (!country || row.pais === country) &&
    (!region || row.region_id === region)), [rows, country, region])
  const candidates = useMemo(() => selected.filter(comparable), [selected])
  const visible = selected
  const comparableCounts = ['AMBOS', 'SOLO_MODIS', 'SOLO_VIIRS', 'NINGUNO', 'NO_EVALUABLE'].map(label => ({ label, value: selected.filter(row => row.coincidencia_qa === label).length }))
  useEffect(() => {
    if (!menuOpen) return
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenuOpen(false) }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [menuOpen])
  const hasObservations = visible.length > 0
  const status = dateRangeError || (!globalFirms && operational && !showH3 ? operationalQuery.isError ? 'Error consultando la integraci\u00f3n mundial FIRMS.' : operationalQuery.isFetching ? 'Cargando producto operativo mundial...' : operationalQuery.data?.missing_dates.length ? 'Hay fechas pendientes de sincronizaci\u00f3n mundial. Solicita el trabajo o ejecuta harmonize_firms.' : !operationalQuery.data?.count ? 'Sin detecciones para este per\u00edodo y \u00e1rea.' : '' : '') || (globalFirms || (operational && !showH3) ? '' : !showH3 ? (pointsQuery.isError ? 'Error consultando el producto armonizado.' : pointsQuery.isFetching ? 'Cargando detecciones armonizadas Level 2…' : !pointsQuery.data?.length ? 'No hay detecciones armonizadas procesadas para este período y área.' : '') : (query.isError ? 'Error consultando el análisis H3.' : query.isFetching ? 'Cargando análisis H3…' : !visible.length ? 'No hay observaciones H3 para este período.' : ''))
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
        <button type="button" role="tab" aria-selected={tab === item} className={tab === item ? 'selected' : ''} key={item} onClick={() => { switchTab(item) }}>
          <span className="tab-letter" aria-hidden="true">{index === 0 ? 'M' : index === 1 ? 'V' : 'A'}</span>
          <span>{item}</span>
        </button>
      )}</nav>
      <div className="heading"><div><h1>{tab === 'MODIS' ? 'Observación satelital' : tab === 'VIIRS' ? 'Observaciones VIIRS' : 'Armonización MODIS–VIIRS'}</h1>
      <p>{tab === 'MODIS' ? 'Detecciones térmicas NASA FIRMS · Terra y Aqua' : tab === 'VIIRS' ? 'Detecciones mundiales NASA FIRMS · Suomi NPP' : operational ? 'Integraci\u00f3n mundial MODIS + VIIRS \u00b7 FIRMS, asociaciones exploratorias' : 'Armonizaci\u00f3n cient\u00edfica Level 2 \u00b7 Cobertura procesada parcial'}</p></div></div>
      <section aria-label="Filtros de observación" className="filters">
        {!globalFirms && showH3 && <label>Versión científica<select value={version} onChange={e => setVersion(e.target.value)}>{[...new Set([version,...(runsQuery.data ?? []).map(r => r.version)])].map(v => <option key={v}>{v}</option>)}</select></label>}
        {globalFirms && <label>Satélite<select value={satellite} onChange={e => setSatellite(e.target.value)}><option value="">Todos</option>{(sensor === 'modis' ? ['aqua','terra'] : ['snpp']).map(value => <option key={value} value={value}>{value.toUpperCase()}</option>)}</select></label>}

        <div className="date-range" role="group" aria-label="Rango de fechas UTC">
          <label>Desde (UTC)<input type="date" value={startDate} min={globalFirms ? available?.min_date : undefined} max={globalFirms ? available?.max_date : endDate || undefined} onChange={event => { if(!globalFirms)harmonyInitialized.current=true; setStartDate(event.target.value); setCountry('') }} /></label>
          <label>Hasta (UTC)<input type="date" value={endDate} min={globalFirms ? available?.min_date : startDate || undefined} max={globalFirms ? available?.max_date : undefined} onChange={event => { if(!globalFirms)harmonyInitialized.current=true; setEndDate(event.target.value); setCountry('') }} /></label>
        </div>
        <LocationSearch kind="country" label="País" placeholder="Escribe un país…" value={selectedCountry} onSelect={place => {
          setScientificArea(''); setRegion(''); setSelectedCountry(place); setSelectedPlace(null); setSelectedCity(null)
          // Solo filtramos la tabla si la API conoce el país por ese nombre;
          // la búsqueda cartográfica funciona incluso si no hay lotes disponibles.
          const match = place && countries.find(name => name.toLocaleLowerCase('es').normalize('NFD').replace(/[\u0300-\u036f]/g, '') === place.name.toLocaleLowerCase('es').normalize('NFD').replace(/[\u0300-\u036f]/g, ''))
          void match; setCountry('')
        }} />
        <LocationSearch kind="state" label="Estado / provincia" placeholder={selectedCountry ? 'Elige o escribe un estado…' : 'Selecciona un país'}
          disabled={!selectedCountry?.countryCode} countryCode={selectedCountry?.countryCode} value={selectedPlace} onSelect={place => {
            setScientificArea(''); setRegion(''); setSelectedPlace(place); setSelectedCity(null)
            const match = place && regions.find(name => name.toLocaleLowerCase('es').normalize('NFD').replace(/[\u0300-\u036f]/g, '') === place.name.toLocaleLowerCase('es').normalize('NFD').replace(/[\u0300-\u036f]/g, ''))
            void match
          }} />
        <LocationSearch kind="city" label="Ciudad / municipio" placeholder={!selectedCountry ? 'Selecciona un país' : !selectedPlace ? 'Selecciona un estado' : 'Elige o escribe una ciudad…'}
          disabled={!selectedCountry?.countryCode || !selectedPlace} countryCode={selectedCountry?.countryCode} stateName={selectedPlace?.name} stateBounds={selectedPlace?.bbox} value={selectedCity} onSelect={place=>{setScientificArea('');setSelectedCity(place)}} />
      </section>
      {globalFirms && available && <div className="nasa-availability"><span>{sensor.toUpperCase()} · UTC · {available.min_date} — {available.max_date}</span>{[1,7].map(days => <button key={days} onClick={() => { const end=available.max_date; setEndDate(end); setStartDate(new Date(Date.parse(end+'T00:00:00Z')-(days-1)*86400000).toISOString().slice(0,10)) }}>{days===1 ? 'Últimas 24 horas disponibles' : 'Últimos 7 días disponibles'}</button>)}</div>}
      {availabilityQuery.isError && <p role="alert">Disponibilidad NASA no verificable; no se asumen límites.</p>}
      {datesQuery.isError && <p role="alert">No se pudieron cargar las fechas de PostgreSQL.</p>}
      {regionQuery.isError && <p role="alert">No se pudieron cargar las regiones de PostgreSQL.</p>}
      {status && <div className="status" role="status">{status} {query.isError && <button onClick={() => void query.refetch()}>Reintentar</button>}</div>}

      {!globalFirms && !showH3 && <div className="nasa-availability"><label>Producto <select aria-label="Producto armonizado" value={operational?'operational':'level2'} onChange={e=>setOperational(e.target.value==='operational')}><option value="operational">Integración mundial FIRMS</option><option value="level2">Armonización científica Level 2</option></select></label>{!operational && <label>Versión <select value={productVersion} onChange={e=>setProductVersion(e.target.value)}><option value="">Unificado sin duplicados de reprocesamiento</option>{pointCatalog.data?.versions.map(v=><option key={v.version}>{v.version}</option>)}</select></label>}<span>{operational ? operationalQuery.data?.count??0 : pointsQuery.data?.length??0} detecciones armonizadas</span></div>}
      <div className="dashboard map-view">
        <Globe onWorld={()=>{setScientificArea('');setSelectedCountry(null);setSelectedPlace(null);setSelectedCity(null)}} operational={operational} harmonized={pointRows} showH3={showH3} onShowH3={setShowH3} onAreaSelected={setScientificArea} firms={globalFirms ? { start: startDate, end: endDate, sensor, satellite, region, valid: !dateRangeError } : undefined} focusPoint={selectedCity ?? selectedPlace ?? selectedCountry} rows={globalFirms ? empty : visible} active={tab === 'MODIS' ? ['modis'] : tab === 'VIIRS' ? ['viirs'] : [...sensors]} />
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
      {!globalFirms && showH3 && <section className="below-map" aria-label="Resumen de armonización">
        {visible.length>0 && !visible.some(r=>['AMBOS','SOLO_MODIS','SOLO_VIIRS'].includes(r.coincidencia_qa)) && <p className="note">Hay observaciones procesadas, pero ninguna detección evaluable positiva en esta selección. Usa Todas las observaciones H3 para revisar la cobertura y QA.</p>}
        <h2>Armonización experimental · {version}</h2>
        <div className="selection-summary"><div><span>Observaciones</span><strong>{visible.length}</strong></div><div><span>Evaluables</span><strong>{visible.filter(r=>r.coincidencia_original!=='NO_EVALUABLE').length}</strong></div><div><span>Regiones</span><strong>{unique(visible.map(r=>r.region_nombre)).join(', ') || 'Sin resultados'}</strong></div><div><span>UTC</span><strong>{startDate} — {endDate}</strong></div></div>
        <div className="metrics">{comparableCounts.map(item=><div key={item.label}><span>{item.label}</span> <strong>{item.value}</strong></div>)}</div>
        <p className="note">Selecciona una celda para consultar QA, tiempos, cobertura y sobrevuelos. Los hexágonos H3 no representan perímetros de incendios.</p>
      </section>}
      {!globalFirms && !showH3 && <section className="below-map" aria-label="Resumen de detecciones armonizadas"><span>{startDate} — {endDate} UTC · {operational ? operationalQuery.data?.count??0 : pointRows.length} resultados · {selectedLocation?.name || scientificArea || 'Mundo'} · {operational ? 'Integración operativa FIRMS mundial' : 'Level 2; cobertura procesada parcial'}</span><div className="metrics">{['ASOCIADA','SOLO_MODIS','SOLO_VIIRS',...(!operational?['SIN_COMPARABILIDAD']:[])].map(status=><span key={status}>{status}: {operational ? operationalQuery.data?.counts[status]??0 : pointRows.filter(p=>p.status===status).length}</span>)}</div><p className="note">{operational ? `Asociaciones exploratorias FIRMS: 1.500 m / 15 min, dentro de cada día UTC. Sin QA Level 2 ni cobertura compartida evaluada. ${operationalQuery.data?.mode==='aggregated' ? 'Vista mundial agrupada; cada punto usa una observación original representativa. Selecciona un área para ver el detalle.' : ''}` : 'Asociaciones Level 2 exploratorias. Cada punto utiliza un centro de píxel original.'}</p></section>}
      {!globalFirms && <ScientificJobs operational={operational && !showH3} date={startDate} bbox={harmonyBBox} onResults={(date,version)=>{setStartDate(date);setEndDate(date);setVersion(version);setOperational(false);setProductVersion('pixel_assoc_v1__'+version);setShowH3(false);setScientificArea('');setSelectedCountry(null);setSelectedPlace(null);setSelectedCity(null)}}/>}
      <footer>TerraFlare © {new Date().getFullYear()} · Datos: <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer">NASA FIRMS</a> / <a href="https://www.earthdata.nasa.gov/" target="_blank" rel="noreferrer">Earthdata</a>.</footer>
    </main>
  </div>
}

const client = new QueryClient()
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={client}><App /></QueryClientProvider>)
