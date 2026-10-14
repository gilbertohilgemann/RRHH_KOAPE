import { useEffect, useState, type FormEvent } from 'react'
import axios from 'axios'
import { History, RotateCcw, UserMinus } from 'lucide-react'
import api from '../services/api'
import CampoFecha from './CampoFecha'
import { fechaLegible, hoyIso, mensajeDeError } from '../formato'
import { tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Registro } from '../tipos'

/** Debajo del legajo: baja lógica o reactivación (cada una con su permiso)
 * y el historial de asignaciones del empleado. */
export default function AccionesEmpleado({ empleado, onCambio }: { empleado: Registro; onCambio: () => void }) {
  const { usuario } = useSesion()
  const [historial, setHistorial] = useState<Registro[] | null>(null)
  const [abierto, setAbierto] = useState(false)
  const [fecha, setFecha] = useState(hoyIso())
  const [motivo, setMotivo] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const deBaja = empleado.estado === 'baja'
  const puedeAccion = deBaja ? tienePermiso(usuario, 'empleados.reactivar_empleado') : tienePermiso(usuario, 'empleados.dar_baja_empleado')

  useEffect(() => {
    if (!tienePermiso(usuario, 'empleados.view_historialasignacion')) return
    api.get<Registro[]>(`/empleados/${empleado.id}/historial/`).then((r) => setHistorial(r.data)).catch(() => setHistorial(null))
  }, [empleado.id, empleado.estado, empleado.modificado, usuario])

  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      if (deBaja) await api.post(`/empleados/${empleado.id}/reactivar/`, { motivo })
      else await api.post(`/empleados/${empleado.id}/dar_baja/`, { fecha_egreso: fecha, motivo })
      setAbierto(false)
      setMotivo('')
      onCambio()
    } catch (err) {
      const datos = axios.isAxiosError(err) ? err.response?.data as Record<string, unknown> | undefined : undefined
      const porCampo = datos && (datos.fecha_egreso ?? datos.motivo)
      setError(Array.isArray(porCampo) ? String(porCampo[0]) : mensajeDeError(datos, 'No se pudo completar.'))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <>
      {puedeAccion && (
        <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
          {!abierto ? (
            <button type="button" onClick={() => setAbierto(true)}
              className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium ${deBaja
                ? 'border border-marca-700 text-marca-800 hover:bg-marca-50' : 'border border-red-300 text-red-700 hover:bg-red-50'}`}>
              {deBaja ? <><RotateCcw size={16} /> Reactivar empleado</> : <><UserMinus size={16} /> Dar de baja</>}
            </button>
          ) : (
            <form onSubmit={enviar} className="space-y-3">
              <h2 className="font-semibold text-stone-800">{deBaja ? 'Reactivar empleado' : 'Dar de baja (baja lógica)'}</h2>
              <p className="text-sm text-stone-600">
                {deBaja
                  ? 'El empleado vuelve a estar activo. La baja anterior queda registrada en la auditoría.'
                  : 'El legajo no se borra: conserva sus datos, historial y documentos. Se puede reactivar.'}
              </p>
              {!deBaja && (
                <label className="block text-sm font-medium text-stone-800">Fecha de egreso
                  <CampoFecha valor={fecha} onCambio={setFecha} className="mt-1 w-48" />
                </label>
              )}
              <label className="block text-sm font-medium text-stone-800">Motivo
                <input value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={250} required
                  className="mt-1 w-full rounded-lg border border-stone-300 p-2 focus:outline-none focus:ring-2 focus:ring-marca-600" />
              </label>
              {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
              <div className="flex gap-2">
                <button type="submit" disabled={enviando || !motivo.trim()}
                  className={`rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-60 ${deBaja ? 'bg-marca-700 hover:bg-marca-600' : 'bg-red-700 hover:bg-red-600'}`}>
                  {enviando ? 'Guardando…' : deBaja ? 'Confirmar reactivación' : 'Confirmar baja'}
                </button>
                <button type="button" onClick={() => setAbierto(false)} className="rounded-lg border border-stone-300 px-4 py-2 text-sm">Cancelar</button>
              </div>
            </form>
          )}
        </div>
      )}

      {historial && historial.length > 0 && (
        <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
          <h2 className="mb-3 flex items-center gap-2 font-semibold text-stone-800"><History size={18} /> Historial de asignaciones</h2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-max text-sm">
              <thead className="text-left text-stone-500">
                <tr><th className="py-1 pr-3">Desde</th><th className="pr-3">Hasta</th><th className="pr-3">Sucursal</th>
                  <th className="pr-3">Departamento</th><th className="pr-3">Puesto</th><th className="pr-3">Supervisor</th><th>Motivo</th></tr>
              </thead>
              <tbody>
                {historial.map((h) => (
                  <tr key={h.id} className="border-t border-stone-100">
                    <td className="py-1 pr-3">{fechaLegible(String(h.vigente_desde))}</td>
                    <td className="pr-3">{h.vigente_hasta ? fechaLegible(String(h.vigente_hasta)) : 'vigente'}</td>
                    <td className="pr-3">{String(h.sucursal_texto || '—')}</td>
                    <td className="pr-3">{String(h.departamento_texto || '—')}</td>
                    <td className="pr-3">{String(h.puesto_texto || '—')}</td>
                    <td className="pr-3">{String(h.supervisor_texto || '—')}</td>
                    <td>{String(h.motivo || '')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}
