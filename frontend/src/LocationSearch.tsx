import { useEffect, useMemo, useRef, useState } from 'react'
import { countries } from './countries'
import { localCities, localStates } from './localPlaces'

export type Place = { name: string; label: string; lon: number; lat: number; countryCode: string; kind: 'country' | 'state' | 'city'; bbox?: [number,number,number,number]; isoCode?: string; id?: string }

type Props = {
  label: string
  placeholder: string
  kind: 'country' | 'state' | 'city'
  countryCode?: string
  stateBounds?: [number,number,number,number]
  stateName?: string
  value: Place | null
  disabled?: boolean
  onSelect: (place: Place | null) => void
}

const geographyCache=new Map<string,{body:string;expires:number}>()
async function geoFetch(url:string,options?:RequestInit){
  const cached=geographyCache.get(url)
  if(cached && cached.expires>Date.now())return new Response(cached.body,{headers:{'Content-Type':'application/json'}})
  const response=await fetch(url,options)
  if(response.ok){const body=await response.clone().text();geographyCache.set(url,{body,expires:Date.now()+300000});if(geographyCache.size>100)geographyCache.delete(geographyCache.keys().next().value!)}
  return response
}

type PhotonFeature = {
  properties?: { osm_id?: number; osm_type?: string; extent?: number[]; name?: string; country?: string; state?: string; countrycode?: string; type?: string; osm_value?: string }
  geometry?: { coordinates?: number[] }
}

// Los países se buscan localmente; estado y ciudad usan Photon.
const normalize = (input: string) => input.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es').trim()
const featuredCodes = [] as string[]
export default function LocationSearch({ label, placeholder, kind, countryCode, stateName, stateBounds, value, disabled, onSelect }: Props) {
  const [text, setText] = useState(value?.label || '')
  const [highlighted, setHighlighted] = useState(0)
  const [isoStates,setIsoStates] = useState<{name:string;code:string;countryCode:string;type:string}[]>([])
  const [shown,setShown]=useState(20)
  const [cityLimit,setCityLimit]=useState(20)
  useEffect(()=>{let alive=true;setIsoStates([]);setShown(20);if(kind==='state' && countryCode) import('./subdivisions').then(data=>{if(alive)setIsoStates(data.default.filter(r=>r.countryCode===countryCode && (countryCode!=='ES' || r.type.startsWith('Autonomous'))))});return()=>{alive=false}},[kind,countryCode])
  const [items, setItems] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const selectionRequest=useRef(0)
  useEffect(()=>{selectionRequest.current++},[countryCode,stateName])
  const reference = useRef<HTMLDivElement>(null)
  useEffect(() => { if (value) { setText(value.label); setOpen(false); setHighlighted(0) } }, [value])
  useEffect(() => { if (!value) { setText(''); setOpen(false); setHighlighted(0); setItems([]); setError('') } }, [countryCode, stateName])
  const localCountries = useMemo(() => {
    if (kind !== 'country') return [] as Place[]
    const q = normalize(value && text === value.label ? '' : text)
    const matches = countries.filter(c => !q || [c.name, c.code, ...c.aliases].some(n => normalize(n).includes(q)))
    matches.sort((a, b) => {
      if (!q) return featuredCodes.indexOf(a.code) === -1 ? (featuredCodes.indexOf(b.code) === -1 ? a.name.localeCompare(b.name, 'es') : 1) : (featuredCodes.indexOf(b.code) === -1 ? -1 : featuredCodes.indexOf(a.code) - featuredCodes.indexOf(b.code))
      const ax = normalize(a.name).startsWith(q) ? 0 : 1
      const bx = normalize(b.name).startsWith(q) ? 0 : 1
      return ax - bx || a.name.localeCompare(b.name, 'es')
    })
    return matches.map(c => ({name:c.name, label:c.name, lat:c.lat, lon:c.lon, countryCode:c.code, kind:'country' as const}))
  }, [kind, text])
  const offline = useMemo(() => {
    if (kind === 'country' || !countryCode) return [] as Place[]
    const q = normalize(value && text === value.label ? '' : text)
    if(kind==='state' && isoStates.length) return isoStates.filter(r=>!q || normalize(r.name).includes(q)).slice(0,shown).map(r=>({name:r.name,label:r.name,isoCode:r.code,lon:Number.NaN,lat:Number.NaN,countryCode:r.countryCode,kind:'state' as const}))
    const source = kind === 'state' ? localStates : localCities
    return source.filter(item => item.countryCode === countryCode &&
      (kind === 'state' || !stateName || normalize(item.state || '') === normalize(stateName)) &&
      (!q || normalize(item.name).includes(q)))
      .sort((a, b) => (normalize(a.name).startsWith(q) ? 0 : 1) - (normalize(b.name).startsWith(q) ? 0 : 1) || a.name.localeCompare(b.name, 'es'))
      .slice(0, kind === 'state' ? 60 : 100).map(item => ({...item, label:item.name, kind} as Place))
  }, [kind, countryCode, stateName, text, isoStates, shown])
  const suggestions = kind === 'country' ? localCountries : [...offline, ...items.filter(item => !offline.some(local => normalize(local.name) === normalize(item.name)))].slice(0, Math.max(50,shown,cityLimit))
  const choose = async (place: Place) => {
    const sequence=++selectionRequest.current
    if(!Number.isFinite(place.lon) || place.kind==='country') {
      setBusy(true);setError('')
      try {
        const response=await geoFetch('https://photon.komoot.io/api/?'+new URLSearchParams({q:place.name,countrycode:place.countryCode,layer:place.kind==='country'?'country':'state',limit:'5'}))
        if(!response.ok)throw new Error('Geocodificador no disponible')
        const data=await response.json() as {features:PhotonFeature[]}
        const feature=data.features.find(f=>f.properties?.countrycode?.toUpperCase()===place.countryCode && f.geometry?.coordinates?.every(Number.isFinite))
        if(!feature)throw new Error('Sin geometría verificada para esta subdivisión; selecciona un área en el globo.')
        const [lon,lat]=feature.geometry!.coordinates!
        const extent=feature.properties?.extent
        place={...place,lon,lat,bbox:extent?.length===4 ? [extent[0],extent[3],extent[2],extent[1]] : undefined}
      } catch(e) {setError(e instanceof Error?e.message:'Error geográfico');return} finally {setBusy(false)}
    }
    if(sequence!==selectionRequest.current)return
    setText(place.label);setOpen(false);setHighlighted(0);onSelect(place)
  }
  useEffect(() => {
    if (kind === 'country' || !open || disabled || !countryCode || text.trim().length < 2 || text === value?.label) {
      setItems([])
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setBusy(true)
      setError('')
      try {
        const params = new URLSearchParams({ q: text.trim(), limit: String(cityLimit), lang: 'es' })
        if(stateBounds && kind==='city')params.set('bbox',stateBounds.join(','))
        {
          params.append('countrycode', countryCode!)
          if (kind === 'state') {
            params.append('layer', 'state')
          } else {
            params.append('layer', 'city')
            params.append('layer', 'locality')
          }
        }
        const response = await geoFetch('https://photon.komoot.io/api/?' + params, { signal: controller.signal })
        if (!response.ok) throw new Error('No se pudo consultar el buscador geográfico.')
        const json = await response.json() as { features?: PhotonFeature[] }
        const suggestions: Place[] = (json.features || []).flatMap((feature) => {
          const p = feature.properties
          const coords = feature.geometry?.coordinates
          if (!p?.name || !coords || !Number.isFinite(coords[0]) || !Number.isFinite(coords[1])) return []
          const val = p.type || p.osm_value || ''
          const category: Place['kind'] = ['state', 'province', 'region'].includes(val) ? 'state' : 'city'
          return [{ name: p.name, label: `${p.name}${p.state && p.state !== p.name ? ', ' + p.state : ''}`, lon: coords[0], lat: coords[1], id:p.osm_id?`${p.osm_type}/${p.osm_id}`:undefined,countryCode: (p.countrycode || '').toUpperCase(), bbox:p.extent?.length===4?[p.extent[0],p.extent[3],p.extent[2],p.extent[1]]:undefined, kind: category }]
        })
        if(controller.signal.aborted)return
        const filtered = kind === 'city' && stateName && !stateBounds
          ? suggestions.filter(item => item.label.toLocaleLowerCase('es').includes(stateName.toLocaleLowerCase('es')))
          : suggestions
        const valid=filtered.filter(item=>item.countryCode===countryCode)
        if (valid.length) {
          setItems([...new Map(valid.map(item => [item.label + item.countryCode, item])).values()].slice(0, cityLimit))
        } else {
          // Respaldo si Photon no encuentra municipios por nombre.
          const alt = await geoFetch('https://geocoding-api.open-meteo.com/v1/search?' + new URLSearchParams({name:text.trim(),count:String(cityLimit),language:'es',format:'json'}), {signal:controller.signal})
          if (alt.ok) {
            const data = await alt.json() as {results?: {name:string;latitude:number;longitude:number;country_code?:string;admin1?:string}[]}
            setItems((data.results || []).filter(x => x.country_code === countryCode && (!stateName || kind === 'state' || normalize(x.admin1 || '') === normalize(stateName))).map(x => ({name:x.name,label:x.name,lat:x.latitude,lon:x.longitude,countryCode,kind})).slice(0, cityLimit))
          } else setItems([])
        }
      } catch {
        // Respaldo de red cuando Photon no responde.
        if (!controller.signal.aborted) {
          try {
            const alt = await geoFetch('https://geocoding-api.open-meteo.com/v1/search?' + new URLSearchParams({name:text.trim(),count:String(cityLimit),language:'es',format:'json'}), {signal:controller.signal})
            if (!alt.ok) throw new Error('No disponible')
            const data = await alt.json() as {results?: {name:string;latitude:number;longitude:number;country_code?:string;admin1?:string}[]}
            setItems((data.results || []).filter(x => x.country_code === countryCode && (!stateName || kind === 'state' || normalize(x.admin1 || '') === normalize(stateName))).map(x => ({name:x.name,label:x.name,lat:x.latitude,lon:x.longitude,countryCode:countryCode!,kind})).slice(0, cityLimit))
          } catch {
            if (!controller.signal.aborted) { setItems([]); setError('Búsqueda en línea no disponible; usa las sugerencias del catálogo local.') }
          }
        }
      } finally { if (!controller.signal.aborted) setBusy(false) }
    }, 650)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [text, kind, countryCode, stateName, open, disabled, value, cityLimit, stateBounds])
  useEffect(() => {
    const outside = (event: MouseEvent) => { if (reference.current && !reference.current.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', outside)
    return () => document.removeEventListener('mousedown', outside)
  }, [])
  const clear = () => { selectionRequest.current++; setText(''); setItems([]); onSelect(null); setOpen(true) }
  return <div className="geo-field" ref={reference}>
    <label htmlFor={`geo-${kind}`}>{label}</label>
    <div className="geo-input-wrap">
      <input id={`geo-${kind}`} type="text" value={text} disabled={disabled} autoComplete="off" placeholder={placeholder}
        role="combobox" aria-autocomplete="list" aria-expanded={open && suggestions.length > 0}
        aria-controls={`geo-options-${kind}`}
        onClick={() => { if (!disabled) setOpen(true) }}
        onChange={event => { selectionRequest.current++; setText(event.target.value); setHighlighted(0); onSelect(null); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onKeyDown={event => {
          if (event.key === 'Escape') { setOpen(false); return }
          if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true); setHighlighted(i => Math.min(i + 1, suggestions.length - 1)); return }
          if (event.key === 'ArrowUp') { event.preventDefault(); setHighlighted(i => Math.max(i - 1, 0)); return }
          if (event.key === 'Enter' && open && suggestions.length) { event.preventDefault(); choose(suggestions[highlighted] || suggestions[0]) }
        }} />
      {(text || value) && <button type="button" className="geo-clear" title="Borrar selección" onClick={clear}>×</button>}
      {!disabled && <button type="button" className="geo-dropdown-toggle" title={`Mostrar ${kind === 'state' ? 'estados' : kind === 'city' ? 'ciudades y municipios' : 'países'}`} aria-label="Mostrar opciones" aria-expanded={open} onClick={() => setOpen(current => !current)}><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg></button>}
    </div>
    {open && !disabled && <div className="geo-options" id={`geo-options-${kind}`} role="listbox">
      {kind !== 'country' && busy && <p>Buscando lugares…</p>}
      {!busy && error && <p role="alert">{error}</p>}
      {kind !== 'country' && !suggestions.length && !busy && !error && <p>{countryCode === 'MX' ? 'No hay más localidades en el catálogo local. Escribe el nombre para buscar en línea.' : 'Escribe el nombre para buscar en línea. La lista completa requiere datos del servicio geográfico.'}</p>}
      {suggestions.length > 0 && <div className="geo-options-heading">{kind === 'country' ? 'Selecciona un país' : kind === 'state' ? 'Selecciona un estado o provincia' : 'Selecciona una ciudad o municipio'} · {suggestions.length} opciones</div>}
      {kind==='state' && isoStates.length>shown && <button type="button" onClick={()=>setShown(n=>n+20)}>Cargar más subdivisiones ISO</button>}
      {kind==='city' && items.length>=cityLimit && cityLimit<50 && <button type="button" onClick={()=>setCityLimit(n=>Math.min(50,n+20))}>Cargar m?s localidades</button>}
      {suggestions.map((item, index) => <button type="button" role="option" aria-selected={highlighted === index} key={`${item.label}-${item.lon}-${item.lat}`}
        onMouseDown={event => event.preventDefault()}
        onMouseEnter={() => setHighlighted(index)}
        onClick={() => choose(item)}>
        <strong>{item.name}</strong><small>{item.kind === 'country' ? '' : item.kind === 'state' ? (item.isoCode || 'Subdivision administrativa') : 'Ciudad / municipio'}{item.label !== item.name ? ' · ' + item.label.slice(item.name.length + 2) : ''}</small>
      </button>)}
    </div>}
  </div>
}
