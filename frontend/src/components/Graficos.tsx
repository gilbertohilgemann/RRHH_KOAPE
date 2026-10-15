import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ArrowDownRight, ArrowUpRight, Minus, Table2, BarChart3 } from 'lucide-react'

/* Gráficos del tablero, en SVG propio (sin librerías). Reglas de la guía de
   visualización: marcas finas (columnas de hasta 24 px con punta redondeada de
   4 px, líneas de 2 px), separación de 2 px entre segmentos, grilla y ejes
   recesivos, una sola escala por gráfico, leyenda desde dos series, el texto
   siempre en tinta (nunca del color de la serie), tooltip al pasar el mouse y
   vista de tabla en cada gráfico (los colores claros no llegan a 3:1). */

/** Paleta categórica validada (orden fijo; el color sigue a la entidad, no a su posición en un ranking). */
export const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
const GRILLA = '#e7e5e4'
const EJE = '#d6d3d1'
const TINTA_SUAVE = '#78716c'

export interface Serie { nombre: string; color: string; valores: (number | null)[] }

const compacto = new Intl.NumberFormat('es-PY', { notation: 'compact', maximumFractionDigits: 1 })
export const numeroCompacto = (n: number) => compacto.format(n)
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
/** '2026-09' → 'sep 26' (o 'sep 2026' con `largo`). */
export function mesCorto(mes: string, largo = false) {
  const [a, m] = mes.split('-')
  return `${MESES[Number(m) - 1] ?? m} ${largo ? a : a.slice(2)}`
}

function useAncho<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [ancho, setAncho] = useState(0)
  useEffect(() => {
    if (!ref.current) return
    const observador = new ResizeObserver(([e]) => setAncho(Math.floor(e.contentRect.width)))
    observador.observe(ref.current)
    return () => observador.disconnect()
  }, [])
  return [ref, ancho] as const
}

/** Escala "linda": máximo redondeado y 4 marcas. */
function escala(maximo: number, enteros = false) {
  if (maximo <= 0) return { tope: 1, marcas: [0, 1] }
  const paso0 = enteros ? Math.max(1, maximo / 4) : maximo / 4
  const potencia = 10 ** Math.floor(Math.log10(paso0))
  const paso = (enteros ? [1, 2, 5, 10] : [1, 2, 2.5, 5, 10]).map((m) => m * potencia).find((p) => p >= paso0) ?? paso0
  const tope = paso * Math.ceil(maximo / paso)
  return { tope, marcas: Array.from({ length: Math.round(tope / paso) + 1 }, (_, i) => i * paso) }
}

export function Leyenda({ series }: { series: { nombre: string; color: string }[] }) {
  if (series.length < 2) return null
  return (
    <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-600">
      {series.map((s) => (
        <li key={s.nombre} className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />{s.nombre}
        </li>
      ))}
    </ul>
  )
}

interface DatosTooltip { x: number; y: number; titulo: string; filas: { nombre: string; color?: string; valor: string }[] }

function Tooltip({ datos, ancho }: { datos: DatosTooltip | null; ancho: number }) {
  if (!datos) return null
  const izquierda = datos.x > ancho / 2
  return (
    <div className="pointer-events-none absolute z-10 min-w-40 rounded-lg bg-white px-3 py-2 text-xs shadow-lg ring-1 ring-stone-200"
      style={{ top: Math.max(0, datos.y), ...(izquierda ? { right: ancho - datos.x + 12 } : { left: datos.x + 12 }) }}>
      <p className="mb-1 font-semibold text-stone-900">{datos.titulo}</p>
      {datos.filas.map((f) => (
        <p key={f.nombre} className="flex items-center justify-between gap-3 text-stone-700">
          <span className="flex items-center gap-1.5">
            {f.color && <span className="inline-block h-2 w-2 rounded-sm" style={{ background: f.color }} />}{f.nombre}
          </span>
          <span className="font-medium tabular-nums text-stone-900">{f.valor}</span>
        </p>
      ))}
    </div>
  )
}

const MARGEN = { arriba: 8, derecha: 8, abajo: 26, izquierda: 52 }

function Ejes({ ancho, alto, marcas, tope, formato }: { ancho: number; alto: number; marcas: number[]; tope: number; formato: (n: number) => string }) {
  const y = (v: number) => MARGEN.arriba + (alto - MARGEN.arriba - MARGEN.abajo) * (1 - v / tope)
  return (
    <g>
      {marcas.map((m) => (
        <g key={m}>
          <line x1={MARGEN.izquierda} x2={ancho - MARGEN.derecha} y1={y(m)} y2={y(m)} stroke={m === 0 ? EJE : GRILLA} strokeWidth={1} />
          <text x={MARGEN.izquierda - 6} y={y(m)} dy="0.32em" textAnchor="end" fontSize={11} fill={TINTA_SUAVE} style={{ fontVariantNumeric: 'tabular-nums' }}>
            {formato(m)}
          </text>
        </g>
      ))}
    </g>
  )
}

/** Etiquetas del eje X: salta las que no entran. */
function EtiquetasX({ categorias, x, alto, banda }: { categorias: string[]; x: (i: number) => number; alto: number; banda: number }) {
  const cada = Math.max(1, Math.ceil(44 / Math.max(banda, 1)))
  return (
    <g>
      {categorias.map((c, i) => i % cada === 0 ? (
        <text key={c + i} x={x(i)} y={alto - 8} textAnchor="middle" fontSize={11} fill={TINTA_SUAVE}>{c}</text>
      ) : null)}
    </g>
  )
}

/** Columna con la punta redondeada (4 px) y la base recta. */
function pathColumna(x: number, y: number, w: number, h: number, redondear: boolean) {
  if (h <= 0) return ''
  const r = redondear ? Math.min(4, w / 2, h) : 0
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}

interface PropsColumnas {
  /** Conteos: marcas del eje en números enteros. */
  enteros?: boolean
  categorias: string[]
  titulos?: string[]
  series: Serie[]
  formato: (n: number) => string
  formatoEje?: (n: number) => string
  apiladas?: boolean
  alto?: number
  total?: string
}

/** Columnas por categoría (meses): apiladas o agrupadas. */
export function Columnas({ categorias, titulos, series, formato, formatoEje = numeroCompacto, apiladas = true, alto = 240, total, enteros = false }: PropsColumnas) {
  const [ref, ancho] = useAncho<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const sumas = categorias.map((_, i) => series.reduce((s, serie) => s + Math.max(0, serie.valores[i] ?? 0), 0))
  const maximo = apiladas ? Math.max(0, ...sumas) : Math.max(0, ...series.flatMap((s) => s.valores.map((v) => v ?? 0)))
  const { tope, marcas } = escala(maximo, enteros)
  const interior = Math.max(0, ancho - MARGEN.izquierda - MARGEN.derecha)
  const banda = categorias.length ? interior / categorias.length : 0
  const x = (i: number) => MARGEN.izquierda + banda * (i + 0.5)
  const altoUtil = alto - MARGEN.arriba - MARGEN.abajo
  const h = (v: number) => (altoUtil * Math.max(0, v)) / tope
  const grueso = apiladas ? Math.min(24, banda * 0.6) : Math.min(16, (banda * 0.8) / Math.max(1, series.length) - 2)
  const tooltip: DatosTooltip | null = hover === null ? null : {
    x: x(hover), y: MARGEN.arriba, titulo: titulos?.[hover] ?? categorias[hover],
    filas: [...series.map((s) => ({ nombre: s.nombre, color: s.color, valor: s.valores[hover] === null ? '—' : formato(s.valores[hover] ?? 0) })),
      ...(apiladas && total && series.length > 1 ? [{ nombre: total, valor: formato(sumas[hover]) }] : [])],
  }
  return (
    <div ref={ref} className="relative min-w-0 overflow-hidden" onMouseLeave={() => setHover(null)}>
      {ancho > 0 && (
        <svg width={ancho} height={alto} role="img" aria-label="Gráfico de columnas">
          <Ejes ancho={ancho} alto={alto} marcas={marcas} tope={tope} formato={formatoEje} />
          {hover !== null && <rect x={x(hover) - banda / 2} y={MARGEN.arriba} width={banda} height={altoUtil} fill="#f5f5f4" />}
          {categorias.map((_, i) => {
            if (apiladas) {
              let base = alto - MARGEN.abajo
              const visibles = series.map((s) => Math.max(0, s.valores[i] ?? 0))
              const ultimo = visibles.reduce((u, v, k) => (v > 0 ? k : u), -1)
              return (
                <g key={i}>
                  {series.map((s, k) => {
                    const alturaReal = h(visibles[k])
                    if (alturaReal <= 0) return null
                    const y = base - alturaReal
                    // 2 px de aire entre segmentos (se le quita al segmento de abajo).
                    const altura = k === ultimo ? alturaReal : Math.max(0, alturaReal - 2)
                    base = y
                    return <path key={s.nombre} d={pathColumna(x(i) - grueso / 2, k === ultimo ? y : y + 2, grueso, altura, k === ultimo)} fill={s.color} />
                  })}
                </g>
              )
            }
            const totalAncho = series.length * grueso + (series.length - 1) * 2
            return (
              <g key={i}>
                {series.map((s, k) => {
                  const altura = h(s.valores[i] ?? 0)
                  return <path key={s.nombre} d={pathColumna(x(i) - totalAncho / 2 + k * (grueso + 2), alto - MARGEN.abajo - altura, grueso, altura, true)} fill={s.color} />
                })}
              </g>
            )
          })}
          <EtiquetasX categorias={categorias} x={x} alto={alto} banda={banda} />
          {categorias.map((_, i) => (
            <rect key={i} x={x(i) - banda / 2} y={MARGEN.arriba} width={banda} height={altoUtil} fill="transparent" onMouseEnter={() => setHover(i)} />
          ))}
        </svg>
      )}
      <Tooltip datos={tooltip} ancho={ancho} />
    </div>
  )
}

interface PropsLineas {
  /** Conteos: marcas del eje en números enteros. */
  enteros?: boolean
  categorias: string[]
  titulos?: string[]
  series: Serie[]
  formato: (n: number) => string
  formatoEje?: (n: number) => string
  alto?: number
}

/** Líneas por mes con cruz de lectura y tooltip. */
export function Lineas({ categorias, titulos, series, formato, formatoEje = numeroCompacto, alto = 240, enteros = false }: PropsLineas) {
  const [ref, ancho] = useAncho<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const maximo = Math.max(0, ...series.flatMap((s) => s.valores.map((v) => v ?? 0)))
  const { tope, marcas } = escala(maximo, enteros)
  const interior = Math.max(0, ancho - MARGEN.izquierda - MARGEN.derecha)
  const banda = categorias.length ? interior / categorias.length : 0
  const x = (i: number) => MARGEN.izquierda + banda * (i + 0.5)
  const altoUtil = alto - MARGEN.arriba - MARGEN.abajo
  const y = (v: number) => MARGEN.arriba + altoUtil * (1 - v / tope)
  // Un mes sin dato corta la línea (no se inventa un cero).
  const tramo = (s: Serie) => {
    let d = ''
    let abierto = false
    s.valores.forEach((v, i) => {
      if (v === null) { abierto = false; return }
      d += `${abierto ? 'L' : 'M'}${x(i)},${y(v)}`
      abierto = true
    })
    return d
  }
  const tooltip: DatosTooltip | null = hover === null ? null : {
    x: x(hover), y: MARGEN.arriba, titulo: titulos?.[hover] ?? categorias[hover],
    filas: series.map((s) => ({ nombre: s.nombre, color: s.color, valor: s.valores[hover] === null ? '—' : formato(s.valores[hover] ?? 0) })),
  }
  return (
    <div ref={ref} className="relative min-w-0 overflow-hidden" onMouseLeave={() => setHover(null)}>
      {ancho > 0 && (
        <svg width={ancho} height={alto} role="img" aria-label="Gráfico de líneas">
          <Ejes ancho={ancho} alto={alto} marcas={marcas} tope={tope} formato={formatoEje} />
          {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={MARGEN.arriba} y2={alto - MARGEN.abajo} stroke={EJE} strokeWidth={1} />}
          {series.map((s) => (
            <path key={s.nombre} d={tramo(s)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {series.map((s) => {
            const i = hover ?? s.valores.reduce<number>((u, v, k) => (v !== null ? k : u), -1)
            const v = s.valores[i]
            return i >= 0 && v !== null && v !== undefined
              ? <circle key={s.nombre} cx={x(i)} cy={y(v)} r={4} fill={s.color} stroke="white" strokeWidth={2} /> : null
          })}
          <EtiquetasX categorias={categorias} x={x} alto={alto} banda={banda} />
          {categorias.map((_, i) => (
            <rect key={i} x={x(i) - banda / 2} y={MARGEN.arriba} width={banda} height={altoUtil} fill="transparent" onMouseEnter={() => setHover(i)} />
          ))}
        </svg>
      )}
      <Tooltip datos={tooltip} ancho={ancho} />
    </div>
  )
}

export interface FilaBarra { etiqueta: string; valores: number[]; nota?: string }

/** Barras horizontales (ranking o comparación A/B). El valor va en la punta. */
export function Barras({ filas, series, formato }: { filas: FilaBarra[]; series: { nombre: string; color: string }[]; formato: (n: number) => string }) {
  const maximo = Math.max(0, ...filas.flatMap((f) => f.valores))
  const [hover, setHover] = useState<number | null>(null)
  return (
    <div className="space-y-2">
      {filas.map((f, i) => (
        <div key={f.etiqueta + i} className={`grid grid-cols-[minmax(6rem,38%)_1fr] items-center gap-3 rounded-md px-1 ${hover === i ? 'bg-stone-50' : ''}`}
          onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
          title={`${f.etiqueta}: ${f.valores.map((v, k) => `${series[k]?.nombre ?? ''} ${formato(v)}`).join(' · ')}`}>
          <span className="truncate text-sm text-stone-700">{f.etiqueta}</span>
          <div className="min-w-0 space-y-0.5 py-0.5">
            {f.valores.map((v, k) => (
              <div key={k} className="flex items-center gap-2">
                <div className="h-3.5 rounded-r" style={{ width: `${maximo ? Math.max(0.5, (v / maximo) * 78) : 0}%`, background: series[k]?.color }} />
                <span className="whitespace-nowrap text-xs tabular-nums text-stone-700">
                  {formato(v)}{k === 0 && f.nota ? <span className="ml-1 text-stone-500">{f.nota}</span> : null}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export interface ColumnaTabla { titulo: string; valores: string[] }

/** Tarjeta de un gráfico con su título, leyenda y el botón para ver los datos como tabla. */
export function Panel({ titulo, subtitulo, series, tabla, children, className = '' }: {
  titulo: string; subtitulo?: string; series?: { nombre: string; color: string }[]
  tabla?: { encabezado: string; filas: string[]; columnas: ColumnaTabla[] }; children: ReactNode; className?: string
}) {
  const [verTabla, setVerTabla] = useState(false)
  return (
    <section className={`min-w-0 rounded-xl bg-white p-4 ring-1 ring-stone-200 ${className}`}>
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold text-stone-900">{titulo}</h2>
          {subtitulo && <p className="text-xs text-stone-500">{subtitulo}</p>}
        </div>
        {tabla && (
          <button type="button" onClick={() => setVerTabla(!verTabla)} title={verTabla ? 'Ver gráfico' : 'Ver como tabla'}
            className="rounded-md p-1.5 text-stone-500 hover:bg-stone-100" aria-label={verTabla ? 'Ver gráfico' : 'Ver como tabla'}>
            {verTabla ? <BarChart3 size={16} /> : <Table2 size={16} />}
          </button>
        )}
      </div>
      {verTabla && tabla ? (
        <div className="max-h-80 overflow-auto rounded-lg border border-stone-200">
          <table className="w-full min-w-max text-xs">
            <thead className="sticky top-0 bg-stone-50 text-left text-stone-600">
              <tr><th className="px-2 py-1">{tabla.encabezado}</th>{tabla.columnas.map((c) => <th key={c.titulo} className="px-2 py-1 text-right">{c.titulo}</th>)}</tr>
            </thead>
            <tbody>
              {tabla.filas.map((f, i) => (
                <tr key={f + i} className="border-t border-stone-100">
                  <td className="px-2 py-1 text-stone-700">{f}</td>
                  {tabla.columnas.map((c) => <td key={c.titulo} className="px-2 py-1 text-right tabular-nums text-stone-900">{c.valores[i]}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          {series && <Leyenda series={series} />}
          {children}
        </>
      )}
    </section>
  )
}

/** Variación porcentual con flecha (sin color de "bueno/malo": en nómina depende de qué se mira). */
export function Variacion({ actual, anterior, etiqueta }: { actual?: number; anterior?: number; etiqueta: string }) {
  if (actual === undefined || !anterior) return <p className="text-xs text-stone-400">{etiqueta}: sin dato</p>
  const cambio = ((actual - anterior) / Math.abs(anterior)) * 100
  const Icono = Math.abs(cambio) < 0.05 ? Minus : cambio > 0 ? ArrowUpRight : ArrowDownRight
  return (
    <p className="flex items-center gap-1 text-xs text-stone-600">
      <Icono size={14} className="text-stone-500" />
      <span className="font-medium tabular-nums text-stone-800">{cambio > 0 ? '+' : ''}{cambio.toLocaleString('es-PY', { maximumFractionDigits: 1 })} %</span>
      <span>{etiqueta}</span>
    </p>
  )
}

/** Tarjeta de indicador: etiqueta, valor y variaciones. */
export function Indicador({ etiqueta, valor, children }: { etiqueta: string; valor: string; children?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl bg-white p-4 ring-1 ring-stone-200">
      <p className="text-sm text-stone-600">{etiqueta}</p>
      <p className="mt-1 text-2xl font-semibold text-stone-900">{valor}</p>
      <div className="mt-1 space-y-0.5">{children}</div>
    </div>
  )
}
