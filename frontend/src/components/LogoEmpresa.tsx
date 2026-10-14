import { useRef, useState } from 'react'
import axios from 'axios'
import { ImageUp, Trash2 } from 'lucide-react'
import api from '../services/api'
import { LOGO_KOAPE } from '../marca'
import { mensajeDeError } from '../formato'
import type { Marca } from '../tipos'

/** Logo de la empresa (debajo de "Datos de la empresa"): se sube o se
 * quita; sin logo propio se usa el de Koape. Al cambiar, se actualiza la
 * sesión para que se vea enseguida en el encabezado. */
export default function LogoEmpresa({ empresa, marca, editable, onCambio }: {
  empresa: number; marca: Marca | undefined; editable: boolean; onCambio: () => void
}) {
  const archivo = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const enviar = async (accion: () => Promise<unknown>) => {
    setError(null)
    setEnviando(true)
    try {
      await accion()
      onCambio()
    } catch (err) {
      const datos = axios.isAxiosError(err) ? err.response?.data as Record<string, unknown> | undefined : undefined
      setError(Array.isArray(datos?.logo) ? String(datos.logo[0]) : mensajeDeError(datos, 'No se pudo guardar el logo.'))
    } finally {
      setEnviando(false)
      if (archivo.current) archivo.current.value = ''
    }
  }

  const subir = (elegido: File | undefined) => {
    if (!elegido) return
    const datos = new FormData()
    datos.append('logo', elegido)
    enviar(() => api.post(`/empresas/${empresa}/logo/`, datos))
  }

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <h2 className="mb-1 font-semibold text-stone-800">Logo de la empresa</h2>
      <p className="mb-4 text-sm text-stone-500">
        Sale en el encabezado de la aplicación para todos los usuarios de la empresa, y en los recibos e informes.
        PNG, JPG o WEBP de hasta 2 MB, mejor con fondo transparente.
      </p>
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex h-24 w-40 items-center justify-center rounded-xl border border-dashed border-stone-300 bg-stone-50 p-2">
          <img src={marca?.logo || LOGO_KOAPE} alt="Logo actual" className="max-h-full max-w-full object-contain" />
        </div>
        <div className="space-y-2 text-sm">
          <p className="text-stone-600">{marca?.logo ? 'Logo propio de la empresa.' : 'Sin logo propio: se usa el de Koape.'}</p>
          {editable && (
            <div className="flex flex-wrap gap-2">
              <input ref={archivo} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                onChange={(e) => subir(e.target.files?.[0])} />
              <button type="button" disabled={enviando} onClick={() => archivo.current?.click()}
                className="flex items-center gap-1 rounded-lg bg-marca-700 px-3 py-2 font-medium text-white hover:bg-marca-600 disabled:opacity-60">
                <ImageUp size={16} /> {enviando ? 'Subiendo…' : marca?.logo ? 'Cambiar logo' : 'Subir logo'}
              </button>
              {marca?.logo && (
                <button type="button" disabled={enviando}
                  onClick={() => window.confirm('¿Quitar el logo? Vuelve a verse el de Koape.') && enviar(() => api.delete(`/empresas/${empresa}/logo/`))}
                  className="flex items-center gap-1 rounded-lg border border-red-300 px-3 py-2 font-medium text-red-700 hover:bg-red-50 disabled:opacity-60">
                  <Trash2 size={16} /> Quitar
                </button>
              )}
            </div>
          )}
        </div>
      </div>
      {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
    </div>
  )
}
