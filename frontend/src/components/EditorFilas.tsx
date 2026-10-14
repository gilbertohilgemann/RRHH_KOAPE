import { Copy, Plus, Trash2 } from 'lucide-react'
import CampoFecha from './CampoFecha'
import type { Campo } from '../tipos'

type Fila = Record<string, unknown>

const claseCelda = 'w-full rounded-md border border-stone-300 bg-white p-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-marca-600'

function valorInicial(c: Campo): unknown {
  if (c.porDefecto !== undefined) return c.porDefecto
  if (c.tipo === 'decimal' || c.tipo === 'fecha') return null
  return c.tipo === 'booleano' ? false : c.tipo === 'entero' ? 0 : ''
}

/** Celda editable de una fila según el tipo de su subcampo. */
function Celda({ campo, valor, onCambio }: { campo: Campo; valor: unknown; onCambio: (v: unknown) => void }) {
  const texto = valor === null || valor === undefined ? '' : String(valor)
  switch (campo.tipo) {
    case 'hora':
      return <input type="time" value={texto.slice(0, 5)} onChange={(e) => onCambio(e.target.value)} className={claseCelda} aria-label={campo.etiqueta} />
    case 'fecha':
      // Vacía = sin fecha (null): la API no acepta un texto vacío como fecha.
      return <CampoFecha valor={texto} onCambio={(v) => onCambio(v || null)} aria-label={campo.etiqueta} />
    case 'decimal':
      return <input type="number" step="any" value={texto} onChange={(e) => onCambio(e.target.value === '' ? null : e.target.value)}
        className={claseCelda} aria-label={campo.etiqueta} />
    case 'entero':
      return <input type="number" min="0" step="1" value={texto} onChange={(e) => onCambio(e.target.value === '' ? 0 : Number(e.target.value))}
        className={claseCelda} aria-label={campo.etiqueta} />
    case 'booleano':
      return <input type="checkbox" checked={valor === true} onChange={(e) => onCambio(e.target.checked)} className="h-4 w-4 accent-marca-700" aria-label={campo.etiqueta} />
    case 'opciones':
      return (
        <select value={texto} onChange={(e) => onCambio(/^\d+$/.test(e.target.value) ? Number(e.target.value) : e.target.value)}
          className={claseCelda} aria-label={campo.etiqueta}>
          {campo.opciones?.map((o) => <option key={o.valor} value={o.valor}>{o.texto}</option>)}
        </select>
      )
    default:
      return <input type="text" value={texto} maxLength={campo.maxLength} onChange={(e) => onCambio(e.target.value)} className={claseCelda} aria-label={campo.etiqueta} />
  }
}

/** Tabla para editar filas hijas que se guardan junto con el registro
 * (tramos de un horario, días de un calendario). Los errores por fila que
 * devuelve la API se muestran debajo. */
export default function EditorFilas({ campo, valor, error, deshabilitado, onCambio }: {
  campo: Campo; valor: unknown; error?: string; deshabilitado?: boolean; onCambio: (filas: Fila[]) => void
}) {
  const subcampos = campo.subcampos ?? []
  const filas: Fila[] = Array.isArray(valor) ? (valor as Fila[]) : []
  const cambiarFila = (i: number, nombre: string, v: unknown) => onCambio(filas.map((f, j) => (j === i ? { ...f, [nombre]: v } : f)))
  const agregar = () => {
    const ultima = filas[filas.length - 1]
    onCambio([...filas, ultima ? { ...ultima, id: undefined } : Object.fromEntries(subcampos.map((c) => [c.nombre, valorInicial(c)]))])
  }
  const copiarLunes = () => {
    const delLunes = filas.filter((f) => Number(f.dia_semana) === 0)
    if (delLunes.length === 0) return
    const resto = filas.filter((f) => ![1, 2, 3, 4].includes(Number(f.dia_semana)))
    const copias = [1, 2, 3, 4].flatMap((dia) => delLunes.map((f) => ({ ...f, id: undefined, dia_semana: dia })))
    onCambio([...resto, ...copias].sort((a, b) => Number(a.dia_semana) - Number(b.dia_semana)))
  }

  return (
    <div className="sm:col-span-2">
      <p className="mb-1 block text-sm font-medium text-stone-800">{campo.etiqueta}</p>
      <div className="overflow-x-auto rounded-lg border border-stone-200">
        <table className="w-full min-w-max text-sm">
          <thead className="bg-marca-50 text-left text-stone-700">
            <tr>
              {subcampos.map((c) => <th key={c.nombre} className="px-2 py-1.5 font-semibold">{c.etiqueta}</th>)}
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {filas.map((fila, i) => (
              <tr key={i} className="border-t border-stone-100">
                {subcampos.map((c) => (
                  <td key={c.nombre} className="px-2 py-1">
                    <Celda campo={c} valor={fila[c.nombre]} onCambio={(v) => cambiarFila(i, c.nombre, v)} />
                  </td>
                ))}
                <td className="px-1">
                  {!deshabilitado && (
                    <button type="button" onClick={() => onCambio(filas.filter((_, j) => j !== i))} aria-label="Quitar fila"
                      className="rounded p-1 text-stone-400 hover:bg-red-50 hover:text-red-700"><Trash2 size={16} /></button>
                  )}
                </td>
              </tr>
            ))}
            {filas.length === 0 && (
              <tr><td colSpan={subcampos.length + 1} className="px-2 py-3 text-center text-stone-500">Sin filas.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {!deshabilitado && (
        <div className="mt-2 flex flex-wrap gap-2">
          <button type="button" onClick={agregar}
            className="flex items-center gap-1 rounded-lg border border-marca-700 px-3 py-1.5 text-sm font-medium text-marca-800 hover:bg-marca-50">
            <Plus size={16} /> Agregar fila
          </button>
          {campo.copiarLunes && (
            <button type="button" onClick={copiarLunes}
              className="flex items-center gap-1 rounded-lg border border-stone-300 px-3 py-1.5 text-sm text-stone-700 hover:bg-stone-50">
              <Copy size={16} /> Copiar el lunes a martes–viernes
            </button>
          )}
        </div>
      )}
      {campo.ayuda && !error && <p className="mt-1 text-xs text-stone-500">{campo.ayuda}</p>}
      {error && <p className="mt-1 text-sm text-red-700">{error}</p>}
    </div>
  )
}
