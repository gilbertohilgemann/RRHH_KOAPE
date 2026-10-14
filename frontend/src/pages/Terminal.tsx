import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import axios from 'axios'
import QRCode from 'qrcode'
import { Delete, KeyRound, LogIn, LogOut as Salir, QrCode, XCircle } from 'lucide-react'
import apiTerminal, { guardarClaveTerminal, leerClaveTerminal } from '../services/apiTerminal'
import TarjetaMarca, { type DatosMarca } from '../components/TarjetaMarca'
import { aplicarMarca, LOGO_KOAPE } from '../marca'
import type { DatosUsuario, Marca } from '../tipos'

interface DatosTerminal {
  terminal: { id: number; codigo: string; nombre: string; ubicacion: string; tipo: string }
  empresa: string
  marca: Marca
  qr: boolean
  codigo_fijo: boolean
  pide_tipo: boolean
  largo_codigo: number
  /** Base del enlace del QR, alcanzable desde el celular (nunca localhost). */
  url_app: string
}
interface EstadoPantalla {
  qr: { id: number; token: string | null; vence_en: string; segundos: number } | null
  eventos: DatosMarca[]
}
type ResultadoCodigo = ({ resultado: 'ok' } & DatosMarca) | { resultado: 'rechazado'; mensaje: string }

const SEGUNDOS_TARJETA = 6
const INTERVALO_CONSULTA_MS = 1000

/** Pantalla de la terminal de marcación (TV, monitor o tablet en la entrada).
 * No usa usuario: se vincula una vez con la clave de la terminal.
 *
 * Proyecta un QR dinámico que genera el servidor (cambia cada pocos segundos
 * y apenas alguien lo usa). El empleado lo escanea con su celular, con su
 * sesión iniciada; cuando el servidor registra la marca, esta pantalla muestra
 * legajo, nombre, hora con segundos y la foto. El QR lleva un enlace a la
 * aplicación (…/marcar/<código>), así funciona también con la cámara normal
 * del teléfono. Si la empresa lo habilita, también acepta el código fijo. */
export default function Terminal() {
  const [datos, setDatos] = useState<DatosTerminal | null>(null)
  const [vinculada, setVinculada] = useState(() => leerClaveTerminal() !== null)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      const r = await apiTerminal.get<DatosTerminal>('/terminal/yo/')
      setDatos(r.data)
      setError(null)
      aplicarMarca({ marca: r.data.marca } as DatosUsuario)
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        guardarClaveTerminal(null)
        setVinculada(false)
        setError('La clave de esta terminal ya no es válida (se regeneró o la terminal se desactivó).')
      } else {
        setError('No se pudo conectar con el servidor. Reintentando…')
      }
    }
  }, [])

  useEffect(() => {
    if (!vinculada) return
    cargar()
    const intervalo = window.setInterval(cargar, 5 * 60_000)
    return () => window.clearInterval(intervalo)
  }, [vinculada, cargar])

  if (!vinculada) return <Vincular error={error} onListo={() => setVinculada(true)} />
  if (!datos) return <div className="flex min-h-screen items-center justify-center bg-stone-900 text-stone-300">{error ?? 'Cargando…'}</div>
  return <Kiosco datos={datos} onDesvincular={() => { guardarClaveTerminal(null); setVinculada(false); setDatos(null) }} />
}

function Vincular({ error, onListo }: { error: string | null; onListo: () => void }) {
  const [clave, setClave] = useState('')
  const [mensaje, setMensaje] = useState<string | null>(error)
  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    guardarClaveTerminal(clave.trim())
    try {
      await apiTerminal.get('/terminal/yo/')
      onListo()
    } catch {
      guardarClaveTerminal(null)
      setMensaje('Clave incorrecta o terminal inactiva.')
    }
  }
  return (
    <div className="fondo-app flex min-h-screen items-center justify-center px-4">
      <form onSubmit={enviar} className="w-full max-w-md space-y-4 rounded-2xl bg-white p-8 shadow-md ring-1 ring-stone-200">
        <img src={LOGO_KOAPE} alt="Koape" className="mx-auto h-16 w-16" />
        <h1 className="text-center text-xl font-bold text-stone-900">Vincular esta terminal</h1>
        <p className="text-sm text-stone-600">
          Pegá la clave que se generó en <strong>Asistencia → Terminales → Generar clave</strong>. Se guarda solo en este
          dispositivo; si la regenerás, hay que vincularla de nuevo.
        </p>
        <input value={clave} onChange={(e) => setClave(e.target.value)} required placeholder="Clave de la terminal"
          className="w-full rounded-lg border border-stone-300 p-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-marca-600" />
        {mensaje && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{mensaje}</p>}
        <button type="submit" className="flex w-full items-center justify-center gap-2 rounded-lg bg-marca-700 px-6 py-2.5 font-medium text-white hover:bg-marca-600">
          <LogIn size={18} /> Vincular
        </button>
      </form>
    </div>
  )
}

function Kiosco({ datos, onDesvincular }: { datos: DatosTerminal; onDesvincular: () => void }) {
  const [modo, setModo] = useState<'qr' | 'codigo'>(datos.qr ? 'qr' : 'codigo')
  const [qr, setQr] = useState<{ id: number; token: string; venceEn: number } | null>(null)
  const [tarjeta, setTarjeta] = useState<DatosMarca | null>(null)
  const [rechazo, setRechazo] = useState<string | null>(null)
  const [sinConexion, setSinConexion] = useState(false)
  const [ahora, setAhora] = useState(() => new Date())
  const ultimaMarca = useRef(0)
  const qrActual = useRef<number | null>(null)

  useEffect(() => {
    const reloj = window.setInterval(() => setAhora(new Date()), 250)
    return () => window.clearInterval(reloj)
  }, [])

  // Consulta al servidor cada segundo: QR a mostrar y marcas nuevas en esta terminal.
  useEffect(() => {
    if (modo !== 'qr') return
    let vigente = true
    const consultar = async () => {
      try {
        const r = await apiTerminal.get<EstadoPantalla>('/terminal/qr/', {
          params: { actual: qrActual.current ?? undefined, desde: ultimaMarca.current },
        })
        if (!vigente) return
        setSinConexion(false)
        const nuevo = r.data.qr
        if (nuevo && nuevo.token) {
          qrActual.current = nuevo.id
          setQr({ id: nuevo.id, token: nuevo.token, venceEn: Date.now() + nuevo.segundos * 1000 })
        } else if (!nuevo) {
          qrActual.current = null
          setQr(null)
        }
        if (r.data.eventos.length) {
          const ultimo = r.data.eventos[r.data.eventos.length - 1]
          // Al arrancar no se muestran las marcas viejas: solo las que llegan después.
          if (ultimaMarca.current !== 0) setTarjeta(ultimo)
          ultimaMarca.current = ultimo.id
        } else if (ultimaMarca.current === 0) {
          ultimaMarca.current = -1
        }
      } catch {
        if (vigente) setSinConexion(true)
      }
    }
    consultar()
    const intervalo = window.setInterval(consultar, INTERVALO_CONSULTA_MS)
    return () => { vigente = false; window.clearInterval(intervalo) }
  }, [modo])

  useEffect(() => {
    if (!tarjeta) return
    const espera = window.setTimeout(() => setTarjeta(null), SEGUNDOS_TARJETA * 1000)
    return () => window.clearTimeout(espera)
  }, [tarjeta])

  useEffect(() => {
    if (!rechazo) return
    const espera = window.setTimeout(() => setRechazo(null), 4000)
    return () => window.clearTimeout(espera)
  }, [rechazo])

  const restan = qr ? Math.max(Math.ceil((qr.venceEn - ahora.getTime()) / 1000), 0) : 0

  return (
    <div className="flex min-h-screen flex-col bg-stone-900 text-white">
      <div className="franja-marca" />
      <header className="flex items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-center gap-3">
          <img src={datos.marca.logo || LOGO_KOAPE} alt="" className="h-12 w-auto max-w-[10rem] rounded bg-white object-contain p-1" />
          <div>
            <p className="text-lg font-semibold">{datos.empresa}</p>
            <p className="text-sm text-stone-400">{datos.terminal.nombre}{datos.terminal.ubicacion && ` · ${datos.terminal.ubicacion}`}</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-4xl font-bold tabular-nums">{ahora.toLocaleTimeString('es-PY', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</p>
          <p className="text-sm text-stone-400">{ahora.toLocaleDateString('es-PY', { weekday: 'long', day: 'numeric', month: 'long' })}</p>
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center gap-8 px-6 pb-6 lg:flex-row lg:items-center">
        {modo === 'qr' ? (
          <>
            <div className="flex flex-col items-center gap-3">
              <p className="text-2xl font-semibold">Escaneá este QR con tu celular</p>
              <p className="text-stone-400">Koape RR. HH. → Ingreso / egreso por QR (o la cámara del teléfono)</p>
              {qr ? <QRProyectado enlace={`${datos.url_app}/marcar/${qr.token}`} /> : (
                <div className="flex h-[22rem] w-[22rem] items-center justify-center rounded-3xl bg-stone-800 text-stone-400">
                  {datos.qr ? 'Generando QR…' : 'El QR no está habilitado para esta terminal.'}
                </div>
              )}
              {qr && <p className={`text-xl tabular-nums ${restan <= 5 ? 'text-amber-300' : 'text-stone-300'}`}>Cambia en {restan} s</p>}
              <p className="text-xs text-stone-500">Abre {datos.url_app}</p>
              {sinConexion && <p className="rounded-lg bg-red-800 px-3 py-1 text-sm">Sin conexión con el servidor: reintentando…</p>}
            </div>
            {tarjeta && (
              <div className="w-full max-w-md">
                <TarjetaMarca marca={tarjeta} cliente={apiTerminal} rutaFoto={`/terminal/foto/${tarjeta.id}/`} grande />
              </div>
            )}
          </>
        ) : (
          <ModoCodigo datos={datos} onMarca={(r) => (r.resultado === 'ok' ? setTarjeta(r) : setRechazo(r.mensaje))}
            tarjeta={tarjeta} rechazo={rechazo} />
        )}
      </main>

      <footer className="flex items-center justify-between gap-2 px-6 pb-4 text-sm text-stone-400">
        <div>
          {datos.qr && datos.codigo_fijo && (
            <button type="button" onClick={() => { setModo(modo === 'qr' ? 'codigo' : 'qr'); setTarjeta(null) }}
              className="flex items-center gap-2 rounded-lg bg-stone-800 px-4 py-2 text-base text-white hover:bg-stone-700">
              {modo === 'qr' ? <><KeyRound size={18} /> Marcar con código</> : <><QrCode size={18} /> Volver al QR</>}
            </button>
          )}
        </div>
        <span>Koape RR. HH. · la hora válida es la del servidor</span>
        <button type="button" onClick={() => window.confirm('¿Desvincular esta terminal? Hará falta la clave para volver a usarla.') && onDesvincular()}
          className="flex items-center gap-1 text-stone-500 hover:text-stone-300"><Salir size={14} /> Desvincular</button>
      </footer>
    </div>
  )
}

/** El QR lleva el enlace a la aplicación con el código (nunca datos personales). */
function QRProyectado({ enlace }: { enlace: string }) {
  const lienzo = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    if (lienzo.current) {
      QRCode.toCanvas(lienzo.current, enlace, { width: 352, margin: 2, errorCorrectionLevel: 'M' }).catch(() => undefined)
    }
  }, [enlace])
  return <canvas ref={lienzo} className="rounded-3xl bg-white" />
}

function ModoCodigo({ datos, onMarca, tarjeta, rechazo }: {
  datos: DatosTerminal; onMarca: (r: ResultadoCodigo) => void; tarjeta: DatosMarca | null; rechazo: string | null
}) {
  const [tipo, setTipo] = useState<'entrada' | 'salida' | null>(null)
  const [codigo, setCodigo] = useState('')
  const [enviando, setEnviando] = useState(false)

  const enviar = async () => {
    setEnviando(true)
    try {
      const r = await apiTerminal.post<ResultadoCodigo>('/terminal/codigo/', { codigo, ...(tipo ? { tipo } : {}) })
      onMarca(r.data)
    } catch (err) {
      const respuesta = axios.isAxiosError(err) ? err.response?.data as { mensaje?: string } | undefined : undefined
      onMarca({ resultado: 'rechazado', mensaje: respuesta?.mensaje ?? 'Sin conexión con el servidor. Probá de nuevo.' })
    } finally {
      setCodigo('')
      setTipo(null)
      setEnviando(false)
    }
  }

  if (tarjeta) return <div className="w-full max-w-md"><TarjetaMarca marca={tarjeta} cliente={apiTerminal} rutaFoto={`/terminal/foto/${tarjeta.id}/`} grande /></div>
  if (rechazo) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-3xl bg-red-700 px-16 py-10 text-center">
        <XCircle size={96} />
        <p className="text-4xl font-bold">No se registró</p>
        <p className="text-2xl">{rechazo}</p>
      </div>
    )
  }
  if (datos.pide_tipo && !tipo) {
    return (
      <div className="flex flex-col items-center gap-6">
        <p className="text-2xl">¿Entrada o salida?</p>
        <div className="flex gap-4">
          {(['entrada', 'salida'] as const).map((t) => (
            <button key={t} type="button" onClick={() => setTipo(t)}
              className={`rounded-2xl px-10 py-6 text-2xl font-bold ${t === 'entrada' ? 'bg-green-700 hover:bg-green-600' : 'bg-sky-700 hover:bg-sky-600'}`}>
              {t === 'entrada' ? 'Entrada' : 'Salida'}
            </button>
          ))}
        </div>
      </div>
    )
  }
  const tocar = (d: string) => { if (codigo.length < 12) setCodigo(codigo + d) }
  return (
    <div className="flex flex-col items-center gap-4">
      <p className="text-2xl">Ingresá tu código{tipo ? ` (${tipo})` : ''}</p>
      <p className="h-14 min-w-[16rem] rounded-xl bg-stone-800 px-6 text-center font-mono text-4xl leading-[3.5rem] tracking-[0.4em]">
        {'•'.repeat(codigo.length) || <span className="text-stone-600">{'·'.repeat(datos.largo_codigo)}</span>}
      </p>
      <div className="grid grid-cols-3 gap-3">
        {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => (
          <button key={d} type="button" onClick={() => tocar(d)} className="h-20 w-20 rounded-2xl bg-stone-700 text-3xl font-bold hover:bg-stone-600">{d}</button>
        ))}
        <button type="button" onClick={() => setCodigo(codigo.slice(0, -1))} aria-label="Borrar"
          className="flex h-20 w-20 items-center justify-center rounded-2xl bg-stone-800 hover:bg-stone-700"><Delete size={32} /></button>
        <button type="button" onClick={() => tocar('0')} className="h-20 w-20 rounded-2xl bg-stone-700 text-3xl font-bold hover:bg-stone-600">0</button>
        <button type="button" onClick={enviar} disabled={enviando || codigo.length < 4}
          className="h-20 w-20 rounded-2xl bg-marca-700 text-xl font-bold hover:bg-marca-600 disabled:opacity-40">OK</button>
      </div>
    </div>
  )
}
