import type { DatosUsuario, Modulo } from './tipos'

// Los permisos vienen de la API (perfiles de Django del usuario, ajustables
// desde el admin). La API es la que realmente controla; acá solo se ocultan
// botones y pantallas que igual serían rechazados.

export function tienePermiso(usuario: DatosUsuario | null, permiso: string): boolean {
  if (!usuario) return false
  return usuario.permisos.includes('*') || usuario.permisos.includes(permiso)
}

function permisoDe(modulo: Modulo, tipo: 'view' | 'add' | 'change' | 'delete'): string {
  if (modulo.permisoPropio) return modulo.permisoPropio
  const [app, modelo] = modulo.modelo.split('.')
  return `${app}.${tipo}_${modelo}`
}

export function puedeVer(usuario: DatosUsuario | null, modulo: Modulo): boolean {
  return tienePermiso(usuario, permisoDe(modulo, 'view'))
}

export function puedeCrear(usuario: DatosUsuario | null, modulo: Modulo): boolean {
  return !modulo.sinAlta && !modulo.soloLectura && tienePermiso(usuario, permisoDe(modulo, 'add'))
}

export function puedeModificar(usuario: DatosUsuario | null, modulo: Modulo): boolean {
  return !modulo.soloLectura && tienePermiso(usuario, permisoDe(modulo, 'change'))
}

export function puedeBorrar(usuario: DatosUsuario | null, modulo: Modulo): boolean {
  return Boolean(modulo.permiteBorrar) && tienePermiso(usuario, permisoDe(modulo, 'delete'))
}

/** Ve los datos generales de RR. HH. (no solo los suyos). */
export function tieneAlcanceGeneral(usuario: DatosUsuario | null): boolean {
  return usuario?.nivel === 'plataforma' || usuario?.nivel === 'administrador' || usuario?.nivel === 'gestor'
}
