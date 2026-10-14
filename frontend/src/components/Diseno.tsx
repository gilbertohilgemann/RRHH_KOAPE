import { useState } from 'react'
import { LogOut, Menu, X } from 'lucide-react'
import { Link, Navigate, Outlet, useLocation } from 'react-router-dom'
import { useSesion } from '../services/sesionContexto'
import { rutaIngreso } from '../services/api'
import MenuLateral from './MenuLateral'
import { LOGO_KOAPE, logoDe } from '../marca'

const NOMBRE_NIVEL: Record<string, string> = {
  plataforma: 'Plataforma',
  administrador: 'Administrador',
  gestor: 'Gestor RR. HH.',
  empleado: 'Empleado',
}

/** Marco común de todas las pantallas con sesión iniciada: encabezado con el
 * usuario y "Salir", menú lateral (en el celular se abre con "Menú") y el
 * contenido. Si no hay sesión, manda a la pantalla de ingreso. */
export default function Diseno() {
  const { usuario, cargando, salir } = useSesion()
  const [menuAbierto, setMenuAbierto] = useState(false)
  const ubicacion = useLocation()

  if (cargando) {
    return <div className="fondo-app flex items-center justify-center text-stone-500">Cargando…</div>
  }
  // Al iniciar sesión se vuelve a donde quería ir (ej. el enlace de un QR de marcación).
  // Vuelve al ingreso de su empresa (/<dirección>) si entró por ahí; si no, al estándar.
  if (!usuario) return <Navigate to={rutaIngreso()} replace state={{ desde: ubicacion.pathname }} />

  return (
    <div className="fondo-app flex flex-col">
      <div className="franja-marca" />
      <header className="border-b border-stone-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-3 px-4 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <button type="button" onClick={() => setMenuAbierto(true)} aria-label="Abrir el menú"
              className="rounded-md p-1.5 text-stone-700 hover:bg-stone-100 lg:hidden">
              <Menu size={22} />
            </button>
            <Link to="/" className="flex min-w-0 items-center gap-2">
              {/* La empresa con logo propio se ve con el suyo y su nombre; si no, Koape RR. HH. */}
              <img src={logoDe(usuario)} alt="" className="h-10 w-auto max-w-[9rem] object-contain" />
              <span className="truncate font-bold text-stone-900">
                {usuario.marca.logo && usuario.empresa ? usuario.empresa.nombre : 'Koape RR. HH.'}
              </span>
            </Link>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-right leading-tight sm:block">
              <span className="block font-medium text-stone-800">{usuario.nombre}</span>
              <span className="block text-xs text-stone-500">
                {NOMBRE_NIVEL[usuario.nivel] ?? usuario.nivel}{usuario.empresa && ` · ${usuario.empresa.nombre}`}
              </span>
            </span>
            <button type="button" onClick={salir}
              className="flex items-center gap-1 rounded-md bg-marca-700 px-3 py-1.5 font-medium text-white hover:bg-marca-600">
              <LogOut size={16} /> Salir
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-[1600px] flex-1 gap-4 px-4 py-6">
        <aside className="hidden w-60 shrink-0 lg:block">
          <div className="sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto rounded-2xl bg-white p-3 shadow-sm ring-1 ring-stone-200">
            <MenuLateral />
          </div>
        </aside>
        {menuAbierto && (
          <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menú">
            <button type="button" aria-label="Cerrar el menú" className="absolute inset-0 bg-black/40" onClick={() => setMenuAbierto(false)} />
            <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] overflow-y-auto bg-white p-3 shadow-xl">
              <div className="mb-2 flex justify-end">
                <button type="button" onClick={() => setMenuAbierto(false)} aria-label="Cerrar el menú"
                  className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><X /></button>
              </div>
              <MenuLateral alElegir={() => setMenuAbierto(false)} />
            </div>
          </div>
        )}
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>

      <footer className="flex items-center justify-center gap-2 px-4 pb-4 text-xs text-stone-500">
        <img src={LOGO_KOAPE} alt="" className="h-5 w-5" />
        <span>Koape RR. HH. · Desarrollado por</span>
        <a href="https://www.koapesystem.com" target="_blank" rel="noreferrer" className="underline">Koape Sistemas</a>
        {' '}· Encarnación, PY
      </footer>
    </div>
  )
}
