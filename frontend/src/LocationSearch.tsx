import { useEffect, useMemo, useRef, useState } from 'react'
import { countries } from './countries'
import { localCities, localStates } from './localPlaces'

export type Place = { name: string; label: string; lon: number; lat: number; countryCode: string; kind: 'country' | 'state' | 'city' }

type Props = {
  label: string
  placeholder: string
  kind: 'country' | 'state' | 'city'
  countryCode?: string
  stateName?: string
  value: Place | null
  disabled?: boolean
  onSelect: (place: Place | null) => void
}

type PhotonFeature = {
  properties?: { name?: string; country?: string; state?: string; countrycode?: string; type?: string; osm_value?: string }
  geometry?: { coordinates?: number[] }
}

// Los países se buscan localmente; estado y ciudad usan Photon.
const normalize = (input: string) => input.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es').trim()
const featuredCodes = ['MX', 'US', 'CA', 'GT', 'CO', 'AR', 'ES', 'BR']
export default function LocationSearch({ label, placeholder, kind, countryCode, stateName, value, disabled, onSelect }: Props) {
  const [text, setText] = useState(value?.label || '')
  const [highlighted, setHighlighted] = useState(0)
  const [items, setItems] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
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
    return matches.slice(0, 10).map(c => ({name:c.name, label:c.name, lat:c.lat, lon:c.lon, countryCode:c.code, kind:'country' as const}))
  }, [kind, text])
  const offline = useMemo(() => {
    if (kind === 'country' || !countryCode) return [] as Place[]
    const q = normalize(value && text === value.label ? '' : text)
    const source = kind === 'state' ? localStates : localCities
    return source.filter(item => item.countryCode === countryCode &&
      (kind === 'state' || !stateName || normalize(item.state || '') === normalize(stateName)) &&
      (!q || normalize(item.name).includes(q)))
      .sort((a, b) => (normalize(a.name).startsWith(q) ? 0 : 1) - (normalize(b.name).startsWith(q) ? 0 : 1) || a.name.localeCompare(b.name, 'es'))
      .slice(0, kind === 'state' ? 60 : 100).map(item => ({...item, label:item.name, kind} as Place))
  }, [kind, countryCode, stateName, text])
  const suggestions = kind === 'country' ? localCountries : [...offline, ...items.filter(item => !offline.some(local => normalize(local.name) === normalize(item.name)))].slice(0, 50)
  const choose = (place: Place) => { setText(place.label); setOpen(false); setHighlighted(0); onSelect(place) }
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
        const params = new URLSearchParams({ q: text.trim(), limit: '12', lang: 'es' })
        {
          params.append('countrycode', countryCode!)
          if (kind === 'state') {
            params.append('layer', 'state')
          } else {
            params.append('layer', 'city')
            params.append('layer', 'locality')
          }
        }
        const response = await fetch('https://photon.komoot.io/api/?' + params, { signal: controller.signal })
        if (!response.ok) throw new Error('No se pudo consultar el buscador geográfico.')
        const json = await response.json() as { features?: PhotonFeature[] }
        const suggestions: Place[] = (json.features || []).flatMap((feature) => {
          const p = feature.properties
          const coords = feature.geometry?.coordinates
          if (!p?.name || !coords || !Number.isFinite(coords[0]) || !Number.isFinite(coords[1])) return []
          const val = p.type || p.osm_value || ''
          const category: Place['kind'] = ['state', 'province', 'region'].includes(val) ? 'state' : 'city'
          return [{ name: p.name, label: `${p.name}${p.state && p.state !== p.name ? ', ' + p.state : ''}`, lon: coords[0], lat: coords[1], countryCode: (p.countrycode || '').toUpperCase(), kind: category }]
        })
        const filtered = kind === 'city' && stateName
          ? suggestions.filter(item => item.label.toLocaleLowerCase('es').includes(stateName.toLocaleLowerCase('es')))
          : suggestions
        if (filtered.length) {
          setItems([...new Map(filtered.map(item => [item.label + item.countryCode, item])).values()].slice(0, 8))
        } else {
          // Respaldo si Photon no encuentra municipios por nombre.
          const alt = await fetch('https://geocoding-api.open-meteo.com/v1/search?' + new URLSearchParams({name:text.trim(),count:'15',language:'es',format:'json'}), {signal:controller.signal})
          if (alt.ok) {
            const data = await alt.json() as {results?: {name:string;latitude:number;longitude:number;country_code?:string;admin1?:string}[]}
            setItems((data.results || []).filter(x => x.country_code === countryCode && (!stateName || kind === 'state' || normalize(x.admin1 || '') === normalize(stateName))).map(x => ({name:x.name,label:x.name,lat:x.latitude,lon:x.longitude,countryCode,kind})).slice(0, 8))
          } else setItems([])
        }
      } catch {
        // Respaldo de red cuando Photon no responde.
        if (!controller.signal.aborted) {
          try {
            const alt = await fetch('https://geocoding-api.open-meteo.com/v1/search?' + new URLSearchParams({name:text.trim(),count:'15',language:'es',format:'json'}), {signal:controller.signal})
            if (!alt.ok) throw new Error('No disponible')
            const data = await alt.json() as {results?: {name:string;latitude:number;longitude:number;country_code?:string;admin1?:string}[]}
            setItems((data.results || []).filter(x => x.country_code === countryCode && (!stateName || kind === 'state' || normalize(x.admin1 || '') === normalize(stateName))).map(x => ({name:x.name,label:x.name,lat:x.latitude,lon:x.longitude,countryCode:countryCode!,kind})).slice(0, 8))
          } catch {
            if (!controller.signal.aborted) { setItems([]); setError('Búsqueda en línea no disponible; usa las sugerencias del catálogo local.') }
          }
        }
      } finally { if (!controller.signal.aborted) setBusy(false) }
    }, 650)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [text, kind, countryCode, stateName, open, disabled, value])
  useEffect(() => {
    const outside = (event: MouseEvent) => { if (reference.current && !reference.current.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', outside)
    return () => document.removeEventListener('mousedown', outside)
  }, [])
  const clear = () => { setText(''); setItems([]); onSelect(null); setOpen(true) }
  return <div className="geo-field" ref={reference}>
    <label htmlFor={`geo-${kind}`}>{label}</label>
    <div className="geo-input-wrap">
      <input id={`geo-${kind}`} type="text" value={text} disabled={disabled} autoComplete="off" placeholder={placeholder}
        role="combobox" aria-autocomplete="list" aria-expanded={open && suggestions.length > 0}
        aria-controls={`geo-options-${kind}`}
        onClick={() => { if (!disabled) setOpen(true) }}
        onChange={event => { setText(event.target.value); setHighlighted(0); onSelect(null); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onKeyDown={event => {
          if (event.key === 'Escape') { setOpen(false); return }
          if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true); setHighlighted(i => Math.min(i + 1, suggestions.length - 1)); return }
          if (event.key === 'ArrowUp') { event.preventDefault(); setHighlighted(i => Math.max(i - 1, 0)); return }
          if (event.key === 'Enter' && open && suggestions.length) { event.preventDefault(); choose(suggestions[highlighted] || suggestions[0]) }
        }} />
      {(text || value) && <button type="button" className="geo-clear" title="Borrar selección" onClick={clear}>×</button>}
      {!disabled && <button type="button" className="geo-dropdown-toggle" title={`Mostrar ${kind === 'state' ? 'estados' : kind === 'city' ? 'ciudades y municipios' : 'países'}`} aria-label="Mostrar opciones" aria-expanded={open} onClick={() => setOpen(current => !current)}>⌄</button>}
    </div>
    {open && !disabled && <div className="geo-options" id={`geo-options-${kind}`} role="listbox">
      {kind !== 'country' && busy && <p>Buscando lugares…</p>}
      {kind !== 'country' && !busy && error && !suggestions.length && <p>{error}</p>}
      {kind !== 'country' && !suggestions.length && !busy && !error && <p>{countryCode === 'MX' ? 'No hay más localidades en el catálogo local. Escribe el nombre para buscar en línea.' : 'Escribe el nombre para buscar en línea. La lista completa requiere datos del servicio geográfico.'}</p>}
      {suggestions.length > 0 && <div className="geo-options-heading">{kind === 'country' ? 'Selecciona un país' : kind === 'state' ? 'Selecciona un estado o provincia' : 'Selecciona una ciudad o municipio'} · {suggestions.length} opciones</div>}
      {suggestions.map((item, index) => <button type="button" role="option" aria-selected={highlighted === index} key={`${item.label}-${item.lon}-${item.lat}`}
        onMouseDown={event => event.preventDefault()}
        onMouseEnter={() => setHighlighted(index)}
        onClick={() => choose(item)}>
        <strong>{item.name}</strong><small>{item.kind === 'country' ? `País · ${item.countryCode}` : item.kind === 'state' ? 'Estado / provincia' : 'Ciudad / municipio'}{item.label !== item.name ? ' · ' + item.label.slice(item.name.length + 2) : ''}</small>
      </button>)}
    </div>}
  </div>
}
