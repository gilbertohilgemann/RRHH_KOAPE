import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import api from '../services/api'
import { fechaLegible, guaranies } from '../formato'
import type { Paginado, Registro } from '../tipos'

/** El empleado ve sus recibos de sueldo publicados y los imprime. */
export default function MisRecibos() {
  const navegar = useNavigate()
  const [recibos, setRecibos] = useState<Registro[]>([])

  useEffect(() => {
    api.get<Paginado<Registro>>('/recibos/', { params: { por_pagina: 60 } }).then((r) => setRecibos(r.data.results)).catch(() => setRecibos([]))
  }, [])

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <div className="mb-3 flex items-center gap-2">
        <Link to="/" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
        <h1 className="text-xl font-bold text-stone-900">Mis recibos de sueldo</h1>
      </div>
      <p className="mb-3 text-sm text-stone-600">Tocá un recibo para verlo con el detalle de cada concepto, imprimirlo o guardarlo en PDF.</p>
      <ul className="divide-y divide-stone-100 rounded-lg border border-stone-200">
        {recibos.map((r) => (
          <li key={r.id}>
            <button type="button" onClick={() => navegar(`/recibos/${r.id}`)}
              className="flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-marca-50/60">
              <span><span className="font-medium">{fechaLegible(String(r.periodo_desde))} al {fechaLegible(String(r.periodo_hasta))}</span>
                <span className="ml-2 font-mono text-xs text-stone-500">{String(r.numero)}</span></span>
              <span className="font-semibold tabular-nums">Gs. {guaranies(r.neto)}</span>
            </button>
          </li>
        ))}
        {recibos.length === 0 && <li className="px-3 py-6 text-center text-sm text-stone-500">Todavía no hay recibos publicados.</li>}
      </ul>
    </div>
  )
}
