// Cliente de la API para la pantalla de terminal (/terminal). La terminal no
// es un usuario: se autentica con su propia clave (`Authorization: Terminal …`),
// que genera un administrador y se guarda en este dispositivo.
import axios from 'axios'

const PUERTO_BACKEND = 8004
const CLAVE_GUARDADA = 'koape_rrhh_terminal'

export function leerClaveTerminal(): string | null {
  try {
    return localStorage.getItem(CLAVE_GUARDADA)
  } catch {
    return null
  }
}

export function guardarClaveTerminal(clave: string | null) {
  try {
    if (clave) localStorage.setItem(CLAVE_GUARDADA, clave)
    else localStorage.removeItem(CLAVE_GUARDADA)
  } catch {
    // Sin almacenamiento: habrá que volver a pegar la clave al recargar.
  }
}

const apiTerminal = axios.create({
  baseURL: import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.hostname}:${PUERTO_BACKEND}/api`,
})

apiTerminal.interceptors.request.use((config) => {
  const clave = leerClaveTerminal()
  if (clave) config.headers.Authorization = `Terminal ${clave}`
  return config
})

export default apiTerminal
