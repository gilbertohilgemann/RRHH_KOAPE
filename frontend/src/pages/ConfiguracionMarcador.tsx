import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'
import { ChevronLeft, Save } from 'lucide-react'
import api from '../services/api'
import CampoFormulario from '../components/CampoFormulario'
import { mensajeDeError } from '../formato'
import { tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Campo } from '../tipos'

// Mismos nombres que asistencia.models.ConfiguracionMarcacion.
const CAMPOS: Campo[] = [
  { nombre: 'permite_qr', etiqueta: 'QR dinámico en la pantalla de la terminal, escaneado con el celular (recomendado)', tipo: 'booleano', seccion: 'Modalidades habilitadas' },
  { nombre: 'permite_codigo_fijo', etiqueta: 'Código fijo del empleado en la terminal', tipo: 'booleano' },
  { nombre: 'permite_csv', etiqueta: 'Importación de archivo CSV (sin verificación presencial)', tipo: 'booleano' },
  { nombre: 'vigencia_qr_segundos', etiqueta: 'Cada cuántos segundos cambia el QR', tipo: 'entero', seccion: 'QR dinámico',
    ayuda: 'Entre 10 y 300. Más corto = más difícil reenviarlo a alguien que no está.' },
  { nombre: 'qr_un_solo_uso', etiqueta: 'El QR cambia apenas alguien lo usa (recomendado: una foto del QR no le sirve a otro)', tipo: 'booleano' },
  { nombre: 'modo_accion', etiqueta: 'Entrada o salida', tipo: 'opciones', requerido: true, seccion: 'Cómo se decide entrada o salida', opciones: [
    { valor: 'automatica', texto: 'Koape propone entrada o salida según la secuencia' },
    { valor: 'explicita', texto: 'La terminal pide elegir Entrada o Salida' },
  ] },
  { nombre: 'segundos_antirrebote', etiqueta: 'Segundos mínimos entre dos marcas', tipo: 'entero',
    ayuda: 'Una segunda marca del mismo empleado antes de este tiempo se rechaza como repetida.' },
  { nombre: 'horas_maximas_turno', etiqueta: 'Horas máximas de un turno', tipo: 'entero',
    ayuda: 'Una entrada sin salida más vieja que esto ya no se empareja con la siguiente marca.' },
  { nombre: 'largo_codigo', etiqueta: 'Largo del código fijo', tipo: 'entero', seccion: 'Código fijo', ayuda: 'Entre 4 y 12 dígitos (vale para los códigos nuevos).' },
  { nombre: 'empleado_ve_su_codigo', etiqueta: 'El empleado puede ver su código fijo en la aplicación', tipo: 'booleano' },
]

/** Configuración del marcador de la empresa (Administrador). */
export default function ConfiguracionMarcador() {
  const { usuario } = useSesion()
  const [valores, setValores] = useState<Record<string, unknown> | null>(null)
  const [errores, setErrores] = useState<Record<string, string>>({})
  const [mensaje, setMensaje] = useState<{ ok: boolean; texto: string } | null>(null)
  const [guardando, setGuardando] = useState(false)
  const editable = tienePermiso(usuario, 'asistencia.change_configuracionmarcacion')

  useEffect(() => {
    api.get('/marcador/configuracion/').then((r) => setValores(r.data))
      .catch((err) => setMensaje({ ok: false, texto: mensajeDeError(axios.isAxiosError(err) ? err.response?.data : null, 'No se pudo cargar la configuración.') }))
  }, [])

  const guardar = async (e: FormEvent) => {
    e.preventDefault()
    if (!valores) return
    setGuardando(true)
    setErrores({})
    setMensaje(null)
    try {
      const r = await api.patch('/marcador/configuracion/', Object.fromEntries(CAMPOS.map((c) => [c.nombre, valores[c.nombre]])))
      setValores(r.data)
      setMensaje({ ok: true, texto: 'Configuración guardada.' })
    } catch (err) {
      const datos = axios.isAxiosError(err) ? err.response?.data as Record<string, unknown> : {}
      setErrores(Object.fromEntries(Object.entries(datos ?? {}).filter(([, v]) => Array.isArray(v)).map(([k, v]) => [k, String((v as unknown[])[0])])))
      setMensaje({ ok: false, texto: mensajeDeError(datos, 'Revisá los campos marcados en rojo.') })
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <div className="mb-4 flex items-center gap-2">
        <Link to="/" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
        <h1 className="text-xl font-bold text-stone-900 sm:text-2xl">Configuración del marcador</h1>
      </div>
      {valores?.permite_codigo_fijo === true && (
        <p className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          ⚠ El código fijo es práctico, pero puede compartirse: identifica el código, no prueba quién lo presenta. Para una
          comprobación de presencia más fuerte, preferí el QR dinámico escaneado desde la sesión del empleado.
        </p>
      )}
      {valores === null ? <p className="text-stone-500">{mensaje?.texto ?? 'Cargando…'}</p> : (
        <form onSubmit={guardar}>
          <fieldset disabled={!editable} className="grid gap-4 sm:grid-cols-2">
            {CAMPOS.map((c) => (
              <div key={c.nombre} className="contents">
                {c.seccion && <h2 className="border-b border-marca-100 pb-1 pt-2 font-semibold text-stone-700 sm:col-span-2">{c.seccion}</h2>}
                <CampoFormulario campo={c} valores={valores} error={errores[c.nombre]} esNuevo={false}
                  onCambio={(cambios) => setValores((v) => ({ ...v, ...cambios }))} />
              </div>
            ))}
          </fieldset>
          {mensaje && <p className={`mt-4 rounded-lg px-3 py-2 text-sm ${mensaje.ok ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>{mensaje.texto}</p>}
          {editable && (
            <div className="mt-5 flex justify-end">
              <button type="submit" disabled={guardando}
                className="flex items-center gap-1 rounded-lg bg-marca-700 px-5 py-2 text-sm font-medium text-white hover:bg-marca-600 disabled:opacity-60">
                <Save size={16} /> {guardando ? 'Guardando…' : 'Guardar'}
              </button>
            </div>
          )}
        </form>
      )}
    </div>
  )
}
