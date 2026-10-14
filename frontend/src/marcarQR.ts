/** Envío de un QR escaneado (lo usan "Ingreso / egreso por QR" y la ruta
 * /marcar/<código> que abre la cámara normal del teléfono). */
import axios from 'axios'
import api from './services/api'
import { mensajeDeError } from './formato'
import type { DatosMarca } from './components/TarjetaMarca'

export type ResultadoQR = ({ resultado: 'ok' } & DatosMarca) | { resultado: 'rechazado'; mensaje: string; codigo?: string }

/** El QR de la terminal lleva un enlace `…/marcar/<código>`; también se acepta el código solo. */
export function tokenDeQR(texto: string): string {
  const coincidencia = /\/marcar\/([A-Za-z0-9_-]+)/.exec(texto.trim())
  return coincidencia ? coincidencia[1] : texto.trim()
}

export async function enviarQR(token: string, tipo?: 'entrada' | 'salida' | null): Promise<ResultadoQR> {
  try {
    const r = await api.post<ResultadoQR>('/marcador/qr/', { token, ...(tipo ? { tipo } : {}) })
    return r.data
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.status === 429) {
      return { resultado: 'rechazado', mensaje: 'Demasiados intentos seguidos. Esperá un minuto.' }
    }
    return { resultado: 'rechazado', mensaje: mensajeDeError(axios.isAxiosError(err) ? err.response?.data : null, 'No se pudo conectar con el servidor.') }
  }
}
