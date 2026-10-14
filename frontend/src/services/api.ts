// Instancia de axios usada por toda la app. La URL base se toma de
// VITE_API_URL (frontend/.env) si está seteada — pensado para producción,
// donde el backend puede estar en otro host/puerto. Si no está seteada, se
// arma sola a partir del host desde el que se está viendo la página (mismo
// dominio/IP, puerto 8004): así funciona igual en localhost, en la IP de la
// red local (celular) o en el dominio real, sin tocar nada.
import axios from 'axios'

// Mismo puerto que usan start.ps1 / start.sh para el backend.
const PUERTO_BACKEND = 8004
const defaultApiUrl = `${window.location.protocol}//${window.location.hostname}:${PUERTO_BACKEND}/api`

const CLAVE_TOKEN = 'koape_rrhh_token'

// localStorage puede no estar disponible (navegación privada, almacenamiento
// bloqueado): en ese caso la sesión simplemente no sobrevive a recargar.
export function leerToken(): string | null {
  try {
    return localStorage.getItem(CLAVE_TOKEN)
  } catch {
    return null
  }
}

export function guardarToken(token: string | null) {
  try {
    if (token) localStorage.setItem(CLAVE_TOKEN, token)
    else localStorage.removeItem(CLAVE_TOKEN)
  } catch {
    // Sin almacenamiento disponible: se sigue sin recordar la sesión.
  }
}

// Dirección de acceso de la empresa por la que se entró (hhrr.koapesystem.com/<dirección>):
// al salir o al vencer la sesión se vuelve a ese mismo ingreso personalizado.
const CLAVE_ACCESO = 'koape_rrhh_acceso'

export function guardarAcceso(direccion: string | null) {
  try {
    if (direccion) localStorage.setItem(CLAVE_ACCESO, direccion)
    else localStorage.removeItem(CLAVE_ACCESO)
  } catch {
    // Sin almacenamiento: se vuelve al ingreso estándar.
  }
}

/** La pantalla de ingreso a la que hay que volver: la de la empresa, o la estándar. */
export function rutaIngreso(): string {
  try {
    const direccion = localStorage.getItem(CLAVE_ACCESO)
    return direccion ? `/${direccion}` : '/ingresar'
  } catch {
    return '/ingresar'
  }
}

// Sin 'Content-Type' fijo: axios pone application/json para los objetos y
// multipart/form-data (con su separador) para los FormData. Si se fijara
// application/json, axios convertiría los FormData a JSON y los archivos
// (documentos, logos) se perderían en el camino.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || defaultApiUrl,
})

api.interceptors.request.use((config) => {
  const token = leerToken()
  if (token) config.headers.Authorization = `Token ${token}`
  return config
})

// Token vencido o borrado (por ejemplo, se cerró sesión en otro dispositivo):
// se descarta y se vuelve a la pantalla de ingreso.
api.interceptors.response.use(
  (respuesta) => respuesta,
  (error) => {
    const url: string = error.config?.url ?? ''
    if (error.response?.status === 401 && !url.includes('sesion/ingresar')) {
      guardarToken(null)
      const ingreso = rutaIngreso()
      if (window.location.pathname !== ingreso) window.location.assign(ingreso)
    }
    return Promise.reject(error)
  },
)

export default api
