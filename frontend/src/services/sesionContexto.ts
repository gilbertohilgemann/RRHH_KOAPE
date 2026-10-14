import { createContext, useContext } from 'react'
import type { DatosUsuario } from '../tipos'

export interface ValorSesion {
  usuario: DatosUsuario | null
  cargando: boolean
  ingresar: (usuario: string, clave: string) => Promise<void>
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
