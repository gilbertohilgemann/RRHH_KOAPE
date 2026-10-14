import { useEffect, useRef, useState } from 'react'
import { CalendarDays } from 'lucide-react'
import { fechaDesdeTexto, fechaLegible } from '../formato'

interface Props {
  /** Fecha en formato de la API: 'AAAA-MM-DD' ('' = vacía). */
  valor: string
  onCambio: (iso: string) => void
  id?: string
  invalido?: boolean
  disabled?: boolean
  className?: string
  'aria-label'?: string
}

/** Campo de fecha que SIEMPRE muestra y acepta dd/mm/aaaa, sin depender del
 * idioma del navegador (el <input type="date"> estándar muestra mm/dd/aaaa
 * en un navegador en inglés). Se escribe con las barras automáticas o se
 * elige en el calendario del botón. Hacia afuera trabaja con 'AAAA-MM-DD'. */
export default function CampoFecha({ valor, onCambio, id, invalido, disabled, className, ...resto }: Props) {
  const [texto, setTexto] = useState(fechaLegible(valor))
  const calendario = useRef<HTMLInputElement>(null)

  // Si la fecha cambia desde afuera (precargada, limpiada), se muestra.
  useEffect(() => {
    setTexto((actual) => (fechaDesdeTexto(actual) === valor ? actual : fechaLegible(valor)))
  }, [valor])

  const escribir = (entrada: string) => {
    // Solo números, con las barras puestas solas: 01102026 → 01/10/2026.
    const digitos = entrada.replace(/\D/g, '').slice(0, 8)
    let armado = digitos
    if (digitos.length > 4) armado = `${digitos.slice(0, 2)}/${digitos.slice(2, 4)}/${digitos.slice(4)}`
    else if (digitos.length > 2) armado = `${digitos.slice(0, 2)}/${digitos.slice(2)}`
    setTexto(armado)
    if (armado === '') onCambio('')
    else {
      const iso = fechaDesdeTexto(armado)
      if (iso) onCambio(iso)
    }
  }

  const incompleta = texto !== '' && fechaDesdeTexto(texto) === null
  const abrirCalendario = () => {
    const campo = calendario.current
    if (!campo) return
    try {
      campo.showPicker()
    } catch {
      campo.focus()
      campo.click()
    }
  }

  return (
    <div className={`relative flex items-center ${className ?? ''}`}>
      <input id={id} type="text" inputMode="numeric" placeholder="dd/mm/aaaa" value={texto} disabled={disabled}
        onChange={(e) => escribir(e.target.value)}
        onBlur={() => { if (incompleta) setTexto(fechaLegible(valor)) }}
        aria-label={resto['aria-label']} aria-invalid={invalido || incompleta || undefined}
        className={`w-full rounded-lg border bg-white p-2 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-marca-600 disabled:bg-stone-50 ${invalido || incompleta ? 'border-red-500' : 'border-stone-300'}`} />
      <button type="button" onClick={abrirCalendario} disabled={disabled} title="Elegir en el calendario"
        aria-label="Elegir en el calendario" className="absolute right-1.5 rounded p-1 text-stone-500 hover:bg-stone-100 disabled:opacity-40">
        <CalendarDays size={16} />
      </button>
      {/* Calendario del navegador, invisible: solo se usa su selector. */}
      <input ref={calendario} type="date" tabIndex={-1} aria-hidden="true" value={valor} disabled={disabled}
        onChange={(e) => { onCambio(e.target.value); setTexto(fechaLegible(e.target.value)) }}
        className="pointer-events-none absolute bottom-0 right-0 h-0 w-0 opacity-0" />
    </div>
  )
}
