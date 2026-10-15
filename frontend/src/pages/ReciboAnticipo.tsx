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

/** Comprobante del pago de un anticipo, para imprimir y firmar al entregarlo (mismo formato que el recibo de sueldo). */
export default function ReciboAnticipo() {
  const { id } = useParams()
  const { usuario } = useSesion()
  const [recibo, setRecibo] = useState<Registro | null>(null)
  const [error, setError] = useState('')
  const general = tieneAlcanceGeneral(usuario)
  const modulo = buscarModulo('anticipos')

  const cargar = () => {
    api.get<Registro>(`/recibos-anticipo/${id}/`).then((r) => setRecibo(r.data)).catch(() => setError('No se encontró el comprobante.'))
  }
  useEffect(cargar, [id])

  if (!recibo) return <p className="text-stone-500">{error || 'Cargando…'}</p>
  const empresa = recibo.empresa as Record<string, string>
  const empleado = recibo.empleado_datos as Record<string, string>
  const anticipo = recibo.anticipo_datos as Record<string, string>
  const cuotas = (recibo.cuotas as Registro[]) ?? []
  const anulado = recibo.estado === 'anulado'

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
        <Link to={general ? `/m/anticipos/${String(recibo.anticipo)}` : '/mis-movimientos'}
          className="flex items-center gap-1 text-sm text-stone-600 hover:text-stone-900">
          <ChevronLeft size={18} /> Volver
        </Link>
        <button type="button" onClick={() => window.print()}
          className="flex items-center gap-1 rounded-lg bg-marca-700 px-3 py-2 text-sm font-medium text-white hover:bg-marca-600">
          <Printer size={16} /> Imprimir o guardar en PDF
        </button>
      </div>

      <article className="mx-auto max-w-3xl rounded-2xl bg-white p-6 text-sm text-stone-900 shadow-sm ring-1 ring-stone-200 print:shadow-none print:ring-0">
        {anulado && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-center font-bold text-red-800">ANULADO: {String(recibo.motivo_anulacion)}</p>}
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-stone-300 pb-3">
          <div className="flex items-center gap-3">
            <img src={logoDe(usuario)} alt="" className="h-12 w-auto object-contain" />
            <div>
              <p className="text-base font-bold">{empresa.razon_social || empresa.nombre}</p>
              <p className="text-xs text-stone-600">
                RUC {empresa.ruc || '—'}
                {/* Sin IPS, el comprobante no lleva el número patronal (lo decide el servidor). */}
                {'numero_patronal_ips' in empresa && ` · N.º patronal IPS ${empresa.numero_patronal_ips || '—'}`}
              </p>
              <p className="text-xs text-stone-600">{empresa.direccion}</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-base font-bold">Comprobante de anticipo</p>
            <p className="font-mono">{String(recibo.numero)}</p>
            <p className="text-xs text-stone-600">Fecha {fechaLegible(String(recibo.fecha_emision))}</p>
          </div>
        </header>
        <section className="mb-4 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
          <p><span className="block text-stone-500">Empleado</span>{empleado.nombre}</p>
          <p><span className="block text-stone-500">Legajo · Cédula</span>{empleado.codigo} · {empleado.documento}</p>
          <p><span className="block text-stone-500">Puesto</span>{empleado.puesto || '—'}</p>
          <p><span className="block text-stone-500">Pedido el</span>{fechaLegible(anticipo.fecha)}</p>
          <p className="col-span-2 sm:col-span-4"><span className="block text-stone-500">Motivo</span>{anticipo.motivo}</p>
          <p><span className="block text-stone-500">Forma de pago</span>{String(recibo.forma_pago) || '—'}</p>
          <p className="col-span-2"><span className="block text-stone-500">Referencia</span>{String(recibo.referencia_pago) || '—'}</p>
        </section>
        <p className="mb-4 rounded-lg bg-stone-50 px-4 py-3 text-base">
          Recibí de <b>{empresa.razon_social || empresa.nombre}</b> la suma de <b>Gs. {guaranies(recibo.monto)}</b> en concepto de anticipo de
          sueldo, que autorizo a descontar de mis haberes en {String(anticipo.cuotas)} cuota(s), según el detalle.
        </p>
        <table className="mb-4 w-full text-xs">
          <thead className="border-y border-stone-300 text-left">
            <tr><th className="py-1">Cuota</th><th className="py-1">Mes de descuento</th><th className="py-1">Estado</th><th className="py-1 text-right">Monto</th></tr>
          </thead>
          <tbody>
            {cuotas.map((c) => (
              <tr key={String(c.numero)} className="border-b border-stone-100">
                <td className="py-1">{String(c.numero)} de {String(anticipo.cuotas)}</td>
                <td className="py-1">{fechaLegible(String(c.mes)).slice(3)}</td>
                <td className="py-1">{String(c.estado)}</td>
                <td className="py-1 text-right tabular-nums">{guaranies(c.monto)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t border-stone-300 font-semibold">
            <tr><td colSpan={3} className="py-1">Total</td><td className="py-1 text-right tabular-nums">{guaranies(recibo.monto)}</td></tr>
          </tfoot>
        </table>
        <p className="text-right text-xs text-stone-600">Saldo pendiente a hoy: Gs. {guaranies(anticipo.saldo)}</p>
        <footer className="mt-12 grid grid-cols-2 gap-8 text-center text-xs text-stone-600">
          <p className="border-t border-stone-400 pt-1">Firma del empleador</p>
          <p className="border-t border-stone-400 pt-1">Recibí conforme · firma del empleado</p>
        </footer>
      </article>
      {general && modulo && !anulado && (
        <div className="mx-auto max-w-3xl print:hidden">
          <AccionesRegistro modulo={{ ...modulo, endpoint: 'recibos-anticipo', acciones: [
            { accion: 'anular', etiqueta: 'Anular comprobante', permiso: 'novedades.pagar_anticipo', peligrosa: true, pideMotivo: true },
          ] }} registro={recibo} onCambio={cargar} />
        </div>
      )}
    </div>
  )
}
