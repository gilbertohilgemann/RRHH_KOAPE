import { fechaHoraLegible } from '../formato'
import type { Registro } from '../tipos'

function mostrar(valor: unknown): string {
  if (valor === null || valor === undefined || valor === '') return '—'
  if (typeof valor === 'boolean') return valor ? 'Sí' : 'No'
  if (Array.isArray(valor)) return valor.join(', ') || '—'
  if (typeof valor === 'object') return JSON.stringify(valor)
  return String(valor)
}

/** Un evento de la auditoría: quién, cuándo, qué, y la tabla de campos con
 * su valor anterior y el nuevo. */
export default function DetalleAuditoria({ evento }: { evento: Registro }) {
  const antes = (evento.datos_anteriores ?? {}) as Record<string, unknown>
  const despues = (evento.datos_nuevos ?? {}) as Record<string, unknown>
  const campos = Array.from(new Set([...Object.keys(antes), ...Object.keys(despues)])).sort()

  return (
    <div className="space-y-4 text-sm">
      <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-[10rem_1fr]">
        <dt className="text-stone-500">Fecha y hora</dt><dd>{fechaHoraLegible(String(evento.fecha))}</dd>
        <dt className="text-stone-500">Usuario</dt><dd>{mostrar(evento.nombre_usuario) === '—' ? 'Sistema o anónimo' : String(evento.nombre_usuario)}</dd>
        <dt className="text-stone-500">Acción</dt><dd>{String(evento.accion_texto ?? evento.accion)}</dd>
        <dt className="text-stone-500">Registro</dt><dd>{mostrar(evento.objeto_texto)} <span className="text-stone-400">({mostrar(evento.modelo)} #{mostrar(evento.objeto_id)})</span></dd>
        {Boolean(evento.descripcion) && <><dt className="text-stone-500">Descripción</dt><dd>{String(evento.descripcion)}</dd></>}
        <dt className="text-stone-500">Dirección IP</dt><dd>{mostrar(evento.ip)}</dd>
      </dl>
      {campos.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-stone-200">
          <table className="w-full text-sm">
            <thead className="bg-marca-50 text-left text-stone-700">
              <tr><th className="px-3 py-2">Campo</th><th className="px-3 py-2">Valor anterior</th><th className="px-3 py-2">Valor nuevo</th></tr>
            </thead>
            <tbody>
              {campos.map((c) => (
                <tr key={c} className="border-t border-stone-100 align-top">
                  <td className="px-3 py-1.5 font-medium">{c}</td>
                  <td className="px-3 py-1.5 text-red-800">{mostrar(antes[c])}</td>
                  <td className="px-3 py-1.5 text-marca-800">{mostrar(despues[c])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
