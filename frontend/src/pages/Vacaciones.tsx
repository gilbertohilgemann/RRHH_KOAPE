import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronLeft, ListOrdered, Plus, RefreshCw } from 'lucide-react'
import api from '../services/api'
import { fechaLegible } from '../formato'
import { tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'

interface Saldo {
  empleado: number
  codigo: string
  nombre: string
  fecha_ingreso: string
  saldo: string | number
  pendiente_de_aprobar: string | number
  proximo_aniversario: string
}

/** Saldo de vacaciones de cada empleado, con el devengo anual y los ajustes. */
export default function Vacaciones() {
  const { usuario } = useSesion()
  const navegar = useNavigate()
  const [saldos, setSaldos] = useState<Saldo[]>([])
  const [buscar, setBuscar] = useState('')
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const cargar = useCallback(() => {
    api.get<Saldo[]>('/movimientos-vacaciones/saldos/', { params: { buscar } })
      .then((r) => setSaldos(r.data)).catch(() => setError('No se pudieron leer los saldos.'))
  }, [buscar])

  useEffect(() => {
    const espera = setTimeout(cargar, 250)
    return () => clearTimeout(espera)
  }, [cargar])

  const devengar = async () => {
    if (!window.confirm('¿Generar el devengo de vacaciones de los aniversarios del último año que todavía no lo tengan? Usa la escala por antigüedad.')) return
    setEnviando(true)
    setError('')
    try {
      const r = await api.post<{ creados: number }>('/movimientos-vacaciones/devengar/', {})
      setMensaje(r.data.creados ? `Se generaron ${r.data.creados} devengos.` : 'No había aniversarios pendientes de devengar.')
      cargar()
    } catch {
      setError('No se pudo generar el devengo.')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Link to="/" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
          <h1 className="text-xl font-bold text-stone-900">Saldo de vacaciones</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/m/vacaciones" className="flex items-center gap-1 rounded-lg border border-stone-300 px-3 py-2 text-sm hover:bg-stone-50">
            <ListOrdered size={16} /> Movimientos
          </Link>
          {tienePermiso(usuario, 'licencias.add_movimientovacaciones') && (
            <Link to="/m/vacaciones/nuevo?volver=/vacaciones" className="flex items-center gap-1 rounded-lg border border-marca-700 px-3 py-2 text-sm font-medium text-marca-800 hover:bg-marca-50">
              <Plus size={16} /> Ajuste
            </Link>
          )}
          {tienePermiso(usuario, 'licencias.devengar_vacaciones') && (
            <button type="button" onClick={devengar} disabled={enviando}
              className="flex items-center gap-1 rounded-lg bg-marca-700 px-3 py-2 text-sm font-medium text-white hover:bg-marca-800 disabled:opacity-50">
              <RefreshCw size={16} /> Generar devengo anual
            </button>
          )}
        </div>
      </div>
      <p className="mb-3 text-sm text-stone-600">El saldo es la suma de los movimientos: devengo por aniversario (según la escala), días tomados al aprobar
        vacaciones, ajustes y correcciones. Tocá un empleado para ver su legajo.</p>
      {mensaje && <p className="mb-3 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">{mensaje}</p>}
      {error && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      <input value={buscar} onChange={(e) => setBuscar(e.target.value)} placeholder="Buscar por código o nombre"
        className="mb-3 w-full max-w-sm rounded-lg border border-stone-300 px-3 py-2 text-sm" />
      <div className="overflow-x-auto rounded-lg border border-stone-200">
        <table className="w-full min-w-max text-sm">
          <thead className="bg-marca-50 text-left text-stone-700">
            <tr>
              <th className="px-2 py-1.5">Código</th><th className="px-2 py-1.5">Empleado</th><th className="px-2 py-1.5">Ingreso</th>
              <th className="px-2 py-1.5 text-right">Saldo (días)</th><th className="px-2 py-1.5 text-right">Pedidos sin aprobar</th>
              <th className="px-2 py-1.5">Próximo aniversario</th>
            </tr>
          </thead>
          <tbody>
            {saldos.map((s) => (
              <tr key={s.empleado} onClick={() => navegar(`/m/empleados/${s.empleado}`)} className="cursor-pointer border-t border-stone-100 hover:bg-marca-50/60">
                <td className="px-2 py-1.5">{s.codigo}</td>
                <td className="px-2 py-1.5">{s.nombre}</td>
                <td className="px-2 py-1.5">{fechaLegible(s.fecha_ingreso)}</td>
                <td className={`px-2 py-1.5 text-right font-medium tabular-nums ${Number(s.saldo) < 0 ? 'text-red-700' : ''}`}>{Number(s.saldo)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{Number(s.pendiente_de_aprobar) || '—'}</td>
                <td className="px-2 py-1.5">{fechaLegible(s.proximo_aniversario)}</td>
              </tr>
            ))}
            {saldos.length === 0 && <tr><td colSpan={6} className="px-2 py-6 text-center text-stone-500">Sin empleados.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
