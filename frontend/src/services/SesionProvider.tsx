import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import api, { guardarToken, leerToken } from './api'
import { SesionContexto } from './sesionContexto'
import { aplicarMarca } from '../marca'
import type { DatosUsuario } from '../tipos'

export function SesionProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<DatosUsuario | null>(null)
  const [cargando, setCargando] = useState(() => leerToken() !== null)

  // Colores de la empresa del usuario (o los de Koape sin sesión).
  useEffect(() => { aplicarMarca(usuario) }, [usuario])

  // Si quedó un token guardado de antes, se confirma que siga siendo válido.
  useEffect(() => {
    if (!leerToken()) return
    api.get<DatosUsuario>('/sesion/yo/')
      .then((r) => setUsuario(r.data))
      .catch(() => guardarToken(null))
      .finally(() => setCargando(false))
  }, [])

  const ingresar = useCallback(async (nombreUsuario: string, clave: string) => {
    const r = await api.post<{ token: string; usuario: DatosUsuario }>('/sesion/ingresar/', {
      usuario: nombreUsuario,
      clave,
    })
    guardarToken(r.data.token)
    setUsuario(r.data.usuario)
  }, [])

  const salir = useCallback(async () => {
    try {
      await api.post('/sesion/salir/')
    } catch {
      // Aunque el servidor no responda, localmente la sesión se cierra igual.
    }
    guardarToken(null)
    setUsuario(null)
  }, [])

  /** Datos de la sesión al día: los perfiles y permisos pueden cambiar
   * mientras el usuario está conectado (los cambia un administrador). */
  const actualizar = useCallback(async () => {
    if (!leerToken()) return
    try {
      const r = await api.get<DatosUsuario>('/sesion/yo/')
      // Solo si algo cambió: un objeto nuevo haría redibujar (y recalcular) todo.
      setUsuario((antes) => (JSON.stringify(antes) === JSON.stringify(r.data) ? antes : r.data))
    } catch {
      // Si falla (sin conexión), se sigue con lo que había.
    }
  }, [])

  // Al volver a la pestaña o a la aplicación, y cada 2 minutos.
  const hayUsuario = usuario !== null
  useEffect(() => {
    if (!hayUsuario) return
    let ultima = Date.now()
    const siHaceFalta = () => {
      if (Date.now() - ultima < 30_000) return
      ultima = Date.now()
      actualizar()
    }
    const alVolver = () => { if (document.visibilityState === 'visible') siHaceFalta() }
    document.addEventListener('visibilitychange', alVolver)
    window.addEventListener('focus', siHaceFalta)
    const intervalo = window.setInterval(() => { ultima = 0; siHaceFalta() }, 120_000)
    return () => {
      document.removeEventListener('visibilitychange', alVolver)
      window.removeEventListener('focus', siHaceFalta)
      window.clearInterval(intervalo)
    }
    // Solo depende de si hay sesión, no de cada actualización de sus datos.
  }, [hayUsuario, actualizar])

  const valor = useMemo(() => ({ usuario, cargando, ingresar, salir, actualizar }), [usuario, cargando, ingresar, salir, actualizar])

  return <SesionContexto.Provider value={valor}>{children}</SesionContexto.Provider>
}
