import { useState } from 'react'
import { BookOpen, CalendarCheck, ChevronDown, IdCard, HandCoins, LayoutDashboard, Palmtree, QrCode, Receipt } from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'
import { ICONO_GRUPO, gruposVisibles, rutaDe } from '../menu'
import { tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Grupo, Modulo } from '../tipos'

const claseEnlace = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-marca-700 font-medium text-white' : 'text-stone-700 hover:bg-marca-50'}`

const claseSubmenu = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm ${isActive ? 'bg-marca-700 font-medium text-white' : 'text-stone-600 hover:bg-marca-50 hover:text-stone-900'}`

const CLAVE_GUARDADA = 'koape_rrhh_menu_abierto'

/** Las direcciones de un módulo: su listado y sus pantallas propias de alta y de detalle. */
function rutasDe(m: Modulo): string[] {
  const rutas = [m.rutaPropia ?? `/m/${m.clave}`]
  if (m.rutaNuevo) rutas.push(m.rutaNuevo)
  if (m.rutaDetalle) rutas.push(m.rutaDetalle(0).replace(/0$/, ''))
  return rutas
}

// Qué grupos dejó abiertos el usuario (se recuerda en este navegador; si el
// almacenamiento no está disponible, simplemente no se recuerda).
function leerAbiertos(): Grupo[] {
  try {
    const valor = JSON.parse(localStorage.getItem(CLAVE_GUARDADA) ?? '[]')
    return Array.isArray(valor) ? valor : []
  } catch {
    return []
  }
}

function guardarAbiertos(grupos: Grupo[]) {
  try {
    localStorage.setItem(CLAVE_GUARDADA, JSON.stringify(grupos))
  } catch {
    // Sin almacenamiento: no se recuerda.
  }
}

/** Menú con todos los accesos que el usuario puede ver. Cada grupo
 * (Personal, Jornada, Estructura, Administración) es un menú desplegable y
 * sus módulos son el submenú. El grupo de la pantalla abierta se despliega solo. */
export default function MenuLateral({ alElegir }: { alElegir?: () => void }) {
  const { usuario } = useSesion()
  const { pathname } = useLocation()
  const grupos = gruposVisibles(usuario)
  // El grupo del módulo que se está viendo se abre al entrar a él (después
  // se puede cerrar a mano).
  const grupoActual = grupos.find(({ modulos }) => modulos.some((m) => rutasDe(m).some((r) => pathname.startsWith(r))))?.grupo
  const [abiertos, setAbiertos] = useState<Grupo[]>(() => {
    const guardados = leerAbiertos()
    return grupoActual && !guardados.includes(grupoActual) ? [...guardados, grupoActual] : guardados
  })
  const [grupoPrevio, setGrupoPrevio] = useState(grupoActual)
  if (grupoActual !== grupoPrevio) {
    setGrupoPrevio(grupoActual)
    if (grupoActual && !abiertos.includes(grupoActual)) setAbiertos([...abiertos, grupoActual])
  }

  const alternar = (grupo: Grupo) => {
    const nuevos = abiertos.includes(grupo) ? abiertos.filter((g) => g !== grupo) : [...abiertos, grupo]
    setAbiertos(nuevos)
    guardarAbiertos(nuevos)
  }

  return (
    <nav className="space-y-1">
      <NavLink to="/" end className={claseEnlace} onClick={alElegir}><LayoutDashboard size={18} /> Panel</NavLink>
      {usuario?.empleado && (
        <NavLink to="/mi-ficha" className={claseEnlace} onClick={alElegir}><IdCard size={18} /> Mi ficha</NavLink>
      )}
      {usuario?.empleado && tienePermiso(usuario, 'asistencia.marcar_con_qr') && (
        <NavLink to="/mi-marcacion" className={claseEnlace} onClick={alElegir}><QrCode size={18} /> Ingreso / egreso por QR</NavLink>
      )}
      {usuario?.empleado && tienePermiso(usuario, 'asistencia.view_diaasistencia') && (
        <NavLink to="/mi-asistencia" className={claseEnlace} onClick={alElegir}><CalendarCheck size={18} /> Mi asistencia</NavLink>
      )}
      {usuario?.empleado && tienePermiso(usuario, 'licencias.view_solicitudlicencia') && (
        <NavLink to="/mis-licencias" className={claseEnlace} onClick={alElegir}><Palmtree size={18} /> Mis licencias</NavLink>
      )}
      {usuario?.empleado && tienePermiso(usuario, 'nomina.view_recibosueldo') && (
        <NavLink to="/mis-recibos" className={claseEnlace} onClick={alElegir}><Receipt size={18} /> Mis recibos</NavLink>
      )}
      {usuario?.empleado && tienePermiso(usuario, 'novedades.view_anticipo') && (
        <NavLink to="/mis-movimientos" className={claseEnlace} onClick={alElegir}><HandCoins size={18} /> Mis anticipos y descuentos</NavLink>
      )}

      {grupos.map(({ grupo, modulos }) => {
        const abierto = abiertos.includes(grupo)
        const IconoGrupo = ICONO_GRUPO[grupo]
        const idSubmenu = `submenu-${grupo}`
        return (
          <div key={grupo}>
            <button type="button" onClick={() => alternar(grupo)} aria-expanded={abierto} aria-controls={idSubmenu}
              className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium hover:bg-marca-50 ${
                grupo === grupoActual ? 'text-marca-800' : 'text-stone-800'}`}>
              <IconoGrupo size={18} />
              <span className="flex-1 text-left">{grupo}</span>
              <ChevronDown size={16} className={`text-stone-400 transition-transform ${abierto ? 'rotate-180' : ''}`} />
            </button>
            {abierto && (
              <div id={idSubmenu} className="mb-1 ml-5 space-y-0.5 border-l border-marca-100 pl-2">
                {modulos.map((m) => {
                  const Icono = m.icono
                  return (
                    <NavLink key={m.clave} to={rutaDe(m, usuario)} className={claseSubmenu} onClick={alElegir}>
                      <Icono size={16} /> {m.titulo}
                    </NavLink>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}

      <div className="mt-2 border-t border-stone-200 pt-2">
        <NavLink to="/manual" className={claseEnlace} onClick={alElegir}><BookOpen size={18} /> Manual</NavLink>
      </div>
    </nav>
  )
}
