import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import api from '../services/api'
import CampoFecha from '../components/CampoFecha'
import { guaranies } from '../formato'

interface Fila {
  grupo: string
  bruto: string
  aportes_patronales: string
  otros_costos: string
  costo_total: string
  provision_aguinaldo: string
}

const AGRUPAR = [['centro_costo', 'Centro de costo'], ['departamento', 'Departamento'], ['sucursal', 'Sucursal'], ['empleado', 'Empleado']]

/** Costo del empleador de las liquidaciones cerradas (§12). La provisión de aguinaldo es una estimación aparte: no suma al total. */
export default function CostoPatronal() {
  const ahora = new Date()
  const [desde, setDesde] = useState(`${ahora.getFullYear()}-01-01`)
  const [hasta, setHasta] = useState(`${ahora.getFullYear()}-12-31`)
  const [agrupar, setAgrupar] = useState('centro_costo')
  const [datos, setDatos] = useState<{ filas: Fila[]; totales: Record<string, string | null> } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/costo-patronal/', { params: { desde, hasta, agrupar } })
      .then((r) => { setDatos(r.data); setError('') }).catch(() => setError('No se pudo leer el costo.'))
  }, [desde, hasta, agrupar])

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <div className="mb-3 flex items-center gap-2">
        <Link to="/" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
        <h1 className="text-xl font-bold text-stone-900">Costo del empleador</h1>
      </div>
      <p className="mb-3 text-sm text-stone-600">De las liquidaciones cerradas (si una se rectificó, cuenta la rectificación). Costo = remuneración bruta +
        aportes del empleador + otros costos. La provisión de aguinaldo es una estimación y se muestra aparte, sin sumarla.</p>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <label className="text-sm font-medium text-stone-800">Desde<CampoFecha valor={desde} onCambio={setDesde} className="mt-1 w-40" /></label>
        <label className="text-sm font-medium text-stone-800">Hasta<CampoFecha valor={hasta} onCambio={setHasta} className="mt-1 w-40" /></label>
        <label className="text-sm font-medium text-stone-800">Agrupar por
          <select value={agrupar} onChange={(e) => setAgrupar(e.target.value)} className="mt-1 block rounded-lg border border-stone-300 p-2">
            {AGRUPAR.map(([valor, texto]) => <option key={valor} value={valor}>{texto}</option>)}
          </select>
        </label>
      </div>
      {error && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      <div className="overflow-x-auto rounded-lg border border-stone-200">
        <table className="w-full min-w-max text-sm">
          <thead className="bg-marca-50 text-left text-stone-700">
            <tr>
              <th className="px-2 py-1.5">{AGRUPAR.find(([v]) => v === agrupar)?.[1]}</th><th className="px-2 py-1.5 text-right">Bruto</th>
              <th className="px-2 py-1.5 text-right">Aportes empleador</th><th className="px-2 py-1.5 text-right">Otros</th>
              <th className="px-2 py-1.5 text-right">Costo total</th><th className="px-2 py-1.5 text-right text-stone-500">Provisión aguinaldo</th>
            </tr>
          </thead>
          <tbody>
            {datos?.filas.map((f) => (
              <tr key={f.grupo} className="border-t border-stone-100">
                <td className="px-2 py-1.5">{f.grupo}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{guaranies(f.bruto)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{guaranies(f.aportes_patronales)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{guaranies(f.otros_costos)}</td>
                <td className="px-2 py-1.5 text-right font-semibold tabular-nums">{guaranies(f.costo_total)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums text-stone-500">{guaranies(f.provision_aguinaldo)}</td>
              </tr>
            ))}
            {datos && datos.filas.length === 0 && (
              <tr><td colSpan={6} className="px-2 py-6 text-center text-stone-500">No hay liquidaciones cerradas en esas fechas.</td></tr>
            )}
          </tbody>
          {datos && datos.filas.length > 0 && (
            <tfoot className="border-t border-stone-300 font-semibold">
              <tr>
                <td className="px-2 py-1.5">Total</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{guaranies(datos.totales.bruto)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{guaranies(datos.totales.aportes)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{guaranies(datos.totales.otros)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{guaranies(datos.totales.total)}</td>
                <td className="px-2 py-1.5 text-right tabular-nums text-stone-500">{guaranies(datos.totales.provision)}</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  )
}
