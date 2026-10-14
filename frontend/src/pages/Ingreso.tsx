import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import axios from 'axios'
import api from '../services/api'
import { useSesion } from '../services/sesionContexto'
import { mensajeDeError } from '../formato'
import { aplicarMarca, LOGO_KOAPE } from '../marca'
import type { DatosUsuario, Marca } from '../tipos'

interface Acceso { nombre: string; direccion_acceso: string; marca: Marca }

/** Pantalla de ingreso. En /ingresar es la estándar de Koape; en /<dirección> (ej. /delacosta) muestra el logo,
 * el nombre y los colores de esa empresa, y solo deja entrar a sus usuarios (lo controla el servidor). */
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
  if (buscando) return <div className="fondo-app flex items-center justify-center text-stone-500">Cargando…</div>

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

  return (
    <div className="fondo-app flex items-center justify-center px-4">
      <div className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-md ring-1 ring-stone-200">
        <div className="franja-marca" />
        <div className="p-8">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          {acceso ? (
            <>
              <img src={acceso.marca.logo || LOGO_KOAPE} alt={acceso.nombre} className="h-24 max-w-[16rem] object-contain" />
              <h1 className="text-2xl font-bold text-stone-900">{acceso.nombre}</h1>
              <p className="text-sm text-stone-500">Recursos humanos · ingresá con tu usuario</p>
            </>
          ) : (
            <>
              <img src={LOGO_KOAPE} alt="Koape" className="h-24 w-24" />
              <h1 className="text-2xl font-bold text-stone-900">Iniciar sesión</h1>
              <p className="text-sm text-stone-500">Koape RR. HH. · legajos, asistencia y nómina</p>
            </>
          )}
          {inexistente && (
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">No encontramos la dirección «{direccion}»: este es el ingreso general.</p>
          )}
        </div>

        <form onSubmit={enviar} className="space-y-5">
          <div>
            <label htmlFor="usuario" className="mb-1 block text-sm font-medium">Usuario</label>
            <input id="usuario" autoComplete="username" autoCapitalize="none" value={nombre}
              onChange={(e) => setNombre(e.target.value)} required
              className="w-full rounded-lg border border-stone-300 p-2 focus:outline-none focus:ring-2 focus:ring-marca-600" />
          </div>
          <div>
            <label htmlFor="clave" className="mb-1 block text-sm font-medium">Contraseña</label>
            <input id="clave" type="password" autoComplete="current-password" value={clave}
              onChange={(e) => setClave(e.target.value)} required
              className="w-full rounded-lg border border-stone-300 p-2 focus:outline-none focus:ring-2 focus:ring-marca-600" />
          </div>

          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}

          <button type="submit" disabled={enviando}
            className="w-full rounded-lg bg-marca-700 px-6 py-2.5 font-medium text-white transition hover:bg-marca-600 disabled:opacity-60">
            {enviando ? 'Ingresando…' : 'Entrar'}
          </button>
        </form>
        {acceso && <p className="mt-6 text-center text-xs text-stone-400">Con la tecnología de Koape RR. HH.</p>}
        </div>
      </div>
    </div>
  )
}
