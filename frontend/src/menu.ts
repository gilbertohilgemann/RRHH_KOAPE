/** Lo que muestran el Panel y el menú lateral: los grupos de módulos que
 * el usuario puede ver según sus permisos. El perfil Empleado no ve módulos
 * generales: solo "Mi ficha" (y lo suyo, en las fases siguientes). */
import { BarChart3, Building2, CalendarClock, Fingerprint, Palmtree, Settings, Users, Wallet, type LucideIcon } from 'lucide-react'
import { GRUPOS, MODULOS } from './modulos'
import { puedeVer, tieneAlcanceGeneral } from './permisos'
import type { DatosUsuario, Grupo, Modulo } from './tipos'

/** Ícono de cada grupo, que en el menú lateral es un menú desplegable. */
export const ICONO_GRUPO: Record<Grupo, LucideIcon> = {
  Personal: Users,
  Jornada: CalendarClock,
  Asistencia: Fingerprint,
  Licencias: Palmtree,
  'Nómina': Wallet,
  Reportes: BarChart3,
  Estructura: Building2,
  'Administración': Settings,
}

export function moduloVisible(usuario: DatosUsuario | null, modulo: Modulo): boolean {
  return !modulo.oculto && tieneAlcanceGeneral(usuario) && puedeVer(usuario, modulo)
}

export function gruposVisibles(usuario: DatosUsuario | null): { grupo: Grupo; modulos: Modulo[] }[] {
  return GRUPOS.map((grupo) => ({
    grupo,
    modulos: MODULOS.filter((m) => m.grupo === grupo && moduloVisible(usuario, m)),
  })).filter((g) => g.modulos.length > 0)
}

/** La empresa propia se abre directo en su ficha (la plataforma ve la lista de todas). */
export const rutaDe = (m: Modulo, usuario: DatosUsuario | null) =>
  m.rutaPropia ?? (m.clave === 'empresa' && usuario?.empresa ? `/m/empresa/${usuario.empresa.id}` : `/m/${m.clave}`)
