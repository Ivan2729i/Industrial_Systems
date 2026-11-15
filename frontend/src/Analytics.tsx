
import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet } from './data'
import './Analytics.css'

type AnalyticsProps = {
  onBack: () => void
}

type SensorFilter = 'all' | 'modis' | 'viirs'

type Availability = {
  min_date: string
  max_date: string
}

export default function Analytics({ onBack }: AnalyticsProps) {
  const [sensor, setSensor] = useState<SensorFilter>('all')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const todayUTC = new Date().toISOString().slice(0, 10)

  // Consultamos la disponibilidad real de NASA.
  const modisQuery = useQuery({
    queryKey: ['analytics-availability', 'modis'],
    queryFn: ({ signal }) =>
      apiGet<Availability>(
        '/v1/detections/availability/?sensor=modis',
        signal
      ),
    staleTime: 60 * 60 * 1000,
    retry: false,
  })

  const viirsQuery = useQuery({
    queryKey: ['analytics-availability', 'viirs'],
    queryFn: ({ signal }) =>
      apiGet<Availability>(
        '/v1/detections/availability/?sensor=viirs',
        signal
      ),
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

    if (sources.some(source =>
      !source?.min_date || !source?.max_date
    )) {
      return null
    }

    const valid = sources as Availability[]

    // En "Ambos", usamos la unión de las fechas disponibles.
    const min = valid
      .map(source => source.min_date)
      .sort()[0]

    const latestNASA = valid
      .map(source => source.max_date)
      .sort()
      .at(-1)!

    // Nunca permitir fechas posteriores al día UTC actual.
    const max = latestNASA < todayUTC ? latestNASA : todayUTC

    if (min > max) return null

    return { min, max }
  }, [sensor, modisQuery.data, viirsQuery.data, todayUTC])

  // Inicializar y ajustar las fechas dentro del rango permitido.
  useEffect(() => {
    if (!dateBounds) return

    const clamp = (date: string) => {
      if (!date) return dateBounds.max
      if (date < dateBounds.min) return dateBounds.min
      if (date > dateBounds.max) return dateBounds.max
      return date
    }

    setStartDate(previous => clamp(previous))
    setEndDate(previous => clamp(previous))
  }, [dateBounds])

  const validRange = Boolean(
    dateBounds &&
    startDate &&
    endDate &&
    startDate >= dateBounds.min &&
    endDate <= dateBounds.max &&
    startDate <= endDate
  )

  const changeStartDate = (value: string) => {
    if (!dateBounds) return
    if (value && (value < dateBounds.min || value > dateBounds.max)) return

    setStartDate(value)

    if (value && endDate && value > endDate) {
      setEndDate(value)
    }
  }

  const changeEndDate = (value: string) => {
    if (!dateBounds) return
    if (value && (value < dateBounds.min || value > dateBounds.max)) return

    setEndDate(value)

    if (value && startDate && value < startDate) {
      setStartDate(value)
    }
  }

  return (
    <main className="analytics-page">
      <header className="analytics-header">
        <div>
          <p className="analytics-eyebrow">
            TERRAFLARE / ANALÍTICA
          </p>

          <h1>Analítica satelital</h1>

          <p>
            Explora y compara las observaciones de MODIS,
            VIIRS y los resultados armonizados.
          </p>
        </div>

        <button
          type="button"
          onClick={onBack}
          className="analytics-back"
        >
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
              onChange={event =>
                setSensor(event.target.value as SensorFilter)
              }
            >
              <option value="all">MODIS y VIIRS</option>
              <option value="modis">MODIS</option>
              <option value="viirs">VIIRS</option>
            </select>
          </label>

          <label>
            Desde (UTC)
            <input
              type="date"
              value={startDate}
              min={dateBounds?.min}
              max={endDate || dateBounds?.max}
              disabled={!dateBounds}
              onChange={event =>
                changeStartDate(event.target.value)
              }
            />
          </label>

          <label>
            Hasta (UTC)
            <input
              type="date"
              value={endDate}
              min={startDate || dateBounds?.min}
              max={dateBounds?.max}
              disabled={!dateBounds}
              onChange={event =>
                changeEndDate(event.target.value)
              }
            />
          </label>
        </div>

        {availabilityError ? (
          <p className="analytics-note" role="alert">
            No fue posible consultar la disponibilidad NASA.
            Comprueba la conexión con Django.
          </p>
        ) : !dateBounds ? (
          <p className="analytics-note">
            Consultando fechas disponibles...
          </p>
        ) : (
          <>
            <p className="analytics-note">
              Disponibilidad: {dateBounds.min} al {dateBounds.max} UTC
            </p>

            <p className="analytics-note">
              {validRange
                ? `Período seleccionado: ${startDate} al ${endDate}`
                : 'Selecciona un período válido.'}
            </p>

            {sensor === 'all' && (
              <p className="analytics-note">
                Cada sensor tiene su propio período de cobertura.
                Las fechas anteriores al inicio de VIIRS
                únicamente pueden contener observaciones MODIS.
              </p>
            )}
          </>
        )}
      </section>

      <section className="analytics-panel">
        <h2>Resumen de observaciones</h2>
        <div className="analytics-empty">
          Los indicadores reales se conectarán
          con PostgreSQL en el siguiente paso.
        </div>
      </section>

      <section className="analytics-panel">
        <h2>Evolución temporal</h2>
        <div className="analytics-empty">
          Aquí se mostrarán las detecciones por día.
        </div>
      </section>

      <section className="analytics-panel">
        <h2>Comparación de sensores</h2>
        <div className="analytics-empty">
          Comparación de observaciones MODIS,
          VIIRS y resultados armonizados.
        </div>
      </section>
    </main>
  )
}
