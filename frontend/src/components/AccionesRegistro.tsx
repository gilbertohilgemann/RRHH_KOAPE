import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import api from '../services/api'
import CampoFecha from './CampoFecha'
import { descargarArchivo } from '../descargas'
import { hoyIso, mensajeDeError } from '../formato'
import { tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Accion, Modulo, Registro } from '../tipos'

/** Botones de las acciones propias de un registro (modulos.ts → `acciones`):
 * cambios de estado (con motivo o fecha si hacen falta), descargas y
 * "ver número completo". Cada uno solo aparece con su permiso; la API igual
 * lo vuelve a controlar. */
export default function AccionesRegistro({ modulo, registro, onCambio }: { modulo: Modulo; registro: Registro; onCambio: () => void }) {
  const { usuario } = useSesion()
  const navegar = useNavigate()
  const [abierta, setAbierta] = useState<Accion | null>(null)
  const [motivo, setMotivo] = useState('')
  const [fecha, setFecha] = useState(hoyIso())
  const [revelado, setRevelado] = useState<string | null>(null)
  const [resultado, setResultado] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const visibles = (modulo.acciones ?? []).filter((a) => tienePermiso(usuario, a.permiso) && (!a.visibleSi || a.visibleSi(registro)))
  if (visibles.length === 0) return null
  const ruta = (a: Accion) => `/${modulo.endpoint}/${registro.id}/${a.accion}/`

  const ejecutar = async (a: Accion, datos: Record<string, string> = {}) => {
    setError(null)
    setEnviando(true)
    try {
      if (a.tipo === 'descarga') {
        await descargarArchivo(ruta(a), String(registro.nombre_original ?? 'documento'))
      } else if (a.tipo === 'revelar') {
        if (a.confirmar && !window.confirm(a.confirmar)) return
        const r = await api.post<{ numero?: string; clave?: string }>(ruta(a))
        setRevelado(r.data.numero ?? r.data.clave ?? '')
      } else if (a.tipo === 'resultado') {
        const r = await api.post<{ texto?: string }>(ruta(a), datos)
        setResultado(r.data.texto ?? '')
        setAbierta(null)
      } else {
        const r = await api.post<Registro>(ruta(a), datos)
        setAbierta(null)
        setMotivo('')
        if (a.irA) navegar(a.irA(r.data))
        else onCambio()
      }
    } catch (err) {
      const respuesta = axios.isAxiosError(err) ? err.response?.data as Record<string, unknown> | undefined : undefined
      const porCampo = respuesta && Object.values(respuesta).find((v) => Array.isArray(v))
      setError(Array.isArray(porCampo) ? String(porCampo[0]) : mensajeDeError(respuesta, 'No se pudo completar la acción.'))
    } finally {
      setEnviando(false)
    }
  }

  const tocar = (a: Accion) => {
    setError(null)
    if (a.pideMotivo || a.pideFecha) { setAbierta(a); return }
    if (a.tipo !== 'revelar' && a.confirmar && !window.confirm(a.confirmar)) return
    ejecutar(a)
  }

  const confirmarFormulario = (e: FormEvent) => {
    e.preventDefault()
    if (!abierta) return
    const datos: Record<string, string> = {}
    if (abierta.pideMotivo) datos.motivo = motivo
    if (abierta.pideFecha) datos[abierta.pideFecha.campo] = fecha
    ejecutar(abierta, datos)
  }

  const clase = (a: Accion) => a.peligrosa
    ? 'border border-red-300 text-red-700 hover:bg-red-50'
    : 'bg-marca-700 text-white hover:bg-marca-600'

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      {!abierta ? (
        <div className="flex flex-wrap gap-2">
          {visibles.map((a) => (
            <button key={`${a.accion}-${a.etiqueta}`} type="button" disabled={enviando} onClick={() => tocar(a)}
              className={`rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-60 ${clase(a)}`}>
              {a.etiqueta}
            </button>
          ))}
        </div>
      ) : (
        <form onSubmit={confirmarFormulario} className="space-y-3">
          <h2 className="font-semibold text-stone-800">{abierta.etiqueta}</h2>
          {abierta.pideFecha && (
            <label className="block text-sm font-medium text-stone-800">{abierta.pideFecha.etiqueta}
              <CampoFecha valor={fecha} onCambio={setFecha} className="mt-1 w-48" />
            </label>
          )}
          {abierta.pideMotivo && (
            <label className="block text-sm font-medium text-stone-800">{abierta.etiquetaMotivo ?? 'Motivo'}
              <input value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={250} required
                className="mt-1 w-full rounded-lg border border-stone-300 p-2 focus:outline-none focus:ring-2 focus:ring-marca-600" />
            </label>
          )}
          <div className="flex gap-2">
            <button type="submit" disabled={enviando || (abierta.pideMotivo && !motivo.trim())}
              className={`rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-60 ${abierta.peligrosa ? 'bg-red-700 text-white hover:bg-red-600' : 'bg-marca-700 text-white hover:bg-marca-600'}`}>
              {enviando ? 'Guardando…' : 'Confirmar'}
            </button>
            <button type="button" onClick={() => setAbierta(null)} className="rounded-lg border border-stone-300 px-4 py-2 text-sm">Cancelar</button>
          </div>
        </form>
      )}
      {revelado && (
        <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <p className="break-all font-mono text-base">{revelado}</p>
          <p className="mt-1 text-xs text-amber-700">Quedó registrado en la auditoría. No lo compartas por medios inseguros.</p>
          <button type="button" onClick={() => navigator.clipboard?.writeText(revelado).catch(() => undefined)}
            className="mt-1 text-xs underline">Copiar</button>
        </div>
      )}
      {resultado !== null && (
        <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-stone-50 px-3 py-2 font-mono text-sm text-stone-800 ring-1 ring-stone-200">{resultado}</pre>
      )}
      {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
    </div>
  )
}
