import { useNavigate } from 'react-router-dom'
import { CheckCircle2 } from 'lucide-react'
import { fechaHoraLegible, fechaLegible, horasMinutos } from '../formato'
import type { Registro } from '../tipos'

export const COLOR_ESTADO: Record<string, string> = {
  presente: 'bg-green-100 text-green-800',
  incompleto: 'bg-amber-100 text-amber-900',
  ausente: 'bg-red-100 text-red-800',
  franco: 'bg-stone-100 text-stone-600',
  feriado: 'bg-sky-100 text-sky-800',
  sin_horario: 'bg-stone-100 text-stone-500',
  licencia: 'bg-violet-100 text-violet-800',
}

const soloHora = (valor: unknown) => (valor ? fechaHoraLegible(String(valor)).slice(11) : '—')

/** Tabla de días de asistencia (la usan "Asistencia diaria" y "Mi asistencia"). */
export default function TablaDias({ dias, conEmpleado = true }: { dias: Registro[]; conEmpleado?: boolean }) {
  const navegar = useNavigate()
  return (
    <div className="overflow-x-auto rounded-lg border border-stone-200">
      <table className="w-full min-w-max text-sm">
        <thead className="bg-marca-50 text-left text-stone-700">
          <tr>
            <th className="px-2 py-1.5">Fecha</th>
            {conEmpleado && <th className="px-2 py-1.5">Empleado</th>}
            <th className="px-2 py-1.5">Entrada</th><th className="px-2 py-1.5">Salida</th>
            <th className="px-2 py-1.5 text-right">Program.</th><th className="px-2 py-1.5 text-right">Trabajado</th>
            <th className="px-2 py-1.5 text-right">Tarde</th><th className="px-2 py-1.5 text-right">Salió antes</th>
            <th className="px-2 py-1.5 text-right">Extra cand./aut.</th><th className="px-2 py-1.5 text-right">Noct.</th>
            <th className="px-2 py-1.5">Estado</th><th className="px-2 py-1.5" title="Revisado">Rev.</th>
          </tr>
        </thead>
        <tbody>
          {dias.map((d) => (
            <tr key={d.id} onClick={() => navegar(`/asistencia/dias/${d.id}`)} className="cursor-pointer border-t border-stone-100 hover:bg-marca-50/60">
              <td className="px-2 py-1.5 whitespace-nowrap">{fechaLegible(String(d.fecha))}</td>
              {conEmpleado && <td className="px-2 py-1.5">{String(d.empleado_texto)}</td>}
              <td className="px-2 py-1.5">{soloHora(d.primera_entrada)}</td>
              <td className="px-2 py-1.5">{soloHora(d.ultima_salida)}</td>
              <td className="px-2 py-1.5 text-right tabular-nums">{horasMinutos(d.minutos_programados)}</td>
              <td className="px-2 py-1.5 text-right font-medium tabular-nums">{horasMinutos(d.minutos_trabajados)}</td>
              <td className={`px-2 py-1.5 text-right tabular-nums ${Number(d.minutos_tardanza) ? 'text-red-700' : ''}`}>{horasMinutos(d.minutos_tardanza)}</td>
              <td className={`px-2 py-1.5 text-right tabular-nums ${Number(d.minutos_salida_anticipada) ? 'text-red-700' : ''}`}>{horasMinutos(d.minutos_salida_anticipada)}</td>
              <td className="px-2 py-1.5 text-right tabular-nums">
                {Number(d.minutos_extra_candidatos) ? `${horasMinutos(d.minutos_extra_candidatos)} / ${horasMinutos(d.minutos_extra_autorizados)}` : '—'}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums">{horasMinutos(d.minutos_nocturnos)}</td>
              <td className="px-2 py-1.5">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${COLOR_ESTADO[String(d.estado)] ?? ''}`}>{String(d.estado_texto)}</span>
                {Boolean(d.feriado) && <span className="ml-1 text-xs text-sky-700">{String(d.feriado)}</span>}
              </td>
              <td className="px-2 py-1.5">{d.revisado_en ? <CheckCircle2 size={16} className="text-green-700" /> : ''}</td>
            </tr>
          ))}
          {dias.length === 0 && <tr><td colSpan={conEmpleado ? 12 : 11} className="px-2 py-6 text-center text-stone-500">Sin días calculados en ese período.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
