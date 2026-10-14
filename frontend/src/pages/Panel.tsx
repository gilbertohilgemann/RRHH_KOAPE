import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { IdCard } from 'lucide-react'
import api from '../services/api'
import { gruposVisibles, rutaDe } from '../menu'
import { tieneAlcanceGeneral } from '../permisos'
import { useSesion } from '../services/sesionContexto'

interface Resumen {
  empleados_activos?: number
  empleados_suspendidos?: number
  altas_del_mes?: number
  bajas_del_mes?: number
  sucursales_activas?: number
}

const INDICADORES: { clave: keyof Resumen; texto: string; filtro?: string }[] = [
  { clave: 'empleados_activos', texto: 'Empleados activos', filtro: 'estado=activo' },
  { clave: 'empleados_suspendidos', texto: 'Suspendidos', filtro: 'estado=suspendido' },
  { clave: 'altas_del_mes', texto: 'Altas del mes' },
  { clave: 'bajas_del_mes', texto: 'Bajas del mes' },
  { clave: 'sucursales_activas', texto: 'Sucursales activas' },
]

/** Pantalla de inicio: indicadores del alcance del usuario y accesos a los
 * módulos que puede ver. El empleado ve el acceso a su ficha. */
export default function Panel() {
  const { usuario } = useSesion()
  const [resumen, setResumen] = useState<Resumen | null>(null)
  const general = tieneAlcanceGeneral(usuario)

  useEffect(() => {
    if (!general) return
    api.get<Resumen>('/resumen/').then((r) => setResumen(r.data)).catch(() => setResumen(null))
  }, [general])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">Hola, {usuario?.nombre}</h1>
        <p className="text-sm text-stone-500">{usuario?.empresa?.nombre ?? 'Plataforma Koape: todas las empresas'}</p>
      </div>

      {general && resumen && Object.keys(resumen).length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {INDICADORES.map((i) => (
            <Link key={i.clave} to={i.filtro ? `/m/empleados?${i.filtro}` : '/m/empleados'}
              className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 hover:ring-marca-400">
              <p className="text-3xl font-bold text-marca-800">{resumen[i.clave] ?? 0}</p>
              <p className="text-sm text-stone-600">{i.texto}</p>
            </Link>
          ))}
        </div>
      )}

      {usuario?.empleado && (
        <Link to="/mi-ficha" className="flex items-center gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 hover:ring-marca-400">
          <IdCard className="text-marca-700" />
          <div>
            <p className="font-semibold text-stone-900">Mi ficha</p>
            <p className="text-sm text-stone-500">{usuario.empleado.nombre} · {usuario.empleado.codigo}</p>
          </div>
        </Link>
      )}

      {gruposVisibles(usuario).map(({ grupo, modulos }) => (
        <section key={grupo}>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-stone-500">{grupo}</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {modulos.map((m) => {
              const Icono = m.icono
              return (
                <Link key={m.clave} to={rutaDe(m, usuario)}
                  className="flex items-start gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 hover:ring-marca-400">
                  <Icono className="mt-0.5 shrink-0 text-marca-700" />
                  <div>
                    <p className="font-semibold text-stone-900">{m.titulo}</p>
                    <p className="text-sm text-stone-500">{m.descripcion}</p>
                  </div>
                </Link>
              )
            })}
          </div>
        </section>
      ))}

      {!general && !usuario?.empleado && (
        <p className="rounded-2xl bg-white p-4 text-stone-600 shadow-sm">Tu usuario todavía no tiene accesos asignados.</p>
      )}
    </div>
  )
}
