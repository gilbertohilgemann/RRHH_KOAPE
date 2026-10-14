import { useEffect, useRef, useState } from 'react'
import jsQR from 'jsqr'
import { CameraOff } from 'lucide-react'

/** Lee un QR con la cámara trasera del celular (jsQR sobre cada cuadro del
 * video). El navegador solo da la cámara en HTTPS o en localhost: si no
 * puede, avisa y se puede escanear con la cámara normal del teléfono. */
export default function EscanerQR({ activo, onLeido }: { activo: boolean; onLeido: (texto: string) => void }) {
  const [error, setError] = useState<string | null>(null)
  const video = useRef<HTMLVideoElement>(null)
  const lienzo = useRef<HTMLCanvasElement>(null)
  const avisar = useRef(onLeido)
  useEffect(() => { avisar.current = onLeido }, [onLeido])
  const disponible = typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia)

  useEffect(() => {
    if (!activo || !disponible) return
    let flujo: MediaStream | null = null
    let cuadro = 0
    let cancelado = false
    let leido = false
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } }).then((s) => {
      if (cancelado) { s.getTracks().forEach((t) => t.stop()); return }
      flujo = s
      if (video.current) { video.current.srcObject = s; video.current.play().catch(() => undefined) }
      const analizar = () => {
        const v = video.current, c = lienzo.current
        if (!leido && v && c && v.readyState === v.HAVE_ENOUGH_DATA) {
          c.width = v.videoWidth
          c.height = v.videoHeight
          const ctx = c.getContext('2d', { willReadFrequently: true })
          if (ctx) {
            ctx.drawImage(v, 0, 0, c.width, c.height)
            const resultado = jsQR(ctx.getImageData(0, 0, c.width, c.height).data, c.width, c.height)
            if (resultado?.data) {
              leido = true
              avisar.current(resultado.data)
            }
          }
        }
        if (!leido) cuadro = requestAnimationFrame(analizar)
      }
      cuadro = requestAnimationFrame(analizar)
    }).catch(() => setError('No se pudo usar la cámara (permiso denegado o la conexión no es HTTPS).'))
    return () => { cancelado = true; cancelAnimationFrame(cuadro); flujo?.getTracks().forEach((t) => t.stop()) }
  }, [activo, disponible])

  if (!disponible || error) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-2xl bg-stone-100 p-4 text-center text-sm text-stone-700">
        <CameraOff className="text-stone-500" />
        <p>{error ?? 'La cámara no está disponible en esta conexión (hace falta HTTPS).'}</p>
        <p><strong>Escaneá el QR de la pantalla con la cámara normal de tu teléfono</strong>: abre esta aplicación y la marca se registra sola.</p>
      </div>
    )
  }
  return (
    <div className="relative mx-auto aspect-square w-full max-w-xs overflow-hidden rounded-2xl bg-black">
      <video ref={video} muted playsInline className="h-full w-full object-cover" />
      <div className="pointer-events-none absolute inset-8 rounded-xl border-4 border-white/80" />
      <canvas ref={lienzo} className="hidden" />
    </div>
  )
}
