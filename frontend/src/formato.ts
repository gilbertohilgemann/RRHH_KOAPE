import type { Campo, Registro } from './tipos'

const numeroPy = new Intl.NumberFormat('es-PY', { maximumFractionDigits: 2 })

function dosDigitos(n: number) {
  return String(n).padStart(2, '0')
}

/** Fecha de hoy en formato AAAA-MM-DD, en la hora local (no UTC). */
export function hoyIso(): string {
  const d = new Date()
  return `${d.getFullYear()}-${dosDigitos(d.getMonth() + 1)}-${dosDigitos(d.getDate())}`
}

// Todas las fechas de la app se muestran como dd/mm/aaaa (y dd/mm/aaaa hh:mm),
// siempre, sin depender del idioma del navegador.

/** 'AAAA-MM-DD' → 'dd/mm/aaaa' ('' si viene vacía). */
export function fechaLegible(iso: string | null | undefined): string {
  if (!iso) return ''
  const [a, m, d] = iso.slice(0, 10).split('-')
  return d && m && a ? `${d}/${m}/${a}` : iso
}

/** Fecha y hora (Date o texto ISO de la API) → 'dd/mm/aaaa hh:mm' en hora local. */
export function fechaHoraLegible(valor: Date | string | null | undefined): string {
  if (!valor) return ''
  const d = valor instanceof Date ? valor : new Date(valor)
  if (Number.isNaN(d.getTime())) return String(valor)
  return `${dosDigitos(d.getDate())}/${dosDigitos(d.getMonth() + 1)}/${d.getFullYear()} ${dosDigitos(d.getHours())}:${dosDigitos(d.getMinutes())}`
}

/** 'dd/mm/aaaa' → 'AAAA-MM-DD', o null si no es una fecha válida. */
export function fechaDesdeTexto(texto: string): string | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(texto.trim())
  if (!m) return null
  const [, d, mes, a] = m
  const fecha = new Date(Number(a), Number(mes) - 1, Number(d))
  if (fecha.getFullYear() !== Number(a) || fecha.getMonth() !== Number(mes) - 1 || fecha.getDate() !== Number(d)) return null
  return `${a}-${mes}-${d}`
}

/** Texto para mostrar una celda o un dato. Usa el `<campo>_texto` que arma
 * la API para relaciones y opciones; formatea fechas y números. */
export function valorVisible(registro: Registro, nombre: string, campo?: Campo): string {
  const legible = registro[`${nombre}_texto`]
  if (typeof legible === 'string' && legible !== '') return legible

  const valor = registro[nombre]
  if (valor === null || valor === undefined || valor === '') return '—'
  if (typeof valor === 'boolean') return valor ? 'Sí' : 'No'
  if (Array.isArray(valor)) return valor.join(', ') || '—'

  const tipo = campo?.tipo
  if (typeof valor === 'string' && (tipo === 'fecha' || (!campo && /^\d{4}-\d{2}-\d{2}$/.test(valor)))) {
    return fechaLegible(valor)
  }
  if (typeof valor === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(valor)) {
    return fechaHoraLegible(valor)
  }
  // Números: los decimales llegan como texto desde Django ("12.50"). Los
  // códigos y documentos (texto) se dejan como vienen.
  if (typeof valor === 'number' || (typeof valor === 'string' && tipo && (tipo === 'entero' || tipo === 'decimal'))) {
    return numeroPy.format(Number(valor))
  }
  return String(valor)
}

/** Primer mensaje de error legible de una respuesta de DRF. */
export function mensajeDeError(datos: unknown, porDefecto = 'No se pudo completar la operación.'): string {
  if (!datos || typeof datos !== 'object') return porDefecto
  const d = datos as Record<string, unknown>
  if (typeof d.detail === 'string') return d.detail
  const generales = d.non_field_errors
  if (Array.isArray(generales) && generales.length) return String(generales[0])
  return porDefecto
}

/** Minutos → 'h:mm' (ej. 495 → '8:15'); 0 o vacío → '—'. */
export function horasMinutos(minutos: unknown): string {
  const m = Number(minutos ?? 0)
  if (!m) return '—'
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`
}

/** Importe en guaraníes con separador de miles (ej. 2730000 → '2.730.000'); vacío → '—'. */
export function guaranies(valor: unknown): string {
  if (valor === null || valor === undefined || valor === '') return '—'
  return Math.round(Number(valor)).toLocaleString('es-PY')
}

/** Fecha y hora de la API → valor para <input type="datetime-local"> en hora local. */
export function aEntradaFechaHora(valor: unknown): string {
  if (!valor) return ''
  const d = new Date(String(valor))
  if (Number.isNaN(d.getTime())) return String(valor).slice(0, 16)
  const dos = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}T${dos(d.getHours())}:${dos(d.getMinutes())}`
}