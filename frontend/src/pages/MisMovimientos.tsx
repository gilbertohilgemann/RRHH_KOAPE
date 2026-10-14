import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronLeft, Plus } from 'lucide-react'
import api from '../services/api'
import { fechaLegible } from '../formato'
import { tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Paginado, Registro } from '../tipos'

const gs = (valor: unknown) => (valor === null || valor === undefined || valor === '' ? '—' : `Gs. ${Number(valor).toLocaleString('es-PY')}`)

/** Una lista simple de registros propios, con su estado. */
function Lista({ titulo, filas, vacio, linea, ruta }: {
  titulo: string; filas: Registro[]; vacio: string; linea: (r: Registro) => string; ruta: (r: Registro) => string
}) {
  const navegar = useNavigate()
  return (
    <section>
      <h2 className="mb-1 font-semibold text-stone-800">{titulo}</h2>
      <ul className="divide-y divide-stone-100 rounded-lg border border-stone-200">
        {filas.map((r) => (
          <li key={r.id}>
            <button type="button" onClick={() => navegar(ruta(r))}
              className="flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-marca-50/60">
              <span>{linea(r)}</span>
              <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-700">{String(r.estado_texto)}</span>
            </button>
          </li>
        ))}
        {filas.length === 0 && <li className="px-3 py-4 text-center text-sm text-stone-500">{vacio}</li>}
      </ul>
    </section>
  )
}

/** El empleado ve sus anticipos, préstamos, descuentos y conceptos fijos, y pide un anticipo (queda solicitado). */
export default function MisMovimientos() {
  const { usuario } = useSesion()
  const [datos, setDatos] = useState<Record<string, Registro[]>>({})
  const empleado = usuario?.empleado
  const volver = 'volver=/mis-movimientos'

  useEffect(() => {
    const leer = (ruta: string) => api.get<Paginado<Registro>>(ruta, { params: { por_pagina: 50 } }).then((r) => r.data.results).catch(() => [])
    Promise.all(['/anticipos/', '/prestamos/', '/descuentos-autorizados/', '/conceptos-fijos/'].map(leer))
      .then(([anticipos, prestamos, descuentos, fijos]) => setDatos({ anticipos, prestamos, descuentos, fijos }))
  }, [])

  return (
    <div className="space-y-4 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Link to="/" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
          <h1 className="text-xl font-bold text-stone-900">Mis anticipos y descuentos</h1>
        </div>
        {empleado && tienePermiso(usuario, 'novedades.add_anticipo') && (
          <Link to={`/m/anticipos/nuevo?empleado=${empleado.id}&empleado_texto=${encodeURIComponent(empleado.nombre)}&${volver}`}
            className="flex items-center gap-1 rounded-lg bg-marca-700 px-3 py-2 text-sm font-medium text-white hover:bg-marca-800">
            <Plus size={16} /> Pedir un anticipo
          </Link>
        )}
      </div>
      <p className="text-sm text-stone-600">Tu pedido de anticipo queda <em>solicitado</em> hasta que Recursos Humanos lo apruebe y lo pague. Después se
        descuenta de tu sueldo en las cuotas indicadas.</p>
      <Lista titulo="Anticipos" filas={datos.anticipos ?? []} vacio="Sin anticipos." ruta={(r) => `/m/anticipos/${r.id}?${volver}`}
        linea={(r) => `${fechaLegible(String(r.fecha))} · ${gs(r.monto_aprobado ?? r.monto_solicitado)}${Number(r.saldo) ? ` · saldo ${gs(r.saldo)}` : ''}`} />
      <Lista titulo="Préstamos" filas={datos.prestamos ?? []} vacio="Sin préstamos." ruta={(r) => `/m/prestamos/${r.id}?${volver}`}
        linea={(r) => `${fechaLegible(String(r.fecha))} · ${gs(r.capital)} en ${String(r.cantidad_cuotas)} cuotas de ${gs(r.monto_cuota)} · saldo ${gs(r.saldo)}`} />
      <Lista titulo="Descuentos autorizados" filas={datos.descuentos ?? []} vacio="Sin descuentos." ruta={(r) => `/m/descuentos-autorizados/${r.id}?${volver}`}
        linea={(r) => `${String(r.tipo_texto)} · ${r.porcentaje ? `${String(r.porcentaje)} %` : gs(r.monto_cuota)} desde ${fechaLegible(String(r.fecha_desde))}`} />
      <Lista titulo="Conceptos fijos" filas={(datos.fijos ?? []).map((r) => ({ ...r, estado_texto: r.activo ? (r.aprobado ? 'Vigente' : 'A aprobar') : 'Finalizado' }))}
        vacio="Sin conceptos fijos." ruta={(r) => `/m/conceptos-fijos/${r.id}?${volver}`}
        linea={(r) => `${String(r.concepto_texto)} · ${gs(r.monto)} desde ${fechaLegible(String(r.vigente_desde))}`} />
    </div>
  )
}
