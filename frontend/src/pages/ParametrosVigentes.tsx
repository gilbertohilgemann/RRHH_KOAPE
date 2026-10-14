import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ChevronLeft } from 'lucide-react'
import api from '../services/api'
import CampoFecha from '../components/CampoFecha'
import { hoyIso } from '../formato'

interface Detalle {
  codigo: string
  nombre: string
  valor: string
  referencia: string
  conjunto: string
  conjunto_id: number
  estado: string
  global: boolean
}

interface Respuesta {
  detalle: Detalle[]
  advertencias: string[]
}

/** Qué valor legal rige en una fecha para la empresa y de qué conjunto sale.
 * Sin "simular" solo aparecen los aprobados: son los únicos que valen para liquidar. */
export default function ParametrosVigentes() {
  const [fecha, setFecha] = useState(hoyIso())
  const [simulacion, setSimulacion] = useState(false)
  const [datos, setDatos] = useState<Respuesta | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!fecha) return
    api.get<Respuesta>('/reglas-legales/vigentes/', { params: { fecha, simulacion } })
      .then((r) => { setDatos(r.data); setError('') })
      .catch(() => setError('No se pudieron leer los parámetros.'))
  }, [fecha, simulacion])

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <div className="mb-3 flex items-center gap-2">
        <Link to="/m/reglas-legales" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
        <h1 className="text-xl font-bold text-stone-900">Parámetros legales vigentes</h1>
      </div>
      <p className="mb-3 text-sm text-stone-600">Los valores que rigen en la fecha elegida para tu empresa. Si la empresa tiene reglas propias aprobadas,
        tienen prioridad sobre las de Koape. Solo los <strong>aprobados</strong> valen para liquidar.</p>
      <div className="mb-3 flex flex-wrap items-end gap-4">
        <label className="text-sm font-medium text-stone-800">Fecha
          <CampoFecha valor={fecha} onCambio={setFecha} className="mt-1 w-44" />
        </label>
        <label className="flex items-center gap-2 text-sm text-stone-700">
          <input type="checkbox" checked={simulacion} onChange={(e) => setSimulacion(e.target.checked)} className="h-4 w-4 accent-marca-700" />
          Simular: incluir borradores y revisados
        </label>
      </div>
      {error && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      {datos?.advertencias.map((a) => (
        <p key={a} className="mb-2 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900"><AlertTriangle size={16} className="mt-0.5 shrink-0" />{a}</p>
      ))}
      <div className="overflow-x-auto rounded-lg border border-stone-200">
        <table className="w-full min-w-max text-sm">
          <thead className="bg-marca-50 text-left text-stone-700">
            <tr>
              <th className="px-2 py-1.5">Código</th><th className="px-2 py-1.5">Parámetro</th><th className="px-2 py-1.5 text-right">Valor</th>
              <th className="px-2 py-1.5">Sale de</th><th className="px-2 py-1.5">Referencia</th>
            </tr>
          </thead>
          <tbody>
            {datos?.detalle.map((d) => (
              <tr key={d.codigo} className={`border-t border-stone-100 ${d.estado === 'aprobado' ? '' : 'bg-amber-50/60'}`}>
                <td className="px-2 py-1.5 font-mono text-xs">{d.codigo}</td>
                <td className="px-2 py-1.5">{d.nombre}</td>
                <td className="px-2 py-1.5 text-right font-medium tabular-nums">{d.valor}</td>
                <td className="px-2 py-1.5">
                  <Link to={`/m/reglas-legales/${d.conjunto_id}`} className="text-marca-800 underline">{d.conjunto}</Link>
                  {d.estado !== 'aprobado' && <span className="ml-1 text-xs text-amber-800">({d.estado})</span>}
                </td>
                <td className="px-2 py-1.5 text-xs text-stone-600">{d.referencia}</td>
              </tr>
            ))}
            {datos && datos.detalle.length === 0 && (
              <tr><td colSpan={5} className="px-2 py-6 text-center text-stone-500">
                Ningún parámetro aprobado rige en esa fecha. Hasta que se aprueben, la nómina real queda bloqueada (se puede simular).
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
