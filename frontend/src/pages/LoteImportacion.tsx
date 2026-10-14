import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, FileSpreadsheet, FileText } from 'lucide-react'
import api from '../services/api'
import AccionesRegistro from '../components/AccionesRegistro'
import { buscarModulo } from '../modulos'
import { descargarArchivo } from '../descargas'
import { fechaHoraLegible } from '../formato'
import type { Paginado, Registro } from '../tipos'

const ESTADOS_FILA = [
  { valor: '', texto: 'Todas' }, { valor: 'valida', texto: 'Válidas' },
  { valor: 'rechazada', texto: 'Rechazadas' }, { valor: 'duplicada', texto: 'Duplicadas' },
]
const COLOR_FILA: Record<string, string> = { rechazada: 'bg-red-50', duplicada: 'bg-stone-100 text-stone-500' }

/** Resultado de validar un archivo: resumen, cada fila con su motivo,
 * descarga de las no importadas y las acciones (confirmar, cancelar, revertir). */
export default function LoteImportacion() {
  const { id } = useParams()
  const modulo = buscarModulo('importaciones')!
  const [lote, setLote] = useState<Registro | null>(null)
  const [filas, setFilas] = useState<Paginado<Registro> | null>(null)
  const [estado, setEstado] = useState('')
  const [pagina, setPagina] = useState(1)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    api.get<Registro>(`/importaciones/${id}/`).then((r) => setLote(r.data)).catch(() => setLote(null))
  }, [id, version])

  const cargarFilas = useCallback(() => {
    api.get<Paginado<Registro>>('/filas-importacion/', { params: { lote: id, estado: estado || undefined, page: pagina, por_pagina: 50 } })
      .then((r) => setFilas(r.data)).catch(() => setFilas(null))
  }, [id, estado, pagina])
  useEffect(() => { cargarFilas() }, [cargarFilas, version])

  if (!lote) return <p className="rounded-xl bg-white p-6">Cargando… <Link to="/m/importaciones" className="underline">Volver</Link></p>
  const numero = (campo: string) => Number(lote[campo] ?? 0)
  const hayErrores = numero('rechazadas') + numero('duplicadas') > 0

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <div className="mb-3 flex items-center gap-2">
          <Link to="/m/importaciones" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
          <h1 className="text-xl font-bold text-stone-900 sm:text-2xl">Importación {String(lote.id)} · {String(lote.nombre_archivo)}</h1>
        </div>
        <p className="mb-4 text-sm text-stone-600">
          {String(lote.estado_texto)} · subido el {fechaHoraLegible(String(lote.creado))} por {String(lote.creado_por ?? '')}
          {' · '}perfil {String(lote.perfil_texto)} (v{String(lote.perfil_version)}){lote.reloj_texto ? ` · reloj ${String(lote.reloj_texto)}` : ''}
          {lote.confirmado_en ? ` · confirmado el ${fechaHoraLegible(String(lote.confirmado_en))}` : ''}
        </p>
        {Boolean(lote.aviso) && <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">⚠ {String(lote.aviso)}</p>}
        {lote.estado === 'revertido' && <p className="mb-4 rounded-lg bg-stone-100 px-3 py-2 text-sm">Revertido: {String(lote.motivo_reversion)}. Sus marcas quedaron anuladas.</p>}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[['total_filas', 'Filas', 'text-stone-900'], ['aceptadas', lote.estado === 'confirmado' ? 'Importadas' : 'Válidas', 'text-green-700'],
            ['rechazadas', 'Rechazadas', 'text-red-700'], ['duplicadas', 'Duplicadas', 'text-stone-500']].map(([campo, texto, color]) => (
            <div key={campo} className="rounded-xl border border-stone-200 p-3">
              <p className={`text-3xl font-bold ${color}`}>{numero(campo)}</p>
              <p className="text-sm text-stone-600">{texto}</p>
            </div>
          ))}
        </div>
        {lote.estado === 'validado' && (
          <p className="mt-4 text-sm text-stone-600">Todavía no se creó ninguna marca. Revisá las filas y confirmá: se importan solo las válidas.</p>
        )}
      </div>

      <AccionesRegistro modulo={modulo} registro={lote} onCambio={() => setVersion((v) => v + 1)} />

      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm">
            <h2 className="font-semibold text-stone-800">Filas</h2>
            <select value={estado} onChange={(e) => { setEstado(e.target.value); setPagina(1) }} className="rounded-lg border border-stone-300 p-1.5">
              {ESTADOS_FILA.map((o) => <option key={o.valor} value={o.valor}>{o.texto}</option>)}
            </select>
          </div>
          {hayErrores && (
            <div className="flex gap-2">
              <button type="button" onClick={() => descargarArchivo(`/importaciones/${id}/errores/?formato=csv`, `errores-lote-${id}.csv`)}
                className="flex items-center gap-1 rounded-lg border border-stone-400 px-3 py-1.5 text-sm"><FileText size={16} /> Errores CSV</button>
              <button type="button" onClick={() => descargarArchivo(`/importaciones/${id}/errores/?formato=xlsx`, `errores-lote-${id}.xlsx`)}
                className="flex items-center gap-1 rounded-lg border border-green-700 px-3 py-1.5 text-sm text-green-800"><FileSpreadsheet size={16} /> Errores Excel</button>
            </div>
          )}
        </div>
        <div className="overflow-x-auto rounded-lg border border-stone-200">
          <table className="w-full min-w-max text-sm">
            <thead className="bg-marca-50 text-left text-stone-700">
              <tr><th className="px-2 py-1.5">Fila</th><th className="px-2 py-1.5">Estado</th><th className="px-2 py-1.5">En el archivo</th>
                <th className="px-2 py-1.5">Empleado</th><th className="px-2 py-1.5">Fecha y hora</th><th className="px-2 py-1.5">Tipo</th>
                <th className="px-2 py-1.5">Motivo</th></tr>
            </thead>
            <tbody>
              {filas?.results.map((f) => (
                <tr key={f.id} className={`border-t border-stone-100 ${COLOR_FILA[String(f.estado)] ?? ''}`}>
                  <td className="px-2 py-1">{String(f.numero_fila)}</td>
                  <td className="px-2 py-1">{String(f.estado_texto)}</td>
                  <td className="px-2 py-1 font-mono text-xs">{String(f.codigo_en_archivo || '—')}</td>
                  <td className="px-2 py-1">{String(f.empleado_texto || '—')}</td>
                  <td className="px-2 py-1">{f.fecha_hora ? fechaHoraLegible(String(f.fecha_hora)) : '—'}</td>
                  <td className="px-2 py-1">{String(f.tipo_texto || '—')}</td>
                  <td className="px-2 py-1 text-stone-700">{String(f.mensaje || '')}</td>
                </tr>
              ))}
              {filas && filas.results.length === 0 && <tr><td colSpan={7} className="px-2 py-4 text-center text-stone-500">Sin filas.</td></tr>}
            </tbody>
          </table>
        </div>
        {filas && filas.count > 50 && (
          <div className="mt-3 flex items-center justify-end gap-2 text-sm">
            <button type="button" disabled={!filas.previous} onClick={() => setPagina((p) => p - 1)} className="rounded-md border border-stone-300 px-3 py-1 disabled:opacity-40">Anterior</button>
            <span>{pagina} / {Math.ceil(filas.count / 50)}</span>
            <button type="button" disabled={!filas.next} onClick={() => setPagina((p) => p + 1)} className="rounded-md border border-stone-300 px-3 py-1 disabled:opacity-40">Siguiente</button>
          </div>
        )}
      </div>
    </div>
  )
}
