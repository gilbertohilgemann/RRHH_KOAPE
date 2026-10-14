import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import api from '../services/api'
import { fechaLegible, mensajeDeError } from '../formato'
import type { Paginado, Registro } from '../tipos'

/** Elegir un período abierto y calcular su liquidación. */
export default function NuevaLiquidacion() {
  const navegar = useNavigate()
  const [periodos, setPeriodos] = useState<Registro[]>([])
  const [elegido, setElegido] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    api.get<Paginado<Registro>>('/periodos-nomina/', { params: { estado: 'abierto', por_pagina: 50 } })
      .then((r) => { setPeriodos(r.data.results); if (r.data.results[0]) setElegido(String(r.data.results[0].id)) })
      .catch(() => setError('No se pudieron leer los períodos.'))
  }, [])

  const [anio, setAnio] = useState(String(new Date().getFullYear()))

  const aguinaldo = async () => {
    setEnviando(true)
    setError('')
    try {
      const r = await api.post<Registro>('/corridas-nomina/aguinaldo/', { anio })
      navegar(`/nomina/liquidaciones/${r.data.id}`)
    } catch (e) {
      setError(mensajeDeError((e as { response?: { data?: unknown } }).response?.data, 'No se pudo calcular el aguinaldo.'))
    } finally {
      setEnviando(false)
    }
  }

  const calcular = async () => {
    setEnviando(true)
    setError('')
    try {
      const r = await api.post<Registro>('/corridas-nomina/', { periodo: elegido })
      navegar(`/nomina/liquidaciones/${r.data.id}`)
    } catch (e) {
      setError(mensajeDeError((e as { response?: { data?: unknown } }).response?.data, 'No se pudo calcular.'))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="max-w-xl rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <div className="mb-3 flex items-center gap-2">
        <Link to="/m/corridas-nomina" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
        <h1 className="text-xl font-bold text-stone-900">Calcular una liquidación</h1>
      </div>
      <p className="mb-3 text-sm text-stone-600">Antes de calcular, conviene tener la asistencia del período calculada y las novedades aprobadas.
        Se puede recalcular las veces que haga falta hasta aprobarla.</p>
      {periodos.length ? (
        <label className="mb-3 block text-sm font-medium text-stone-800">Período
          <select value={elegido} onChange={(e) => setElegido(e.target.value)}
            className="mt-1 w-full rounded-lg border border-stone-300 p-2 focus:outline-none focus:ring-2 focus:ring-marca-600">
            {periodos.map((p) => (
              <option key={p.id} value={p.id}>{String(p.codigo)} · {fechaLegible(String(p.fecha_desde))} al {fechaLegible(String(p.fecha_hasta))}</option>
            ))}
          </select>
        </label>
      ) : (
        <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">No hay períodos abiertos.
          {' '}<Link to="/m/periodos-nomina/nuevo?volver=/nomina/liquidar" className="underline">Crear un período</Link>.</p>
      )}
      {error && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      <button type="button" onClick={calcular} disabled={!elegido || enviando}
        className="rounded-lg bg-marca-700 px-4 py-2 text-sm font-medium text-white hover:bg-marca-600 disabled:opacity-60">
        {enviando ? 'Calculando…' : 'Calcular'}
      </button>

      <div className="mt-6 border-t border-stone-200 pt-4">
        <h2 className="mb-1 font-semibold text-stone-800">Aguinaldo</h2>
        <p className="mb-2 text-sm text-stone-600">Toma, de las nóminas cerradas del año, lo que cuenta para el aguinaldo y descuenta lo ya pagado
          (por ejemplo, en una liquidación final). Conviene cerrar antes la nómina de diciembre.</p>
        <div className="flex items-end gap-2">
          <label className="text-sm font-medium text-stone-800">Año
            <input type="number" value={anio} onChange={(e) => setAnio(e.target.value)} min="2000"
              className="mt-1 block w-28 rounded-lg border border-stone-300 p-2" />
          </label>
          <button type="button" onClick={aguinaldo} disabled={!anio || enviando}
            className="rounded-lg border border-marca-700 px-4 py-2 text-sm font-medium text-marca-800 hover:bg-marca-50 disabled:opacity-60">
            Calcular el aguinaldo
          </button>
        </div>
      </div>
    </div>
  )
}
