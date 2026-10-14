import { Fragment, useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AlertTriangle, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'
import api from '../services/api'
import { fechaHoraLegible, guaranies, mensajeDeError } from '../formato'
import { tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Paginado, Registro } from '../tipos'

interface Boton {
  accion: string
  etiqueta: string
  permiso: string
  visible: (c: Registro) => boolean
  confirmar?: string
  pide?: string
  peligrosa?: boolean
}

const BOTONES: Boton[] = [
  { accion: 'calcular', etiqueta: 'Recalcular', permiso: 'nomina.calcular_nomina', visible: (c) => c.estado === 'calculada' || c.estado === 'revisada',
    confirmar: '¿Recalcular con los datos actuales (asistencia, novedades, reglas)? Vuelve a quedar sin revisar.' },
  { accion: 'revisar', etiqueta: 'Marcar como revisada', permiso: 'nomina.calcular_nomina', visible: (c) => c.estado === 'calculada',
    confirmar: '¿Revisaste los importes y las advertencias?' },
  { accion: 'aprobar', etiqueta: 'Aprobar', permiso: 'nomina.aprobar_nomina', visible: (c) => c.estado === 'revisada',
    confirmar: '¿Aprobar la liquidación? Después solo queda cerrarla.' },
  { accion: 'cerrar', etiqueta: 'Cerrar', permiso: 'nomina.cerrar_nomina', visible: (c) => c.estado === 'aprobada',
    confirmar: '¿Cerrar? Es definitivo: se aplican las novedades y cuotas, se cierra el período y ya no se modifica (solo se rectifica).' },
  { accion: 'emitir_recibos', etiqueta: 'Emitir recibos', permiso: 'nomina.emitir_recibos', visible: (c) => c.estado === 'cerrada',
    confirmar: '¿Emitir los recibos numerados de los empleados que todavía no tienen?' },
  { accion: 'publicar_recibos', etiqueta: 'Publicar recibos a los empleados', permiso: 'nomina.emitir_recibos', visible: (c) => c.estado === 'cerrada',
    confirmar: '¿Publicar los recibos emitidos? Cada empleado verá el suyo.' },
  { accion: 'registrar_pagos', etiqueta: 'Registrar pagos (transferencia)', permiso: 'nomina.registrar_pagos', visible: (c) => c.estado === 'cerrada',
    pide: 'Referencia del lote de transferencias' },
  { accion: 'rectificar', etiqueta: 'Rectificar', permiso: 'nomina.rectificar_nomina', visible: (c) => c.estado === 'cerrada' && !c.rectificada,
    pide: 'Motivo de la rectificación', peligrosa: true },
  { accion: 'anular', etiqueta: 'Anular', permiso: 'nomina.aprobar_nomina', visible: (c) => ['calculada', 'revisada', 'aprobada'].includes(String(c.estado)),
    pide: 'Motivo de la anulación', peligrosa: true },
]

const COLOR_CALCULO: Record<string, string> = { ok: '', advertencia: 'bg-amber-50', error: 'bg-red-50' }

/** El detalle de un empleado: cada línea con su explicación. */
function Lineas({ id }: { id: number }) {
  const [lineas, setLineas] = useState<Registro[] | null>(null)
  useEffect(() => {
    api.get<Registro>(`/liquidaciones-nomina/${id}/`).then((r) => setLineas(r.data.lineas as Registro[])).catch(() => setLineas([]))
  }, [id])
  if (!lineas) return <p className="p-2 text-sm text-stone-500">Cargando…</p>
  return (
    <table className="w-full text-xs">
      <tbody>
        {lineas.map((l) => (
          <tr key={l.id} className="border-t border-stone-100 align-top">
            <td className="w-48 px-2 py-1 font-medium">{String(l.nombre)}<span className="block font-normal text-stone-500">{String(l.tipo_texto)}</span></td>
            <td className="px-2 py-1 text-stone-600">{String(l.explicacion)}</td>
            <td className={`w-32 px-2 py-1 text-right font-medium tabular-nums ${Number(l.importe_con_signo) < 0 ? 'text-red-700' : ''}`}>
              {Number(l.importe_con_signo) === 0 ? `(${guaranies(l.importe)})` : guaranies(l.importe_con_signo)}
            </td>
          </tr>
        ))}
        {lineas.length === 0 && <tr><td className="px-2 py-2 text-stone-500">Sin líneas.</td></tr>}
      </tbody>
    </table>
  )
}

export default function CorridaNomina() {
  const { id } = useParams()
  const navegar = useNavigate()
  const { usuario } = useSesion()
  const [corrida, setCorrida] = useState<Registro | null>(null)
  const [liquidaciones, setLiquidaciones] = useState<Registro[]>([])
  const [abierta, setAbierta] = useState<number | null>(null)
  const [mensaje, setMensaje] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  const veCosto = tienePermiso(usuario, 'nomina.ver_costo_patronal')

  const cargar = useCallback(() => {
    api.get<Registro>(`/corridas-nomina/${id}/`).then((r) => setCorrida(r.data)).catch(() => setError('No se encontró la liquidación.'))
    api.get<Paginado<Registro>>('/liquidaciones-nomina/', { params: { corrida: id, por_pagina: 500 } })
      .then((r) => setLiquidaciones(r.data.results)).catch(() => setLiquidaciones([]))
  }, [id])

  useEffect(() => { cargar() }, [cargar])

  const ejecutar = async (b: Boton) => {
    let datos: Record<string, string> = {}
    if (b.pide) {
      const texto = window.prompt(b.pide)
      if (!texto?.trim()) return
      datos = { motivo: texto.trim() }
    } else if (b.confirmar && !window.confirm(b.confirmar)) {
      return
    }
    setEnviando(true)
    setError('')
    setMensaje('')
    try {
      const r = await api.post<Registro>(`/corridas-nomina/${id}/${b.accion}/`, datos)
      if (b.accion === 'rectificar') {
        navegar(`/nomina/liquidaciones/${r.data.id}`)
        return
      }
      setMensaje(`${b.etiqueta}: listo.`)
      cargar()
    } catch (e) {
      setError(mensajeDeError((e as { response?: { data?: unknown } }).response?.data, 'No se pudo completar la acción.'))
    } finally {
      setEnviando(false)
    }
  }

  if (!corrida) return <p className="text-stone-500">{error || 'Cargando…'}</p>
  const advertencias = (corrida.advertencias as string[]) ?? []
  const totales: [string, unknown][] = [
    ['Bruto', corrida.total_bruto], ['Descuentos', corrida.total_descuentos], ['Aportes del trabajador', corrida.total_aportes_trabajador],
    ['Neto a pagar', corrida.total_neto],
    ...(veCosto ? [['Aportes del empleador', corrida.total_aportes_patronales], ['Costo del empleador', corrida.total_costo_empleador]] as [string, unknown][] : []),
  ]

  return (
    <div className="space-y-4">
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Link to="/m/corridas-nomina" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
          <h1 className="text-xl font-bold text-stone-900">Liquidación {String(corrida.periodo_texto)}</h1>
          <span className="rounded-full bg-marca-50 px-2.5 py-0.5 text-sm font-medium text-marca-800">{String(corrida.estado_texto)}</span>
          {corrida.tipo !== 'regular' && <span className="rounded-full bg-violet-100 px-2.5 py-0.5 text-sm text-violet-800">{String(corrida.tipo_texto)}</span>}
          {Boolean(corrida.es_rectificacion) && corrida.tipo !== 'rectificacion' && <span className="rounded-full bg-violet-100 px-2.5 py-0.5 text-sm text-violet-800">Rectificación</span>}
          {Boolean(corrida.rectificada) && <span className="rounded-full bg-stone-100 px-2.5 py-0.5 text-sm text-stone-600">Rectificada</span>}
          {Boolean(corrida.es_simulacion) && <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-sm font-medium text-amber-900">Simulación</span>}
        </div>
        <p className="mb-3 text-xs text-stone-500">
          N.º {String(corrida.numero)} · cálculo n.º {String(corrida.version_calculo)}
          {corrida.calculado_en ? ` · calculada el ${fechaHoraLegible(String(corrida.calculado_en))}` : ''}
          {corrida.motivo_rectificacion ? ` · motivo: ${String(corrida.motivo_rectificacion)}` : ''}
        </p>
        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {totales.map(([texto, valor]) => (
            <div key={texto} className="rounded-xl border border-stone-200 p-2">
              <p className="text-lg font-bold tabular-nums">{guaranies(valor)}</p>
              <p className="text-xs text-stone-500">{texto}</p>
            </div>
          ))}
        </div>
        {advertencias.map((a) => (
          <p key={a} className="mb-2 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />{a}
          </p>
        ))}
        <div className="flex flex-wrap gap-2">
          {BOTONES.filter((b) => b.visible(corrida) && tienePermiso(usuario, b.permiso)).map((b) => (
            <button key={b.accion} type="button" disabled={enviando} onClick={() => ejecutar(b)}
              className={`rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-60 ${b.peligrosa
                ? 'border border-red-300 text-red-700 hover:bg-red-50' : 'bg-marca-700 text-white hover:bg-marca-600'}`}>
              {b.etiqueta}
            </button>
          ))}
        </div>
        {mensaje && <p className="mt-3 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">{mensaje}</p>}
        {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      </div>

      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <h2 className="mb-2 font-semibold text-stone-800">Empleados ({liquidaciones.length})</h2>
        <p className="mb-2 text-xs text-stone-500">Tocá un empleado para ver cada línea con su explicación. En amarillo, con advertencias; en rojo, con errores
          (bloquean la aprobación).</p>
        <div className="overflow-x-auto rounded-lg border border-stone-200">
          <table className="w-full min-w-max text-sm">
            <thead className="bg-marca-50 text-left text-stone-700">
              <tr>
                <th className="w-6" /><th className="px-2 py-1.5">Empleado</th><th className="px-2 py-1.5 text-right">Días pag.</th>
                <th className="px-2 py-1.5 text-right">Bruto</th><th className="px-2 py-1.5 text-right">Descuentos</th>
                <th className="px-2 py-1.5 text-right">Aportes</th><th className="px-2 py-1.5 text-right">Neto</th>
                {Boolean(corrida.es_rectificacion) && <th className="px-2 py-1.5 text-right">Diferencia</th>}
                {veCosto && <th className="px-2 py-1.5 text-right">Costo empleador</th>}
                <th className="px-2 py-1.5">Pago</th>
              </tr>
            </thead>
            <tbody>
              {liquidaciones.map((l) => (
                <Fragment key={l.id}>
                  <tr onClick={() => setAbierta(abierta === l.id ? null : l.id)}
                    className={`cursor-pointer border-t border-stone-100 hover:bg-marca-50/60 ${COLOR_CALCULO[String(l.estado_calculo)] ?? ''}`}>
                    <td className="px-1 text-stone-400">{abierta === l.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</td>
                    <td className="px-2 py-1.5">{String(l.empleado_texto)}
                      {(l.advertencias as string[]).map((a) => <span key={a} className="block text-xs text-amber-800">{a}</span>)}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{Number(l.dias_pagados)}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{guaranies(l.bruto)}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{guaranies(l.descuentos)}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{guaranies(l.aportes_trabajador)}</td>
                    <td className="px-2 py-1.5 text-right font-semibold tabular-nums">{guaranies(l.neto)}</td>
                    {Boolean(corrida.es_rectificacion) && <td className="px-2 py-1.5 text-right tabular-nums">{guaranies(l.a_pagar)}</td>}
                    {veCosto && <td className="px-2 py-1.5 text-right tabular-nums">{guaranies(l.costo_empleador)}</td>}
                    <td className="px-2 py-1.5">{String(l.estado_pago_texto)}</td>
                  </tr>
                  {abierta === l.id && (
                    <tr><td colSpan={10} className="bg-stone-50 px-2 py-1"><Lineas id={l.id} /></td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
