import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'
import { Calculator, ChevronLeft, Search } from 'lucide-react'
import api from '../services/api'
import CampoFecha from '../components/CampoFecha'
import TablaDias from '../components/TablaDias'
import { hoyIso, mensajeDeError } from '../formato'
import { tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Paginado, Registro } from '../tipos'

const POR_PAGINA = 50
const ESTADOS = [
  { valor: '', texto: 'Todos' }, { valor: 'presente', texto: 'Presente' }, { valor: 'incompleto', texto: 'Incompleto' },
  { valor: 'ausente', texto: 'Ausente' }, { valor: 'franco', texto: 'Franco' }, { valor: 'feriado', texto: 'Feriado' }, { valor: 'licencia', texto: 'Licencia' },
  { valor: 'sin_horario', texto: 'Sin horario' },
]

function haceDias(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Asistencia calculada por día y empleado, con el cálculo de un período. */
export default function AsistenciaDiaria() {
  const { usuario } = useSesion()
  const [desde, setDesde] = useState(haceDias(7))
  const [hasta, setHasta] = useState(hoyIso())
  const [estado, setEstado] = useState('')
  const [buscar, setBuscar] = useState('')
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState<Paginado<Registro> | null>(null)
  const [mensaje, setMensaje] = useState<{ ok: boolean; texto: string } | null>(null)
  const [calculando, setCalculando] = useState(false)

  const cargar = useCallback(() => {
    api.get<Paginado<Registro>>('/dias-asistencia/', {
      params: { desde, hasta, estado: estado || undefined, buscar: buscar.trim() || undefined, page: pagina, por_pagina: POR_PAGINA, orden: '-fecha' },
    }).then((r) => setDatos(r.data)).catch(() => setDatos(null))
  }, [desde, hasta, estado, buscar, pagina])

  useEffect(() => {
    const t = window.setTimeout(cargar, 250)
    return () => window.clearTimeout(t)
  }, [cargar])

  const calcular = async () => {
    setCalculando(true)
    setMensaje(null)
    try {
      const r = await api.post<{ dias: number; empleados: number }>('/dias-asistencia/calcular/', { desde, hasta })
      setMensaje({ ok: true, texto: `Listo: ${r.data.dias} días calculados de ${r.data.empleados} empleados.` })
      cargar()
    } catch (err) {
      const d = axios.isAxiosError(err) ? err.response?.data as Record<string, unknown> | undefined : undefined
      const primero = d && Object.values(d).find((v) => Array.isArray(v))
      setMensaje({ ok: false, texto: Array.isArray(primero) ? String(primero[0]) : mensajeDeError(d, 'No se pudo calcular.') })
    } finally {
      setCalculando(false)
    }
  }

  return (
    <div className="space-y-4 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Link to="/" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
          <h1 className="text-xl font-bold text-stone-900 sm:text-2xl">Asistencia diaria</h1>
        </div>
        {tienePermiso(usuario, 'asistencia.calcular_asistencia') && (
          <button type="button" onClick={calcular} disabled={calculando}
            className="flex items-center gap-1 rounded-lg bg-marca-700 px-4 py-2 text-sm font-medium text-white hover:bg-marca-600 disabled:opacity-60">
            <Calculator size={16} /> {calculando ? 'Calculando…' : 'Calcular período'}
          </button>
        )}
      </div>
      <p className="text-sm text-stone-500">
        Se recalcula sola al marcar, al importar y al aprobar ajustes u horas extra. Usá <em>Calcular período</em> después de cambiar
        horarios o feriados, o para ver las ausencias de días sin marcas. Tocá un día para ver cómo se calculó.
      </p>
      <div className="flex flex-wrap gap-2">
        <label className="relative min-w-[12rem] flex-1">
          <Search size={16} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400" />
          <input type="search" placeholder="Buscar empleado…" value={buscar} onChange={(e) => { setBuscar(e.target.value); setPagina(1) }}
            className="w-full rounded-lg border border-stone-300 p-2 pl-8 focus:outline-none focus:ring-2 focus:ring-marca-600" />
        </label>
        <label className="flex items-center gap-2 text-sm text-stone-600">Desde
          <CampoFecha valor={desde} onCambio={(v) => { setDesde(v); setPagina(1) }} className="w-40" aria-label="Desde" />
        </label>
        <label className="flex items-center gap-2 text-sm text-stone-600">Hasta
          <CampoFecha valor={hasta} onCambio={(v) => { setHasta(v); setPagina(1) }} className="w-40" aria-label="Hasta" />
        </label>
        <label className="flex items-center gap-2 text-sm text-stone-600">Estado
          <select value={estado} onChange={(e) => { setEstado(e.target.value); setPagina(1) }} className="rounded-lg border border-stone-300 p-2">
            {ESTADOS.map((o) => <option key={o.valor} value={o.valor}>{o.texto}</option>)}
          </select>
        </label>
      </div>
      {mensaje && <p className={`rounded-lg px-3 py-2 text-sm ${mensaje.ok ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>{mensaje.texto}</p>}
      <TablaDias dias={datos?.results ?? []} />
      {datos && datos.count > POR_PAGINA && (
        <div className="flex items-center justify-between text-sm text-stone-600">
          <span>{datos.count} días</span>
          <div className="flex items-center gap-2">
            <button type="button" disabled={!datos.previous} onClick={() => setPagina((p) => p - 1)} className="rounded-md border border-stone-300 px-3 py-1 disabled:opacity-40">Anterior</button>
            <span>{pagina} / {Math.ceil(datos.count / POR_PAGINA)}</span>
            <button type="button" disabled={!datos.next} onClick={() => setPagina((p) => p + 1)} className="rounded-md border border-stone-300 px-3 py-1 disabled:opacity-40">Siguiente</button>
          </div>
        </div>
      )}
    </div>
  )
}
