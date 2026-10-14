import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, ChevronLeft, PenLine, Timer } from 'lucide-react'
import api from '../services/api'
import { COLOR_ESTADO } from '../components/TablaDias'
import { fechaHoraLegible, fechaLegible, horasMinutos } from '../formato'
import { tieneAlcanceGeneral, tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Registro } from '../tipos'

interface MarcaDelDia { id: number; fecha_hora: string; tipo_texto: string; metodo_texto: string; anulada: boolean; motivo_anulacion: string; terminal: string }
interface IncidenciaDelDia { id: number; tipo_texto: string; descripcion: string; estado_texto: string }

/** Un día de asistencia: los números, cómo se calcularon, las marcas (las
 * anuladas tachadas) e incidencias, y los accesos para corregir. */
export default function DiaAsistencia() {
  const { id } = useParams()
  const { usuario } = useSesion()
  const navegar = useNavigate()
  const [dia, setDia] = useState<Registro | null>(null)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    api.get<Registro>(`/dias-asistencia/${id}/`).then((r) => setDia(r.data)).catch(() => setDia(null))
  }, [id, version])

  if (!dia) return <p className="rounded-xl bg-white p-6">Cargando… <Link to="/asistencia/dias" className="underline">Volver</Link></p>
  const marcas = (dia.marcas ?? []) as MarcaDelDia[]
  const incidencias = (dia.incidencias ?? []) as IncidenciaDelDia[]
  const general = tieneAlcanceGeneral(usuario)
  const volver = general ? '/asistencia/dias' : '/mi-asistencia'
  const aquí = `/asistencia/dias/${id}`
  const empleadoParam = `empleado=${dia.empleado}&empleado_texto=${encodeURIComponent(String(dia.empleado_texto))}&volver=${encodeURIComponent(aquí)}`

  const revisar = async () => {
    await api.post(`/dias-asistencia/${id}/revisar/`)
    setVersion((v) => v + 1)
  }

  const numeros: [string, unknown, string?][] = [
    ['Programado', dia.minutos_programados], ['Trabajado', dia.minutos_trabajados, 'text-stone-900'],
    ['Descanso', dia.minutos_descanso], ['Tardanza', dia.minutos_tardanza, 'text-red-700'],
    ['Salida anticipada', dia.minutos_salida_anticipada, 'text-red-700'], ['Ordinario', dia.minutos_ordinarios],
    ['Extra candidato', dia.minutos_extra_candidatos], ['Extra autorizado', dia.minutos_extra_autorizados, 'text-green-700'],
    ['Nocturno', dia.minutos_nocturnos], ['En feriado', dia.minutos_feriado],
  ]

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Link to={volver} aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
          <h1 className="text-xl font-bold text-stone-900 sm:text-2xl">{String(dia.empleado_texto)} · {fechaLegible(String(dia.fecha))}</h1>
          <span className={`rounded-full px-2.5 py-0.5 text-sm font-medium ${COLOR_ESTADO[String(dia.estado)] ?? ''}`}>{String(dia.estado_texto)}</span>
        </div>
        <p className="mb-4 text-sm text-stone-600">
          {dia.horario_resumen ? `Horario: ${String(dia.horario_texto)} (${String(dia.horario_resumen)})` : 'Sin horario asignado'}
          {dia.feriado ? ` · Feriado: ${String(dia.feriado)}` : ''} · cálculo n.º {String(dia.version_calculo)} del {fechaHoraLegible(String(dia.calculado_en))}
          {dia.revisado_en ? ` · revisado el ${fechaHoraLegible(String(dia.revisado_en))}` : ''}
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {numeros.map(([texto, valor, color]) => (
            <div key={texto} className="rounded-xl border border-stone-200 p-2">
              <p className={`text-xl font-bold tabular-nums ${Number(valor) ? color ?? 'text-stone-800' : 'text-stone-300'}`}>{horasMinutos(valor)}</p>
              <p className="text-xs text-stone-500">{texto}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {tienePermiso(usuario, 'asistencia.add_ajustemarcacion') && (
            <button type="button" onClick={() => navegar(`/m/ajustes-marcacion/nuevo?${empleadoParam}`)}
              className="flex items-center gap-1 rounded-lg border border-marca-700 px-3 py-2 text-sm font-medium text-marca-800 hover:bg-marca-50">
              <PenLine size={16} /> {general ? 'Agregar o anular una marca' : 'Pedir corrección de marca'}
            </button>
          )}
          {general && Number(dia.minutos_extra_candidatos) > Number(dia.minutos_extra_autorizados) && tienePermiso(usuario, 'asistencia.add_autorizacionhorasextra') && (
            <button type="button"
              onClick={() => navegar(`/m/autorizaciones-extra/nuevo?${empleadoParam}&fecha=${String(dia.fecha)}&minutos_solicitados=${Number(dia.minutos_extra_candidatos) - Number(dia.minutos_extra_autorizados)}`)}
              className="flex items-center gap-1 rounded-lg border border-marca-700 px-3 py-2 text-sm font-medium text-marca-800 hover:bg-marca-50">
              <Timer size={16} /> Autorizar horas extra
            </button>
          )}
          {!dia.revisado_en && tienePermiso(usuario, 'asistencia.revisar_asistencia') && (
            <button type="button" onClick={revisar}
              className="flex items-center gap-1 rounded-lg bg-marca-700 px-3 py-2 text-sm font-medium text-white hover:bg-marca-600">
              <CheckCircle2 size={16} /> Marcar como revisado
            </button>
          )}
        </div>
      </div>

      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <h2 className="mb-2 font-semibold text-stone-800">Cómo se calculó</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-stone-700">
          {((dia.explicacion ?? []) as string[]).map((linea, i) => <li key={i}>{linea}</li>)}
        </ul>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
          <h2 className="mb-2 font-semibold text-stone-800">Marcas</h2>
          {marcas.length === 0 ? <p className="text-sm text-stone-500">Sin marcas.</p> : (
            <ul className="space-y-1 text-sm">
              {marcas.map((m) => (
                <li key={m.id} className={m.anulada ? 'text-stone-400 line-through' : ''} title={m.anulada ? m.motivo_anulacion : ''}>
                  <span className="font-mono tabular-nums">{fechaHoraLegible(m.fecha_hora).slice(11)}</span> · {m.tipo_texto} · {m.metodo_texto}
                  {m.terminal && <span className="text-stone-500"> · {m.terminal}</span>}
                  {m.anulada && <span className="ml-1 no-underline">(anulada)</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
          <h2 className="mb-2 font-semibold text-stone-800">Incidencias</h2>
          {incidencias.length === 0 ? <p className="text-sm text-stone-500">Sin incidencias.</p> : (
            <ul className="space-y-1 text-sm">
              {incidencias.map((i) => (
                <li key={i.id}>
                  {general ? <Link to={`/m/incidencias/${i.id}?volver=${encodeURIComponent(aquí)}`} className="text-marca-800 underline">{i.tipo_texto}</Link> : i.tipo_texto}
                  : {i.descripcion} <span className="text-stone-500">({i.estado_texto})</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
