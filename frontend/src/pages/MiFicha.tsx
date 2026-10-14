import { Fragment, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import api from '../services/api'
import LegajoEmpleado from '../components/LegajoEmpleado'
import { buscarModulo } from '../modulos'
import { fechaLegible, valorVisible } from '../formato'
import { useSesion } from '../services/sesionContexto'
import type { Registro } from '../tipos'

/** El legajo del propio empleado, solo para ver (lo corrige RR. HH.). El
 * servidor decide cuál es su legajo: la pantalla solo pide el de la sesión. */
export default function MiFicha() {
  const { usuario } = useSesion()
  const [ficha, setFicha] = useState<Registro | null>(null)
  const [historial, setHistorial] = useState<Registro[]>([])
  const [error, setError] = useState<string | null>(null)
  const idEmpleado = usuario?.empleado?.id

  useEffect(() => {
    if (!idEmpleado) return
    api.get<Registro>(`/empleados/${idEmpleado}/`).then((r) => setFicha(r.data)).catch(() => setError('No se pudo cargar tu ficha.'))
    api.get<Registro[]>(`/empleados/${idEmpleado}/historial/`).then((r) => setHistorial(r.data)).catch(() => setHistorial([]))
  }, [idEmpleado])

  if (!idEmpleado) {
    return <p className="rounded-xl bg-white p-6">Tu usuario no tiene un legajo vinculado. <Link to="/" className="underline">Volver al panel</Link></p>
  }
  const campos = (buscarModulo('empleados')?.campos ?? []).filter((c) => c.nombre !== 'observaciones')

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <div className="mb-4 flex items-center gap-2">
          <Link to="/" aria-label="Volver al panel" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
          <h1 className="text-xl font-bold text-stone-900 sm:text-2xl">Mi ficha</h1>
        </div>
        <p className="mb-4 rounded-lg bg-marca-50 px-3 py-2 text-sm text-marca-900">
          Si algún dato está mal, avisá a Recursos Humanos para que lo corrija.
        </p>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
        {ficha && (
          <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
            {campos.map((c) => (
              <Fragment key={c.nombre}>
                {c.seccion && <h2 className="border-b border-marca-100 pb-1 pt-2 font-semibold text-stone-700 sm:col-span-2">{c.seccion}</h2>}
                <div>
                  <dt className="text-xs text-stone-500">{c.etiqueta}</dt>
                  <dd className="text-stone-900">{valorVisible(ficha, c.nombre, c)}</dd>
                </div>
              </Fragment>
            ))}
            <div>
              <dt className="text-xs text-stone-500">Estado</dt>
              <dd className="text-stone-900">{valorVisible(ficha, 'estado')}</dd>
            </div>
          </dl>
        )}
      </div>
      {historial.length > 0 && (
        <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
          <h2 className="mb-2 font-semibold text-stone-800">Mis asignaciones</h2>
          <ul className="space-y-1 text-sm">
            {historial.map((h) => (
              <li key={h.id} className="border-t border-stone-100 pt-1">
                {fechaLegible(String(h.vigente_desde))} – {h.vigente_hasta ? fechaLegible(String(h.vigente_hasta)) : 'hoy'}:{' '}
                {[h.sucursal_texto, h.departamento_texto, h.puesto_texto].filter(Boolean).join(' · ') || 'sin asignación'}
              </li>
            ))}
          </ul>
        </div>
      )}
      {/* Sus contratos, sueldos aprobados, documentos y cuentas (enmascaradas): solo para ver. */}
      {ficha && <LegajoEmpleado empleado={ficha} soloVer volver="/mi-ficha" />}
    </div>
  )
}
