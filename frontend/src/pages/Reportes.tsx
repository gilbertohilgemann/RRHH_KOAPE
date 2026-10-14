import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft, Download } from 'lucide-react'
import api from '../services/api'
import CampoFecha from '../components/CampoFecha'
import { descargarArchivo } from '../descargas'
import { fechaLegible, guaranies, mensajeDeError } from '../formato'

interface Columna { campo: string; etiqueta: string }
interface Definicion { clave: string; titulo: string; descripcion: string; filtros: string[]; columnas: Columna[] }

const MONTOS = /(bruto|descuentos|aportes|neto|total|salario|monto|saldo|computable|devengado|pagado)$/
const FECHA = /^\d{4}-\d{2}-\d{2}(T.*)?$/

function celda(campo: string, valor: unknown): string {
  if (valor === null || valor === undefined || valor === '') return '—'
  if (typeof valor === 'string' && FECHA.test(valor)) return fechaLegible(valor.slice(0, 10))
  // Importes con separador de miles; los saldos chicos (ej. días de vacaciones) quedan como están.
  if (MONTOS.test(campo) && !Number.isNaN(Number(valor)) && Math.abs(Number(valor)) >= 1000) return guaranies(valor)
  return typeof valor === 'string' && !Number.isNaN(Number(valor)) && valor.includes('.') ? String(Number(valor)) : String(valor)
}

/** Reportes de §12 con filtros, vista previa y exportación a CSV o Excel (protegida contra fórmulas). */
export default function Reportes() {
  const ahora = new Date()
  const [reportes, setReportes] = useState<Definicion[]>([])
  const [clave, setClave] = useState('')
  const [filtros, setFiltros] = useState<Record<string, string>>({
    desde: `${ahora.getFullYear()}-01-01`, hasta: `${ahora.getFullYear()}-12-31`, anio: String(ahora.getFullYear()), dias: '30', estado: '',
  })
  const [filas, setFilas] = useState<Record<string, unknown>[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get<Definicion[]>('/reportes/').then((r) => { setReportes(r.data); if (r.data[0]) setClave(r.data[0].clave) }).catch(() => setReportes([]))
  }, [])

  const actual = reportes.find((r) => r.clave === clave)
  const parametros = () => Object.fromEntries((actual?.filtros ?? []).map((f) => [f, filtros[f]]).filter(([, v]) => v))

  useEffect(() => {
    if (!actual) return
    setFilas(null)
    api.get<{ filas: Record<string, unknown>[] }>(`/reportes/${actual.clave}/`, { params: parametros() })
      .then((r) => { setFilas(r.data.filas); setError('') })
      .catch((e) => setError(mensajeDeError(e.response?.data, 'No se pudo generar el reporte.')))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clave, filtros])

  const exportar = (formato: string) => {
    if (!actual) return
    const consulta = new URLSearchParams({ ...parametros(), formato }).toString()
    descargarArchivo(`/reportes/${actual.clave}/?${consulta}`, `${actual.clave}.${formato}`)
      .catch(() => setError('No se pudo exportar.'))
  }

  const cambiar = (campo: string, valor: string) => setFiltros({ ...filtros, [campo]: valor })

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <div className="mb-3 flex items-center gap-2">
        <Link to="/" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
        <h1 className="text-xl font-bold text-stone-900">Reportes</h1>
      </div>
      {reportes.length === 0 ? <p className="text-sm text-stone-500">No tenés reportes disponibles.</p> : (
        <>
          <div className="mb-3 flex flex-wrap items-end gap-3">
            <label className="text-sm font-medium text-stone-800">Reporte
              <select value={clave} onChange={(e) => setClave(e.target.value)} className="mt-1 block rounded-lg border border-stone-300 p-2">
                {reportes.map((r) => <option key={r.clave} value={r.clave}>{r.titulo}</option>)}
              </select>
            </label>
            {actual?.filtros.includes('desde') && (
              <label className="text-sm font-medium text-stone-800">Desde<CampoFecha valor={filtros.desde} onCambio={(v) => cambiar('desde', v)} className="mt-1 w-40" /></label>
            )}
            {actual?.filtros.includes('hasta') && (
              <label className="text-sm font-medium text-stone-800">Hasta<CampoFecha valor={filtros.hasta} onCambio={(v) => cambiar('hasta', v)} className="mt-1 w-40" /></label>
            )}
            {actual?.filtros.includes('anio') && (
              <label className="text-sm font-medium text-stone-800">Año
                <input type="number" value={filtros.anio} onChange={(e) => cambiar('anio', e.target.value)} className="mt-1 block w-28 rounded-lg border border-stone-300 p-2" />
              </label>
            )}
            {actual?.filtros.includes('dias') && (
              <label className="text-sm font-medium text-stone-800">Próximos días
                <input type="number" value={filtros.dias} onChange={(e) => cambiar('dias', e.target.value)} className="mt-1 block w-28 rounded-lg border border-stone-300 p-2" />
              </label>
            )}
            {actual?.filtros.includes('estado') && (
              <label className="text-sm font-medium text-stone-800">Estado
                <select value={filtros.estado} onChange={(e) => cambiar('estado', e.target.value)} className="mt-1 block rounded-lg border border-stone-300 p-2">
                  <option value="">Todos</option><option value="activo">Activos</option><option value="suspendido">Suspendidos</option><option value="baja">Bajas</option>
                </select>
              </label>
            )}
            <div className="flex gap-2">
              {['csv', 'xlsx'].map((f) => (
                <button key={f} type="button" onClick={() => exportar(f)}
                  className="flex items-center gap-1 rounded-lg bg-marca-700 px-3 py-2 text-sm font-medium text-white hover:bg-marca-600">
                  <Download size={16} /> {f === 'csv' ? 'CSV' : 'Excel'}
                </button>
              ))}
            </div>
          </div>
          {actual?.descripcion && <p className="mb-3 text-sm text-stone-600">{actual.descripcion}</p>}
          {error && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
          <div className="overflow-x-auto rounded-lg border border-stone-200">
            <table className="w-full min-w-max text-sm">
              <thead className="bg-marca-50 text-left text-stone-700">
                <tr>{actual?.columnas.map((c) => <th key={c.campo} className="px-2 py-1.5">{c.etiqueta}</th>)}</tr>
              </thead>
              <tbody>
                {filas?.map((f, i) => (
                  <tr key={i} className="border-t border-stone-100">
                    {actual?.columnas.map((c) => (
                      <td key={c.campo} className={`px-2 py-1.5 ${typeof f[c.campo] === 'number' || MONTOS.test(c.campo) ? 'text-right tabular-nums' : ''}`}>
                        {celda(c.campo, f[c.campo])}
                      </td>
                    ))}
                  </tr>
                ))}
                {filas && filas.length === 0 && (
                  <tr><td colSpan={actual?.columnas.length ?? 1} className="px-2 py-6 text-center text-stone-500">Sin datos con esos filtros.</td></tr>
                )}
                {!filas && <tr><td className="px-2 py-6 text-stone-500">Cargando…</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
