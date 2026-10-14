import api from './services/api'

/** Baja un archivo protegido de la API (con el token) y lo guarda con su nombre. */
export async function descargarArchivo(ruta: string, nombre: string) {
  const r = await api.get<Blob>(ruta, { responseType: 'blob' })
  const url = URL.createObjectURL(r.data)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombre
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
