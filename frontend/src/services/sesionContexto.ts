import { createContext, useContext } from 'react'
import type { DatosUsuario } from '../tipos'

export interface ValorSesion {
  usuario: DatosUsuario | null
  cargando: boolean
  /** `empresa`: la dirección de acceso si se entró por /<dirección> (solo entran usuarios de esa empresa). */
  ingresar: (usuario: string, clave: string, empresa?: string) => Promise<void>
  salir: () => Promise<void>
  /** Vuelve a pedir los datos de la sesión (permisos, perfiles…). */
  actualizar: () => Promise<void>
}

export const SesionContexto = createContext<ValorSesion | null>(null)

export function useSesion(): ValorSesion {
  const valor = useContext(SesionContexto)
  if (!valor) throw new Error('useSesion tiene que usarse dentro de <SesionProvider>')
  return valor
}
