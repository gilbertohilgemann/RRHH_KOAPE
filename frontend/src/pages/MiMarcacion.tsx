import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import axios from 'axios'
import { ChevronLeft, KeyRound, LogIn, LogOut, QrCode, XCircle } from 'lucide-react'
import api from '../services/api'
import EscanerQR from '../components/EscanerQR'
import TarjetaMarca from '../components/TarjetaMarca'
import { enviarQR, tokenDeQR, type ResultadoQR } from '../marcarQR'
import { mensajeDeError } from '../formato'

interface Modalidades { qr: boolean; codigo_fijo: boolean; pide_tipo: boolean }
type Tipo = 'entrada' | 'salida'

/** "Ingreso / egreso por QR" (modalidad A, invertida): el empleado, con su
 * sesión iniciada, escanea el QR que proyecta la pantalla de la terminal. El
 * servidor registra la marca y esta pantalla y la de la terminal muestran
 * legajo, nombre, hora con segundos y la foto.
 *
 * También es la pantalla de /marcar/<código>: el QR lleva ese enlace, así que
 * escaneándolo con la cámara normal del teléfono se abre acá y marca sola. */
export default function MiMarcacion() {
  const { token: tokenDelEnlace } = useParams()
  const [modalidades, setModalidades] = useState<Modalidades | null>(null)
  const [tipo, setTipo] = useState<Tipo | null>(null)
  const [escaneando, setEscaneando] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [resultado, setResultado] = useState<ResultadoQR | null>(null)
  const [pendiente, setPendiente] = useState<string | null>(tokenDelEnlace ?? null)
  const [codigo, setCodigo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<Modalidades>('/marcador/mi-marcador/').then((r) => setModalidades(r.data))
      .catch(() => setModalidades({ qr: false, codigo_fijo: false, pide_tipo: false }))
  }, [])

  const enviar = useCallback(async (token: string, tipoElegido: Tipo | null) => {
    setEnviando(true)
    setEscaneando(false)
    setResultado(await enviarQR(token, tipoElegido))
    setPendiente(null)
    setEnviando(false)
  }, [])

  // Con el enlace de la cámara del teléfono: se envía solo (o después de elegir entrada/salida).
  useEffect(() => {
    if (!pendiente || !modalidades || enviando) return
    if (modalidades.pide_tipo && !tipo) return
    enviar(pendiente, tipo)
  }, [pendiente, modalidades, tipo, enviando, enviar])

  const leido = useCallback((texto: string) => setPendiente(tokenDeQR(texto)), [])

  const empezar = (t: Tipo | null) => {
    setTipo(t)
    setResultado(null)
    setEscaneando(true)
  }

  const verCodigo = async () => {
    try {
      const r = await api.get<{ codigo: string | null }>('/marcador/mi-codigo/')
      setCodigo(r.data.codigo ?? 'Todavía no tenés un código asignado.')
    } catch (err) {
      setError(mensajeDeError(axios.isAxiosError(err) ? err.response?.data : null, 'No se pudo consultar tu código.'))
    }
  }

  const pideTipo = Boolean(modalidades?.pide_tipo)

  return (
    <div className="mx-auto max-w-md space-y-4">
      <div className="flex items-center gap-2">
        <Link to="/" aria-label="Volver al panel" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
        <h1 className="text-xl font-bold text-stone-900">Ingreso / egreso por QR</h1>
      </div>

      {modalidades && !modalidades.qr && !modalidades.codigo_fijo && (
        <p className="rounded-2xl bg-white p-4 text-stone-600 shadow-sm">Tu empresa no tiene habilitada la marcación desde el celular.</p>
      )}

      {modalidades?.qr && (
        <div className="space-y-4 rounded-2xl bg-white p-5 text-center shadow-sm ring-1 ring-stone-200">
          {enviando ? <p className="py-10 text-lg text-stone-600">Registrando…</p>
            : resultado?.resultado === 'ok' ? (
              <>
                <TarjetaMarca marca={resultado} cliente={api} rutaFoto={`/empleados/${resultado.empleado_id}/foto/`} />
                <p className="text-xs text-stone-500">Confirmado por el servidor. La pantalla de la terminal muestra lo mismo.</p>
                <button type="button" onClick={() => setResultado(null)} className="rounded-lg border border-marca-700 px-4 py-2 text-sm font-medium text-marca-800">Listo</button>
              </>
            ) : pendiente && pideTipo && !tipo ? (
              <>
                <p className="text-stone-700">¿Es entrada o salida?</p>
                <BotonesTipo onElegir={setTipo} />
              </>
            ) : escaneando ? (
              <>
                <p className="text-stone-700">Apuntá al QR de la pantalla de la terminal{tipo ? ` (${tipo})` : ''}.</p>
                <EscanerQR activo={escaneando} onLeido={leido} />
                <button type="button" onClick={() => setEscaneando(false)} className="rounded-lg border border-stone-300 px-4 py-2 text-sm">Cancelar</button>
              </>
            ) : (
              <>
                {resultado?.resultado === 'rechazado' && (
                  <p className="flex items-center justify-center gap-2 rounded-lg bg-red-50 px-3 py-3 text-red-800">
                    <XCircle size={18} /> No se registró: {resultado.mensaje}
                  </p>
                )}
                <QrCode size={56} className="mx-auto text-marca-700" />
                <p className="text-sm text-stone-600">Escaneá el QR que muestra la pantalla de la terminal. Cambia cada pocos segundos, así que escaneá el que ves en el momento.</p>
                {pideTipo ? <BotonesTipo onElegir={empezar} /> : (
                  <button type="button" onClick={() => empezar(null)}
                    className="w-full rounded-xl bg-marca-700 px-6 py-4 text-lg font-semibold text-white hover:bg-marca-600">
                    Escanear QR
                  </button>
                )}
                <p className="text-xs text-stone-500">También podés escanearlo con la cámara normal de tu teléfono: abre esta aplicación y marca sola.</p>
              </>
            )}
        </div>
      )}

      {modalidades?.codigo_fijo && (
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-stone-200">
          <h2 className="mb-2 flex items-center gap-2 font-semibold text-stone-800"><KeyRound size={18} /> Mi código fijo</h2>
          <p className="mb-3 text-sm text-stone-600">Para marcar tecleándolo en la terminal. No lo compartas: es personal.</p>
          {codigo ? <p className="text-center font-mono text-3xl tracking-[0.3em] text-stone-900">{codigo}</p> : (
            <button type="button" onClick={verCodigo} className="rounded-lg border border-marca-700 px-4 py-2 text-sm font-medium text-marca-800">Mostrar mi código</button>
          )}
        </div>
      )}

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
    </div>
  )
}

function BotonesTipo({ onElegir }: { onElegir: (t: Tipo) => void }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <button type="button" onClick={() => onElegir('entrada')}
        className="flex items-center justify-center gap-2 rounded-xl bg-green-700 px-4 py-4 text-lg font-semibold text-white hover:bg-green-600">
        <LogIn /> Entrada
      </button>
      <button type="button" onClick={() => onElegir('salida')}
        className="flex items-center justify-center gap-2 rounded-xl bg-sky-700 px-4 py-4 text-lg font-semibold text-white hover:bg-sky-600">
        <LogOut /> Salida
      </button>
    </div>
  )
}
