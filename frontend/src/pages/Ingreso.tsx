import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { useSesion } from '../services/sesionContexto'
import { mensajeDeError } from '../formato'
import { LOGO_KOAPE } from '../marca'

export default function Ingreso() {
  const { usuario, ingresar } = useSesion()
  const navegar = useNavigate()
  const desde = (useLocation().state as { desde?: string } | null)?.desde ?? '/'
  const [nombre, setNombre] = useState('')
  const [clave, setClave] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  if (usuario) return <Navigate to={desde} replace />

  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      await ingresar(nombre.trim(), clave)
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
        <div className="mb-6 flex flex-col items-center gap-3">
          <img src={LOGO_KOAPE} alt="Koape" className="h-24 w-24" />
          <h1 className="text-2xl font-bold text-stone-900">Iniciar sesión</h1>
          <p className="text-sm text-stone-500">Koape RR. HH. · legajos, asistencia y nómina</p>
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
        </div>
      </div>
    </div>
  )
}
