import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, Printer } from 'lucide-react'
import api from '../services/api'
import AccionesRegistro from '../components/AccionesRegistro'
import { fechaLegible, guaranies } from '../formato'
import { logoDe } from '../marca'
import { buscarModulo } from '../modulos'
import { tieneAlcanceGeneral } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Registro } from '../tipos'

/** Recibo de sueldo para ver e imprimir (o guardar como PDF desde el navegador). */
export default function ReciboSueldo() {
  const { id } = useParams()
  const { usuario } = useSesion()
  const [recibo, setRecibo] = useState<Registro | null>(null)
  const [error, setError] = useState('')
  const general = tieneAlcanceGeneral(usuario)
  const modulo = buscarModulo('recibos')

  const cargar = () => {
    api.get<Registro>(`/recibos/${id}/`).then((r) => setRecibo(r.data)).catch(() => setError('No se encontró el recibo.'))
  }
  useEffect(cargar, [id])

  if (!recibo) return <p className="text-stone-500">{error || 'Cargando…'}</p>
  const empresa = recibo.empresa as Record<string, string>
  const empleado = recibo.empleado_datos as Record<string, string>
  const liq = recibo.liquidacion_datos as Record<string, string>
  const lineas = (recibo.lineas as Registro[]) ?? []
  const haberes = lineas.filter((l) => Number(l.importe_con_signo) > 0)
  const descuentos = lineas.filter((l) => Number(l.importe_con_signo) < 0)
  const anulado = recibo.estado === 'anulado'

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
        <Link to={general ? '/m/recibos' : '/mis-recibos'} className="flex items-center gap-1 text-sm text-stone-600 hover:text-stone-900">
          <ChevronLeft size={18} /> Volver
        </Link>
        <button type="button" onClick={() => window.print()}
          className="flex items-center gap-1 rounded-lg bg-marca-700 px-3 py-2 text-sm font-medium text-white hover:bg-marca-600">
          <Printer size={16} /> Imprimir o guardar en PDF
        </button>
      </div>

      <article className="relative mx-auto max-w-3xl rounded-2xl bg-white p-6 text-sm text-stone-900 shadow-sm ring-1 ring-stone-200 print:shadow-none print:ring-0">
        {anulado && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-center font-bold text-red-800">ANULADO: {String(recibo.motivo_anulacion)}</p>}
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-stone-300 pb-3">
          <div className="flex items-center gap-3">
            <img src={logoDe(usuario)} alt="" className="h-12 w-auto object-contain" />
            <div>
              <p className="text-base font-bold">{empresa.razon_social || empresa.nombre}</p>
              <p className="text-xs text-stone-600">
                RUC {empresa.ruc || '—'}
                {/* Solo si el empleado aportaba al IPS: si no, el recibo no lleva el número patronal (lo decide el servidor). */}
                {'numero_patronal_ips' in empresa && ` · N.º patronal IPS ${empresa.numero_patronal_ips || '—'}`}
              </p>
              <p className="text-xs text-stone-600">{empresa.direccion}</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-base font-bold">Recibo de {String(recibo.tipo_texto).toLowerCase()}</p>
            <p className="font-mono">{String(recibo.numero)}</p>
            <p className="text-xs text-stone-600">Emitido el {fechaLegible(String(recibo.fecha_emision))}</p>
          </div>
        </header>
        <section className="mb-4 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
          <p><span className="block text-stone-500">Empleado</span>{empleado.nombre}</p>
          <p><span className="block text-stone-500">Legajo · Cédula</span>{empleado.codigo} · {empleado.documento}</p>
          <p><span className="block text-stone-500">Puesto</span>{empleado.puesto || '—'}</p>
          <p><span className="block text-stone-500">Ingreso</span>{fechaLegible(empleado.fecha_ingreso)}</p>
          <p><span className="block text-stone-500">Período</span>{fechaLegible(String(recibo.periodo_desde))} al {fechaLegible(String(recibo.periodo_hasta))}</p>
          <p><span className="block text-stone-500">Sueldo o tarifa</span>{guaranies(liq.salario_base)}</p>
          <p><span className="block text-stone-500">Días pagados</span>{Number(liq.dias_pagados)}</p>
          <p><span className="block text-stone-500">Días trabajados</span>{Number(liq.dias_trabajados)}</p>
        </section>
        <table className="mb-4 w-full text-xs">
          <thead className="border-y border-stone-300 text-left">
            <tr><th className="py-1">Concepto</th><th className="py-1">Detalle</th><th className="py-1 text-right">Haberes</th><th className="py-1 text-right">Descuentos</th></tr>
          </thead>
          <tbody>
            {[...haberes, ...descuentos].map((l) => (
              <tr key={l.id} className="border-b border-stone-100 align-top">
                <td className="py-1 pr-2 font-medium">{String(l.nombre)}</td>
                <td className="py-1 pr-2 text-stone-600">{String(l.explicacion)}</td>
                <td className="py-1 text-right tabular-nums">{Number(l.importe_con_signo) > 0 ? guaranies(l.importe) : ''}</td>
                <td className="py-1 text-right tabular-nums">{Number(l.importe_con_signo) < 0 ? guaranies(l.importe) : ''}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t border-stone-300 font-semibold">
            <tr><td colSpan={2} className="py-1">Totales</td><td className="py-1 text-right tabular-nums">{guaranies(recibo.bruto)}</td>
              <td className="py-1 text-right tabular-nums">{guaranies(recibo.descuentos)}</td></tr>
          </tfoot>
        </table>
        <p className="mb-1 text-right text-base font-bold">Neto a cobrar: Gs. {guaranies(recibo.neto)}</p>
        {liq.neto_anterior !== null && liq.neto_anterior !== undefined && (
          <p className="text-right text-xs text-stone-600">Rectificación: neto anterior {guaranies(liq.neto_anterior)} · diferencia {guaranies(Number(recibo.neto) - Number(liq.neto_anterior))}</p>
        )}
        {general && recibo.costo_empleador !== undefined && (
          <p className="mt-1 text-right text-xs text-stone-500 print:hidden">Costo del empleador (interno, no se imprime): {guaranies(recibo.costo_empleador)}</p>
        )}
        <footer className="mt-10 grid grid-cols-2 gap-8 text-center text-xs text-stone-600">
          <p className="border-t border-stone-400 pt-1">Firma del empleador</p>
          <p className="border-t border-stone-400 pt-1">Recibí conforme · firma del empleado</p>
        </footer>
      </article>
      {general && modulo && !anulado && (
        <div className="mx-auto max-w-3xl print:hidden">
          <AccionesRegistro modulo={{ ...modulo, acciones: [
            { accion: 'anular', etiqueta: 'Anular recibo', permiso: 'nomina.emitir_recibos', peligrosa: true, pideMotivo: true },
          ] }} registro={recibo} onCambio={cargar} />
        </div>
      )}
    </div>
  )
}
