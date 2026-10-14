import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronLeft, Plus } from 'lucide-react'
import api from '../services/api'
import { fechaLegible } from '../formato'
import { tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Paginado, Registro } from '../tipos'

interface Saldo {
  saldo: string | number
  devengado: string | number
  gozado: string | number
  pendiente_de_aprobar: string | number
  proximo_aniversario: string
}

const COLOR: Record<string, string> = {
  pendiente: 'bg-amber-100 text-amber-900', aprobada: 'bg-green-100 text-green-800',
  rechazada: 'bg-red-100 text-red-800', cancelada: 'bg-stone-100 text-stone-500',
}

/** El empleado ve su saldo de vacaciones y sus licencias, y pide una nueva (queda pendiente). */
export default function MisLicencias() {
  const { usuario } = useSesion()
  const navegar = useNavigate()
  const [saldo, setSaldo] = useState<Saldo | null>(null)
  const [licencias, setLicencias] = useState<Registro[]>([])
  const empleado = usuario?.empleado

  useEffect(() => {
    api.get<Saldo>('/movimientos-vacaciones/saldo/').then((r) => setSaldo(r.data)).catch(() => setSaldo(null))
    api.get<Paginado<Registro>>('/licencias/', { params: { por_pagina: 50, orden: '-fecha_desde' } })
      .then((r) => setLicencias(r.data.results)).catch(() => setLicencias([]))
  }, [])

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Link to="/" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
          <h1 className="text-xl font-bold text-stone-900">Mis licencias y vacaciones</h1>
        </div>
        {empleado && tienePermiso(usuario, 'licencias.add_solicitudlicencia') && (
          <Link to={`/m/licencias/nuevo?empleado=${empleado.id}&empleado_texto=${encodeURIComponent(empleado.nombre)}&volver=/mis-licencias`}
            className="flex items-center gap-1 rounded-lg bg-marca-700 px-3 py-2 text-sm font-medium text-white hover:bg-marca-800">
            <Plus size={16} /> Pedir licencia o vacaciones
          </Link>
        )}
      </div>
      {saldo && (
        <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[['Días disponibles', saldo.saldo], ['Devengados', saldo.devengado], ['Tomados', saldo.gozado],
            ['Pedidos sin aprobar', saldo.pendiente_de_aprobar]].map(([texto, valor]) => (
            <div key={texto} className="rounded-xl border border-stone-200 p-2">
              <p className="text-xl font-bold tabular-nums">{Number(valor)}</p>
              <p className="text-xs text-stone-500">{texto}</p>
            </div>
          ))}
          <p className="col-span-full text-xs text-stone-500">Próximo aniversario (nuevo devengo): {fechaLegible(saldo.proximo_aniversario)}</p>
        </div>
      )}
      <p className="mb-2 text-sm text-stone-600">Tu pedido queda pendiente hasta que Recursos Humanos lo apruebe. Mientras esté pendiente lo podés
        corregir o cancelar tocándolo.</p>
      <ul className="divide-y divide-stone-100 rounded-lg border border-stone-200">
        {licencias.map((l) => (
          <li key={l.id}>
            <button type="button" onClick={() => navegar(`/m/licencias/${l.id}?volver=/mis-licencias`)}
              className="flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-marca-50/60">
              <span>
                <span className="font-medium">{String(l.tipo_texto)}</span>{' · '}
                {fechaLegible(String(l.fecha_desde))}{l.fecha_hasta !== l.fecha_desde && ` al ${fechaLegible(String(l.fecha_hasta))}`}
                {l.hora_desde ? ` · ${String(l.hora_desde).slice(0, 5)}–${String(l.hora_hasta).slice(0, 5)}` : ` · ${Number(l.dias)} días`}
              </span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${COLOR[String(l.estado)] ?? ''}`}>{String(l.estado_texto)}</span>
            </button>
          </li>
        ))}
        {licencias.length === 0 && <li className="px-3 py-6 text-center text-sm text-stone-500">Todavía no pediste licencias.</li>}
      </ul>
    </div>
  )
}
