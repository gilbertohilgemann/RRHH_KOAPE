import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft, PenLine } from 'lucide-react'
import api from '../services/api'
import TablaDias from '../components/TablaDias'
import { horasMinutos } from '../formato'
import { tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Paginado, Registro } from '../tipos'

/** El empleado ve su asistencia de los últimos 31 días y pide correcciones de marca. */
export default function MiAsistencia() {
  const { usuario } = useSesion()
  const [dias, setDias] = useState<Registro[]>([])

  useEffect(() => {
    const d = new Date()
    d.setDate(d.getDate() - 31)
    const desde = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    api.get<Paginado<Registro>>('/dias-asistencia/', { params: { desde, por_pagina: 40, orden: '-fecha' } })
      .then((r) => setDias(r.data.results)).catch(() => setDias([]))
  }, [])

  const total = (campo: string) => dias.reduce((s, d) => s + Number(d[campo] ?? 0), 0)
  const empleado = usuario?.empleado

  return (
    <div className="space-y-4">
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Link to="/" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
            <h1 className="text-xl font-bold text-stone-900">Mi asistencia</h1>
          </div>
          {empleado && tienePermiso(usuario, 'asistencia.add_ajustemarcacion') && (
            <Link to={`/m/ajustes-marcacion/nuevo?empleado=${empleado.id}&empleado_texto=${encodeURIComponent(empleado.nombre)}&volver=/mi-asistencia`}
              className="flex items-center gap-1 rounded-lg border border-marca-700 px-3 py-2 text-sm font-medium text-marca-800 hover:bg-marca-50">
              <PenLine size={16} /> Pedir corrección de marca
            </Link>
          )}
        </div>
        <p className="mb-3 text-sm text-stone-600">Últimos 31 días. Tocá un día para ver tus marcas y cómo se calculó. Si te olvidaste de marcar, pedí la
          corrección: Recursos Humanos la revisa.</p>
        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[['Trabajado', 'minutos_trabajados'], ['Tardanzas', 'minutos_tardanza'], ['Extra autorizado', 'minutos_extra_autorizados'],
            ['Días ausente', '']].map(([texto, campo]) => (
            <div key={texto} className="rounded-xl border border-stone-200 p-2">
              <p className="text-xl font-bold tabular-nums">{campo ? horasMinutos(total(campo)) : dias.filter((d) => d.estado === 'ausente').length}</p>
              <p className="text-xs text-stone-500">{texto}</p>
            </div>
          ))}
        </div>
        <TablaDias dias={dias} conEmpleado={false} />
      </div>
    </div>
  )
}
