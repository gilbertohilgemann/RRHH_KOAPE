import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { ImageUp, Trash2, UserRound } from 'lucide-react'
import api from '../services/api'
import { mensajeDeError } from '../formato'

/** Foto del legajo: se ve en la terminal y en el celular al marcar. Es
 * privada (se pide con la sesión) y el servidor la achica y le quita los
 * datos EXIF. Subirla o quitarla exige poder modificar el legajo. */
export default function FotoEmpleado({ empleado, tieneFoto, editable, onCambio }: {
  empleado: number; tieneFoto: boolean; editable: boolean; onCambio: () => void
}) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [version, setVersion] = useState(0)
  const archivo = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!tieneFoto) return
    let creada: string | null = null
    let vigente = true
    api.get<Blob>(`/empleados/${empleado}/foto/`, { responseType: 'blob' })
      .then((r) => { if (vigente) { creada = URL.createObjectURL(r.data); setUrl(creada) } })
      .catch(() => undefined)
    return () => { vigente = false; if (creada) URL.revokeObjectURL(creada) }
  }, [empleado, tieneFoto, version])

  const enviar = async (accion: () => Promise<unknown>) => {
    setError(null)
    setEnviando(true)
    try {
      await accion()
      setVersion((v) => v + 1)
      onCambio()
    } catch (err) {
      const datos = axios.isAxiosError(err) ? err.response?.data as Record<string, unknown> | undefined : undefined
      setError(Array.isArray(datos?.foto) ? String(datos.foto[0]) : mensajeDeError(datos, 'No se pudo guardar la foto.'))
    } finally {
      setEnviando(false)
      if (archivo.current) archivo.current.value = ''
    }
  }

  const subir = (elegido: File | undefined) => {
    if (!elegido) return
    const datos = new FormData()
    datos.append('foto', elegido)
    enviar(() => api.post(`/empleados/${empleado}/foto/`, datos))
  }

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <h2 className="mb-1 font-semibold text-stone-800">Foto</h2>
      <p className="mb-4 text-sm text-stone-500">Se muestra en la pantalla de la terminal y en el celular del empleado al marcar. JPG, PNG o WEBP de hasta 5 MB.</p>
      <div className="flex flex-wrap items-center gap-4">
        <div className="h-36 w-28 overflow-hidden rounded-xl border border-stone-200 bg-stone-50">
          {tieneFoto && url ? <img src={url} alt="Foto del empleado" className="h-full w-full object-cover" />
            : <UserRound className="h-full w-full p-5 text-stone-300" />}
        </div>
        {editable && (
          <div className="flex flex-wrap gap-2">
            <input ref={archivo} type="file" accept="image/jpeg,image/png,image/webp" capture="user" className="hidden"
              onChange={(e) => subir(e.target.files?.[0])} />
            <button type="button" disabled={enviando} onClick={() => archivo.current?.click()}
              className="flex items-center gap-1 rounded-lg bg-marca-700 px-3 py-2 text-sm font-medium text-white hover:bg-marca-600 disabled:opacity-60">
              <ImageUp size={16} /> {enviando ? 'Subiendo…' : tieneFoto ? 'Cambiar foto' : 'Subir foto'}
            </button>
            {tieneFoto && (
              <button type="button" disabled={enviando}
                onClick={() => window.confirm('¿Quitar la foto?') && enviar(() => api.delete(`/empleados/${empleado}/foto/`))}
                className="flex items-center gap-1 rounded-lg border border-red-300 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60">
                <Trash2 size={16} /> Quitar
              </button>
            )}
          </div>
        )}
      </div>
      {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
    </div>
  )
}
