import { useEffect, useState } from 'react'
import type { AxiosInstance } from 'axios'
import { CheckCircle2, UserRound } from 'lucide-react'

export interface DatosMarca {
  id: number
  legajo: string
  empleado: string
  empleado_id: number
  tipo: string
  tipo_texto: string
  hora: string
  fecha: string
  tiene_foto: boolean
  aviso?: string | null
  terminal?: string
}

/** Foto privada pedida con el cliente que corresponda (sesión del empleado o
 * clave de la terminal) y mostrada desde memoria. */
function useFoto(cliente: AxiosInstance, ruta: string | null) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!ruta) return
    let creada: string | null = null
    let vigente = true
    cliente.get<Blob>(ruta, { responseType: 'blob' })
      .then((r) => { if (vigente) { creada = URL.createObjectURL(r.data); setUrl(creada) } })
      .catch(() => undefined)
    return () => { vigente = false; if (creada) URL.revokeObjectURL(creada) }
  }, [cliente, ruta])
  return ruta ? url : null
}

/** Lo que muestran ambas pantallas al registrarse una marca: foto (si hay),
 * legajo, nombre, entrada o salida y la hora con segundos. */
export default function TarjetaMarca({ marca, cliente, rutaFoto, grande }: {
  marca: DatosMarca; cliente: AxiosInstance; rutaFoto: string | null; grande?: boolean
}) {
  const foto = useFoto(cliente, marca.tiene_foto ? rutaFoto : null)
  const entrada = marca.tipo === 'entrada'
  return (
    <div className={`flex flex-col items-center gap-3 rounded-3xl text-center text-white ${entrada ? 'bg-green-700' : 'bg-sky-700'} ${grande ? 'px-12 py-8' : 'px-6 py-6'}`}>
      <div className={`overflow-hidden rounded-2xl bg-white/20 ${grande ? 'h-56 w-44' : 'h-40 w-32'}`}>
        {foto
          ? <img src={foto} alt={`Foto de ${marca.empleado}`} className="h-full w-full object-cover" />
          : <UserRound className="h-full w-full p-6 text-white/70" />}
      </div>
      <p className={`flex items-center gap-2 font-bold ${grande ? 'text-4xl' : 'text-2xl'}`}>
        <CheckCircle2 size={grande ? 40 : 28} /> {marca.tipo_texto} registrada
      </p>
      <p className={grande ? 'text-3xl font-semibold' : 'text-xl font-semibold'}>{marca.empleado}</p>
      <p className={grande ? 'text-2xl' : 'text-lg'}>Legajo {marca.legajo}</p>
      <p className={`font-bold tabular-nums ${grande ? 'text-6xl' : 'text-4xl'}`}>{marca.hora}</p>
      <p className="text-sm text-white/80">{marca.fecha}{marca.terminal ? ` · ${marca.terminal}` : ''}</p>
      {marca.aviso && <p className="rounded-xl bg-amber-400 px-4 py-2 text-sm font-medium text-stone-900">⚠ {marca.aviso} RR. HH. lo va a revisar.</p>}
    </div>
  )
}
