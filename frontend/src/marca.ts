/** Aplica la identidad de la empresa del usuario (colores) sobre la de Koape.
 * Los valores por defecto viven en index.css; acá solo se reemplazan las
 * variables --marca y --marca-secundario, y el degradado del encabezado. */
import type { DatosUsuario } from './tipos'

export const LOGO_KOAPE = '/logo-koape.png'
// Los mismos que COLOR_PRIMARIO_KOAPE / COLOR_SECUNDARIO_KOAPE del backend (plataforma/models.py).
const PRIMARIO_KOAPE = '#E9264B'
const SECUNDARIO_KOAPE = '#F7941D'

export function aplicarMarca(usuario: DatosUsuario | null) {
  const estilo = document.documentElement.style
  const marca = usuario?.marca
  const coloresPropios = Boolean(marca) && (marca!.color_primario !== PRIMARIO_KOAPE || marca!.color_secundario !== SECUNDARIO_KOAPE)
  if (!coloresPropios) {
    estilo.removeProperty('--marca')
    estilo.removeProperty('--marca-secundario')
    estilo.removeProperty('--degradado-marca')
  } else {
    estilo.setProperty('--marca', marca!.color_primario)
    estilo.setProperty('--marca-secundario', marca!.color_secundario)
    estilo.setProperty('--degradado-marca', `linear-gradient(90deg, ${marca!.color_primario}, ${marca!.color_secundario})`)
  }
  // Color de la barra del navegador en el celular.
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', marca?.color_primario ?? PRIMARIO_KOAPE)
}

/** El logo a mostrar: el de la empresa si cargó uno, si no el de Koape. */
export function logoDe(usuario: DatosUsuario | null): string {
  return usuario?.marca?.logo || LOGO_KOAPE
}
