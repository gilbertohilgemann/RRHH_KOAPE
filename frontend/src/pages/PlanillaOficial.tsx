import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertTriangle, ChevronLeft, Download, RefreshCw } from 'lucide-react'
import api from '../services/api'
import AccionesRegistro from '../components/AccionesRegistro'
import { descargarArchivo } from '../descargas'
import { fechaLegible, guaranies } from '../formato'
import { buscarModulo } from '../modulos'
import { tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Registro } from '../tipos'

const NUMERICOS = /^(dias|salario_imponible|aporte_|total|aguinaldo|beneficios|mes_)/

/** Una planilla MTESS / IPS: sus líneas validadas, la exportación y el registro de la presentación. */
export default function PlanillaOficial() {
  const { id } = useParams()
  const { usuario } = useSesion()
  const [planilla, setPlanilla] = useState<Registro | null>(null)
  const [error, setError] = useState('')
  const modulo = buscarModulo('planillas-oficiales')

  const cargar = useCallback(() => {
    api.get<Registro>(`/planillas-oficiales/${id}/`).then((r) => setPlanilla(r.data)).catch(() => setError('No se encontró la planilla.'))
  }, [id])
  useEffect(() => { cargar() }, [cargar])

  if (!planilla || !modulo) return <p className="text-stone-500">{error || 'Cargando…'}</p>
  const columnas = planilla.columnas as { campo: string; etiqueta: string }[]
  const lineas = planilla.lineas as Registro[]
  const preparar = async () => {
    await api.post(`/planillas-oficiales/${id}/preparar/`).catch(() => setError('No se pudo preparar.'))
    cargar()
  }
  const abierta = planilla.estado === 'preparada' || planilla.estado === 'rechazada'
  const puedePreparar = tienePermiso(usuario, 'cumplimiento.preparar_presentacion')
  const acciones = [
    { accion: 'presentada', etiqueta: 'Registrar la presentación', permiso: 'cumplimiento.confirmar_presentacion', pideMotivo: true,
      etiquetaMotivo: 'Número de comprobante', visibleSi: (r: Registro) => r.estado === 'preparada' },
    { accion: 'rechazada', etiqueta: 'El organismo la rechazó', permiso: 'cumplimiento.confirmar_presentacion', pideMotivo: true, peligrosa: true,
      visibleSi: (r: Registro) => r.estado === 'presentada' },
    { accion: 'anular', etiqueta: 'Anular', permiso: 'cumplimiento.confirmar_presentacion', pideMotivo: true, peligrosa: true,
      visibleSi: (r: Registro) => r.estado !== 'anulada' && r.estado !== 'presentada' },
  ]

  return (
    <div className="space-y-4">
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Link to="/m/planillas-oficiales" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
          <h1 className="text-xl font-bold text-stone-900">{String(planilla.tipo_texto)}</h1>
          <span className="rounded-full bg-marca-50 px-2.5 py-0.5 text-sm font-medium text-marca-800">{String(planilla.estado_texto)}</span>
        </div>
        <p className="mb-3 text-sm text-stone-600">
          {fechaLegible(String(planilla.periodo_desde))} al {fechaLegible(String(planilla.periodo_hasta))} · {String(planilla.cantidad_lineas)} empleados
          {planilla.numero_comprobante ? ` · comprobante ${String(planilla.numero_comprobante)}` : ''}
          {planilla.observaciones ? ` · ${String(planilla.observaciones)}` : ''}
        </p>
        {Number(planilla.lineas_con_errores) > 0 && (
          <p className="mb-3 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            {String(planilla.lineas_con_errores)} empleado(s) con errores: corregí sus legajos y tocá «Preparar de nuevo». Con errores no se registra la presentación.
          </p>
        )}
        <p className="mb-3 text-xs text-stone-500">Los datos salen de las nóminas cerradas. El formato del archivo es una propuesta: verificalo contra el
          sistema del organismo (REI del IPS, planillas del MTESS) antes de presentarlo.</p>
        <div className="flex flex-wrap gap-2">
          {abierta && puedePreparar && (
            <button type="button" onClick={preparar} className="flex items-center gap-1 rounded-lg border border-stone-300 px-3 py-2 text-sm hover:bg-stone-50">
              <RefreshCw size={16} /> Preparar de nuevo
            </button>
          )}
          {puedePreparar && ['csv', 'xlsx'].map((formato) => (
            <button key={formato} type="button"
              onClick={() => descargarArchivo(`/planillas-oficiales/${id}/exportar/?formato=${formato}`, `${String(planilla.tipo)}.${formato}`)}
              className="flex items-center gap-1 rounded-lg bg-marca-700 px-3 py-2 text-sm font-medium text-white hover:bg-marca-600">
              <Download size={16} /> {formato === 'csv' ? 'CSV' : 'Excel'}
            </button>
          ))}
        </div>
      </div>
      <AccionesRegistro modulo={{ ...modulo, acciones }} registro={planilla} onCambio={cargar} />
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <div className="overflow-x-auto rounded-lg border border-stone-200">
          <table className="w-full min-w-max text-xs">
            <thead className="bg-marca-50 text-left text-stone-700">
              <tr><th className="px-2 py-1.5">Empleado</th>{columnas.map((c) => <th key={c.campo} className="px-2 py-1.5">{c.etiqueta}</th>)}<th className="px-2 py-1.5">Observaciones</th></tr>
            </thead>
            <tbody>
              {lineas.map((l) => {
                const datos = l.datos as Record<string, string>
                return (
                  <tr key={l.id} className={`border-t border-stone-100 align-top ${l.valida ? '' : 'bg-red-50'}`}>
                    <td className="px-2 py-1">{String(l.empleado_texto)}</td>
                    {columnas.map((c) => (
                      <td key={c.campo} className={`px-2 py-1 ${NUMERICOS.test(c.campo) ? 'text-right tabular-nums' : ''}`}>
                        {NUMERICOS.test(c.campo) && c.campo !== 'dias' ? guaranies(datos[c.campo]) : datos[c.campo] || '—'}
                      </td>
                    ))}
                    <td className="px-2 py-1">
                      {(l.errores as string[]).map((e) => <span key={e} className="block text-red-700">{e}</span>)}
                      {(l.advertencias as string[]).map((e) => <span key={e} className="block text-amber-800">{e}</span>)}
                    </td>
                  </tr>
                )
              })}
              {lineas.length === 0 && <tr><td colSpan={columnas.length + 2} className="px-2 py-6 text-center text-stone-500">Sin datos en ese período (¿hay nóminas cerradas?).</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
