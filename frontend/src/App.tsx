
function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <header className="border-b border-white/10 px-6 py-5">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <span className="text-xl font-semibold tracking-tight">
            FireSight
          </span>

          <span className="text-xs text-slate-400">
            MODIS / VIIRS
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-12">
        <p className="mb-3 text-sm text-slate-400">
          NASA Earth Observation
        </p>

        <h1 className="text-3xl font-semibold tracking-tight">
          FireSight
        </h1>

        <p className="mt-4 max-w-xl text-slate-400">
          Plataforma de análisis y visualización de
          observaciones satelitales de incendios forestales.
        </p>

        <section className="mt-10 flex min-h-96 items-center justify-center rounded-xl border border-dashed border-white/20 bg-slate-900/60">
          <p className="text-sm text-slate-400">
            Espacio reservado para el globo 3D
          </p>
        </section>
      </main>
    </div>
  )
}

export default App
