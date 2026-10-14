import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import axios from 'axios'
import { CalendarCheck, Lock, ShieldCheck, User, Wallet } from 'lucide-react'
import api from '../services/api'
import { useSesion } from '../services/sesionContexto'
import { mensajeDeError } from '../formato'
import { aplicarMarca, LOGO_KOAPE } from '../marca'
import type { DatosUsuario, Marca } from '../tipos'

interface Acceso { nombre: string; direccion_acceso: string; marca: Marca }

const VENTAJAS = [
  { icono: CalendarCheck, texto: 'Asistencia con QR, licencias y vacaciones' },
  { icono: Wallet, texto: 'Nómina explicada, recibos, aguinaldo y planillas IPS / MTESS' },
  { icono: ShieldCheck, texto: 'Cada empresa ve solo sus datos' },
]

/** Pantalla de ingreso. En /ingresar es la estándar de Koape; en /<dirección> (ej. /delacosta) muestra el logo,
 * el nombre y los colores de esa empresa, y solo deja entrar a sus usuarios (lo controla el servidor).
 * A la izquierda, la identidad de Koape; a la derecha, el formulario. Entre los dos, una curva. */
export default function Ingreso() {
  const { usuario, ingresar } = useSesion()
  const navegar = useNavigate()
  const { direccion } = useParams()
  const desde = (useLocation().state as { desde?: string } | null)?.desde ?? '/'
  const [acceso, setAcceso] = useState<Acceso | null>(null)
  const [buscando, setBuscando] = useState(Boolean(direccion))
  const [inexistente, setInexistente] = useState(false)
  const [nombre, setNombre] = useState('')
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    if (!direccion) { setAcceso(null); setInexistente(false); return }
    setBuscando(true)
    api.get<Acceso>(`/acceso/${encodeURIComponent(direccion.toLowerCase())}/`)
      .then((r) => { setAcceso(r.data); setInexistente(false); aplicarMarca({ marca: r.data.marca } as DatosUsuario) })
      .catch(() => { setAcceso(null); setInexistente(true); aplicarMarca(null) })
      .finally(() => setBuscando(false))
  }, [direccion])

  if (usuario) return <Navigate to={desde} replace />
  if (buscando) return <div className="flex min-h-screen items-center justify-center bg-stone-50 text-stone-500">Cargando…</div>

  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      await ingresar(nombre.trim(), clave, acceso?.direccion_acceso)
      navegar(desde, { replace: true })
    } catch (err) {
      if (axios.isAxiosError(err) && err.response) {
        setError(err.response.status === 429
          ? 'Demasiados intentos. Esperá un minuto y probá de nuevo.'
          : mensajeDeError(err.response.data, 'Usuario o contraseña incorrectos.'))
      } else {
        setError('No se pudo conectar con el servidor.')
      }
    } finally {
      setEnviando(false)
    }
  }

  const campo = 'w-full rounded-lg border border-stone-300 bg-white py-2.5 pl-10 pr-3 text-stone-900 shadow-sm transition ' +
    'placeholder:text-stone-400 focus:border-marca-600 focus:outline-none focus:ring-2 focus:ring-marca-600/30'

  return (
    <div className="relative flex min-h-screen flex-col bg-stone-50 lg:flex-row">
      {/* Identidad de Koape */}
      <aside className="relative z-10 flex flex-col justify-between bg-[#232323] px-8 py-8 text-white lg:w-1/2 lg:px-14 lg:py-12">
        <div className="flex items-center gap-3">
          <img src={LOGO_KOAPE} alt="" className="h-14 w-14 lg:h-20 lg:w-20" />
          <p className="text-lg font-extrabold uppercase leading-[1.05] tracking-tight lg:text-2xl">Koape<br />Sistemas<br />EAS</p>
        </div>
        <div className="hidden max-w-md lg:block">
          <h2 className="text-4xl font-bold tracking-tight">Koape RR. HH.</h2>
          <p className="mt-4 text-lg leading-relaxed text-stone-300">
            Recursos humanos y nómina para Paraguay: legajos, asistencia, licencias y sueldos, en un solo lugar.
          </p>
          <ul className="mt-6 space-y-3 text-sm text-stone-200">
            {VENTAJAS.map(({ icono: Icono, texto }) => (
              <li key={texto} className="flex items-center gap-3"><Icono size={18} className="shrink-0 text-amber-300" />{texto}</li>
            ))}
          </ul>
        </div>
        <p className="hidden text-xs text-stone-400 lg:block">© Koape Sistemas EAS</p>
        {/* La curva: el panel oscuro avanza sobre el claro y vuelve (solo en pantallas anchas). */}
        <svg aria-hidden="true" viewBox="0 0 100 100" preserveAspectRatio="none"
          className="pointer-events-none absolute left-full top-0 hidden h-full w-28 lg:block xl:w-40">
          <path d="M0,0 C55,12 100,40 82,68 C70,88 30,97 0,100 Z" fill="#232323" />
        </svg>
      </aside>

      {/* Formulario */}
      <main className="flex flex-1 items-center justify-center px-6 py-10 lg:px-16">
        <div className="w-full max-w-sm lg:ml-16">
          <div className="mb-8 flex flex-col items-center gap-2 text-center">
            <img src={acceso?.marca.logo || LOGO_KOAPE} alt={acceso?.nombre ?? 'Koape'}
              className="h-20 max-w-[14rem] object-contain" />
            <p className="text-sm font-medium text-stone-600">{acceso?.nombre ?? 'Koape RR. HH.'}</p>
          </div>
          <h1 className="text-2xl font-bold text-stone-900">Ingresar</h1>
          <p className="mb-6 text-sm text-stone-500">
            {acceso ? `Usá tu usuario de ${acceso.nombre}.` : 'Usá el usuario que te dio tu empresa.'}
          </p>
          {inexistente && (
            <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">No encontramos la dirección «{direccion}»: este es el ingreso general.</p>
          )}

          <form onSubmit={enviar} className="space-y-5">
            <div>
              <label htmlFor="usuario" className="mb-1 block text-sm font-medium text-stone-800">Usuario</label>
              <div className="relative">
                <User size={18} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
                <input id="usuario" autoComplete="username" autoCapitalize="none" value={nombre}
                  onChange={(e) => setNombre(e.target.value)} required className={campo} />
              </div>
            </div>
            <div>
              <label htmlFor="clave" className="mb-1 block text-sm font-medium text-stone-800">Contraseña</label>
              <div className="relative">
                <Lock size={18} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
                <input id="clave" type="password" autoComplete="current-password" value={clave}
                  onChange={(e) => setClave(e.target.value)} required className={campo} />
              </div>
            </div>

            {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}

            <button type="submit" disabled={enviando}
              className="w-full rounded-lg bg-marca-700 px-6 py-3 font-semibold text-white shadow-sm transition hover:bg-marca-600 disabled:opacity-60">
              {enviando ? 'Ingresando…' : 'Ingresar'}
            </button>
          </form>
          <p className="mt-8 text-center text-xs text-stone-400 lg:hidden">© Koape Sistemas EAS</p>
        </div>
      </main>

      {/* Franja con el degradado de la marca, al pie */}
      <div className="franja-marca absolute inset-x-0 bottom-0 z-20" />
    </div>
  )
}
