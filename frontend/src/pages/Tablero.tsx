import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ChevronLeft, Download, X } from 'lucide-react'
import api from '../services/api'
import { descargarArchivo } from '../descargas'
import { guaranies, mensajeDeError } from '../formato'
import { Barras, Columnas, Indicador, Lineas, Panel, SERIES, Variacion, mesCorto, numeroCompacto, type Serie } from '../components/Graficos'

interface Detalle { [campo: string]: string | number | undefined | Detalle[] }
interface Fila extends Detalle { clave: string; etiqueta: string; meses?: Detalle[] }
type FilaConMeses = Fila
interface Secciones { nomina: boolean; costo: boolean; licencias: boolean; asistencia: boolean; personal: boolean }
interface Concepto { codigo: string; nombre: string; tipo: string; total: string }
interface PorTipo { tipo: string; solicitudes: number; dias: string; horas: string }
interface Datos {
  secciones: Secciones; agrupar: string; meses: string[]; filas: FilaConMeses[]
  conceptos?: Concepto[]; resumen?: { mes: Detalle; anterior: Detalle; anio_anterior: Detalle } | null; licencias_por_tipo?: PorTipo[]
}
interface Opcion { id: number; nombre: string; baja?: boolean }
interface Opciones { secciones: Secciones; departamentos: Opcion[]; sucursales: Opcion[]; centros: Opcion[]; empleados: Opcion[] }

type Formato = 'gs' | 'n' | '%' | 'h'
interface Metrica { clave: string; nombre: string; seccion: keyof Secciones; formato: Formato; calculo?: (d: Detalle) => number | null; suma?: boolean }

const n = (v: unknown) => Number(v ?? 0)
const porcentaje = (parte: number, total: number) => (total ? (parte / total) * 100 : null)

const METRICAS: Metrica[] = [
  { clave: 'bruto', nombre: 'Bruto', seccion: 'nomina', formato: 'gs', suma: true },
  { clave: 'neto', nombre: 'Neto a cobrar', seccion: 'nomina', formato: 'gs', suma: true },
  { clave: 'aportes_trabajador', nombre: 'Aporte IPS del trabajador', seccion: 'nomina', formato: 'gs', suma: true },
  { clave: 'descuentos', nombre: 'Descuentos', seccion: 'nomina', formato: 'gs', suma: true },
  { clave: 'aportes_patronales', nombre: 'Aporte IPS del empleador', seccion: 'costo', formato: 'gs', suma: true },
  { clave: 'costo_empleador', nombre: 'Costo del empleador', seccion: 'costo', formato: 'gs', suma: true },
  { clave: 'empleados_liquidados', nombre: 'Empleados liquidados', seccion: 'nomina', formato: 'n' },
  { clave: 'descuentos_pct', nombre: 'Descuentos (% del bruto)', seccion: 'nomina', formato: '%', calculo: (d) => porcentaje(n(d.descuentos), n(d.bruto)) },
  { clave: 'dias_licencia', nombre: 'Días de licencia', seccion: 'licencias', formato: 'n', suma: true },
  { clave: 'horas_permiso', nombre: 'Horas de permiso', seccion: 'licencias', formato: 'h', suma: true },
  { clave: 'ausencias', nombre: 'Ausencias (días)', seccion: 'asistencia', formato: 'n', suma: true },
  { clave: 'ausentismo', nombre: 'Ausentismo (%)', seccion: 'asistencia', formato: '%', calculo: (d) => porcentaje(n(d.ausencias), n(d.dias_laborables)) },
  { clave: 'horas_extra', nombre: 'Horas extra autorizadas', seccion: 'asistencia', formato: 'h', suma: true },
  { clave: 'horas_tardanza', nombre: 'Horas de tardanza', seccion: 'asistencia', formato: 'h', suma: true, calculo: (d) => n(d.minutos_tardanza) / 60 },
  { clave: 'dotacion', nombre: 'Dotación', seccion: 'personal', formato: 'n' },
  { clave: 'altas', nombre: 'Altas', seccion: 'personal', formato: 'n', suma: true },
  { clave: 'bajas', nombre: 'Bajas', seccion: 'personal', formato: 'n', suma: true },
]

function valor(d: Detalle | undefined, m: Metrica): number | null {
  if (!d) return null
  if (m.calculo) return m.calculo(d)
  return d[m.clave] === undefined ? null : n(d[m.clave])
}

function formatear(v: number | null, f: Formato) {
  if (v === null || Number.isNaN(v)) return '—'
  if (f === 'gs') return guaranies(v)
  if (f === '%') return `${v.toLocaleString('es-PY', { maximumFractionDigits: 1 })} %`
  return v.toLocaleString('es-PY', { maximumFractionDigits: f === 'h' ? 1 : 0 })
}
const formatoDe = (f: Formato) => (v: number) => formatear(v, f)
const ejeDe = (f: Formato) => (f === '%' ? (v: number) => `${v} %` : numeroCompacto)

// ------------------------------------------------------------------ meses
const mesIso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
function sumarMeses(mes: string, cantidad: number) {
  const [a, m] = mes.split('-').map(Number)
  return mesIso(new Date(a, m - 1 + cantidad, 1))
}
function ultimoDia(mes: string) {
  const [a, m] = mes.split('-').map(Number)
  return `${mes}-${String(new Date(a, m, 0).getDate()).padStart(2, '0')}`
}
const cantidadMeses = (desde: string, hasta: string) => {
  const [a1, m1] = desde.split('-').map(Number)
  const [a2, m2] = hasta.split('-').map(Number)
  return (a2 - a1) * 12 + (m2 - m1) + 1
}
const rango = (desde: string, hasta: string) => `${mesCorto(desde, true)} – ${mesCorto(hasta, true)}`

function SelectorMes({ etiqueta, valor: actual, onCambio }: { etiqueta: string; valor: string; onCambio: (v: string) => void }) {
  const hoy = mesIso(new Date())
  const opciones = Array.from({ length: 72 }, (_, i) => sumarMeses(hoy, -i))
  return (
    <label className="text-sm font-medium text-stone-800">{etiqueta}
      <select value={actual} onChange={(e) => onCambio(e.target.value)} className="mt-1 block rounded-lg border border-stone-300 p-2">
        {opciones.map((m) => <option key={m} value={m}>{mesCorto(m, true)}</option>)}
      </select>
    </label>
  )
}

function Lista({ etiqueta, valor: actual, opciones, onCambio, todos }: { etiqueta: string; valor: string; opciones: Opcion[]; onCambio: (v: string) => void; todos: string }) {
  if (opciones.length === 0) return null
  return (
    <label className="text-sm font-medium text-stone-800">{etiqueta}
      <select value={actual} onChange={(e) => onCambio(e.target.value)} className="mt-1 block max-w-52 rounded-lg border border-stone-300 p-2">
        <option value="">{todos}</option>
        {opciones.map((o) => <option key={o.id} value={o.id}>{o.nombre}</option>)}
      </select>
    </label>
  )
}

type Pestana = 'nomina' | 'comparar' | 'personal' | 'licencias'
type ModoComparar = 'periodos' | 'departamento' | 'sucursal' | 'centro_costo' | 'empleado'
const MODOS: { clave: ModoComparar; nombre: string }[] = [
  { clave: 'periodos', nombre: 'Períodos' }, { clave: 'departamento', nombre: 'Departamentos' }, { clave: 'sucursal', nombre: 'Sucursales' },
  { clave: 'centro_costo', nombre: 'Centros de costo' }, { clave: 'empleado', nombre: 'Empleados' },
]
const MAXIMO_LINEAS = 6

/** Tablero de gestión: nómina, IPS, descuentos, licencias, asistencia y dotación, con comparaciones. */
export default function Tablero() {
  const hoy = mesIso(new Date())
  const [opciones, setOpciones] = useState<Opciones | null>(null)
  const [error, setError] = useState('')
  const [desde, setDesde] = useState(sumarMeses(hoy, -11))
  const [hasta, setHasta] = useState(hoy)
  const [sucursal, setSucursal] = useState('')
  const [departamento, setDepartamento] = useState('')
  const [centro, setCentro] = useState('')
  const [empleados, setEmpleados] = useState<number[]>([])
  const [busqueda, setBusqueda] = useSearchParams()
  const pestana = (busqueda.get('pestana') as Pestana | null) ?? 'nomina'
  const setPestana = (p: Pestana) => setBusqueda(p === 'nomina' ? {} : { pestana: p }, { replace: true })
  const [porMes, setPorMes] = useState<Datos | null>(null)

  const [modo, setModo] = useState<ModoComparar>((busqueda.get('modo') as ModoComparar | null) ?? 'periodos')
  const [metrica, setMetrica] = useState('bruto')
  const [desdeB, setDesdeB] = useState(sumarMeses(hoy, -23))
  const [hastaB, setHastaB] = useState(sumarMeses(hoy, -12))
  const [desglose, setDesglose] = useState<'departamento' | 'sucursal' | 'centro_costo'>('departamento')
  const [comparacion, setComparacion] = useState<{ a?: Datos; b?: Datos; desgloseA?: Datos; desgloseB?: Datos; grupos?: Datos } | null>(null)

  useEffect(() => {
    api.get<Opciones>('/tablero/opciones/').then((r) => setOpciones(r.data))
      .catch((e) => setError(mensajeDeError(e.response?.data, 'No se pudo abrir el tablero.')))
  }, [])

  const filtros = useMemo(() => {
    const p: Record<string, string> = {}
    if (sucursal) p.sucursales = sucursal
    if (departamento) p.departamentos = departamento
    if (centro) p.centros = centro
    if (empleados.length) p.empleados = empleados.join(',')
    return p
  }, [sucursal, departamento, centro, empleados])

  const pedir = (params: Record<string, string>) => api.get<Datos>('/tablero/', { params: { ...filtros, ...params } }).then((r) => r.data)
  const rangoA = { desde: `${desde}-01`, hasta: ultimoDia(hasta) }
  const rangoB = { desde: `${desdeB}-01`, hasta: ultimoDia(hastaB) }

  useEffect(() => {
    if (!opciones) return
    setPorMes(null)
    pedir({ ...rangoA, agrupar: 'mes' }).then((d) => { setPorMes(d); setError('') })
      .catch((e) => setError(mensajeDeError(e.response?.data, 'No se pudieron traer los datos.')))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opciones, desde, hasta, filtros])

  useEffect(() => {
    if (!opciones || pestana !== 'comparar') return
    setComparacion(null)
    const pedido = modo === 'periodos'
      ? Promise.all([pedir({ ...rangoA, agrupar: 'total' }), pedir({ ...rangoB, agrupar: 'total' }),
        pedir({ ...rangoA, agrupar: desglose }), pedir({ ...rangoB, agrupar: desglose })])
        .then(([a, b, desgloseA, desgloseB]) => ({ a, b, desgloseA, desgloseB }))
      : pedir({ ...rangoA, agrupar: modo, por_mes: '1' }).then((grupos) => ({ grupos }))
    pedido.then((c) => { setComparacion(c); setError('') })
      .catch((e) => setError(mensajeDeError(e.response?.data, 'No se pudo armar la comparación.')))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opciones, pestana, modo, desde, hasta, desdeB, hastaB, desglose, filtros])

  const secciones = opciones?.secciones
  const visibles = METRICAS.filter((m) => secciones?.[m.seccion])
  const actual = visibles.find((m) => m.clave === metrica) ?? visibles[0]

  const exportar = () => {
    const params = pestana === 'comparar' && modo !== 'periodos'
      ? { ...rangoA, agrupar: modo, por_mes: '1' } : { ...rangoA, agrupar: 'mes' }
    descargarArchivo(`/tablero/?${new URLSearchParams({ ...filtros, ...params, formato: 'xlsx' })}`, 'tablero.xlsx')
      .catch(() => setError('No se pudo exportar.'))
  }

  const pestanas: { clave: Pestana; nombre: string; ver: boolean }[] = [
    { clave: 'nomina', nombre: 'Nómina', ver: !!secciones?.nomina },
    { clave: 'comparar', nombre: 'Comparar', ver: true },
    { clave: 'personal', nombre: 'Personal y asistencia', ver: !!(secciones?.personal || secciones?.asistencia) },
    { clave: 'licencias', nombre: 'Licencias y permisos', ver: !!secciones?.licencias },
  ]
  const enPestana = pestanas.find((p) => p.clave === pestana && p.ver) ? pestana : pestanas.find((p) => p.ver)?.clave

  return (
    <div className="min-w-0 space-y-4">
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <div className="mb-3 flex items-center gap-2">
          <Link to="/" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
          <h1 className="text-xl font-bold text-stone-900">Tablero</h1>
        </div>
        {error && <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
        {opciones && (
          <>
            <div className="flex flex-wrap items-end gap-3">
              <SelectorMes etiqueta="Desde" valor={desde} onCambio={setDesde} />
              <SelectorMes etiqueta="Hasta" valor={hasta} onCambio={setHasta} />
              <Lista etiqueta="Sucursal" valor={sucursal} opciones={opciones.sucursales} onCambio={setSucursal} todos="Todas" />
              <Lista etiqueta="Departamento" valor={departamento} opciones={opciones.departamentos} onCambio={setDepartamento} todos="Todos" />
              <Lista etiqueta="Centro de costo" valor={centro} opciones={opciones.centros} onCambio={setCentro} todos="Todos" />
              <label className="text-sm font-medium text-stone-800">Empleados
                <select value="" onChange={(e) => e.target.value && setEmpleados([...empleados, Number(e.target.value)])}
                  className="mt-1 block max-w-60 rounded-lg border border-stone-300 p-2">
                  <option value="">{empleados.length ? 'Agregar otro…' : 'Todos (elegí para filtrar)'}</option>
                  {opciones.empleados.filter((o) => !empleados.includes(o.id)).map((o) => (
                    <option key={o.id} value={o.id}>{o.nombre}{o.baja ? ' · baja' : ''}</option>
                  ))}
                </select>
              </label>
              <button type="button" onClick={exportar}
                className="flex items-center gap-1 rounded-lg bg-marca-700 px-3 py-2 text-sm font-medium text-white hover:bg-marca-600">
                <Download size={16} /> Excel
              </button>
            </div>
            {empleados.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {empleados.map((id) => (
                  <span key={id} className="flex items-center gap-1 rounded-full bg-stone-100 py-0.5 pr-1 pl-3 text-xs text-stone-700">
                    {opciones.empleados.find((o) => o.id === id)?.nombre}
                    <button type="button" aria-label="Quitar" onClick={() => setEmpleados(empleados.filter((e) => e !== id))}
                      className="rounded-full p-0.5 hover:bg-stone-200"><X size={12} /></button>
                  </span>
                ))}
              </div>
            )}
            <nav className="mt-4 flex flex-wrap gap-1 border-b border-stone-200">
              {pestanas.filter((p) => p.ver).map((p) => (
                <button key={p.clave} type="button" onClick={() => setPestana(p.clave)}
                  className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${enPestana === p.clave ? 'border-marca-700 text-marca-800' : 'border-transparent text-stone-500 hover:text-stone-800'}`}>
                  {p.nombre}
                </button>
              ))}
            </nav>
          </>
        )}
      </div>

      {opciones && !porMes && !error && <p className="text-sm text-stone-500">Cargando…</p>}
      {porMes && enPestana === 'nomina' && <PestanaNomina datos={porMes} />}
      {porMes && enPestana === 'personal' && <PestanaPersonal datos={porMes} />}
      {porMes && enPestana === 'licencias' && <PestanaLicencias datos={porMes} />}
      {opciones && enPestana === 'comparar' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-3 rounded-xl bg-white p-4 ring-1 ring-stone-200">
            <div>
              <p className="text-sm font-medium text-stone-800">Comparar</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {MODOS.filter((m) => m.clave !== 'sucursal' || opciones.sucursales.length > 1).map((m) => (
                  <button key={m.clave} type="button" onClick={() => setModo(m.clave)}
                    className={`rounded-lg px-3 py-2 text-sm ${modo === m.clave ? 'bg-marca-700 text-white' : 'bg-stone-100 text-stone-700 hover:bg-stone-200'}`}>
                    {m.nombre}
                  </button>
                ))}
              </div>
            </div>
            <label className="text-sm font-medium text-stone-800">Indicador
              <select value={actual?.clave} onChange={(e) => setMetrica(e.target.value)} className="mt-1 block rounded-lg border border-stone-300 p-2">
                {visibles.map((m) => <option key={m.clave} value={m.clave}>{m.nombre}</option>)}
              </select>
            </label>
            {modo === 'periodos' && (
              <>
                <SelectorMes etiqueta="Período B desde" valor={desdeB} onCambio={setDesdeB} />
                <SelectorMes etiqueta="Período B hasta" valor={hastaB} onCambio={setHastaB} />
                <div className="flex gap-1">
                  <button type="button" onClick={() => { setDesdeB(sumarMeses(desde, -12)); setHastaB(sumarMeses(hasta, -12)) }}
                    className="rounded-lg bg-stone-100 px-3 py-2 text-sm text-stone-700 hover:bg-stone-200">Un año antes</button>
                  <button type="button" onClick={() => { const largo = cantidadMeses(desde, hasta); setDesdeB(sumarMeses(desde, -largo)); setHastaB(sumarMeses(desde, -1)) }}
                    className="rounded-lg bg-stone-100 px-3 py-2 text-sm text-stone-700 hover:bg-stone-200">Período anterior</button>
                </div>
                <label className="text-sm font-medium text-stone-800">Desglose
                  <select value={desglose} onChange={(e) => setDesglose(e.target.value as typeof desglose)} className="mt-1 block rounded-lg border border-stone-300 p-2">
                    <option value="departamento">Por departamento</option>
                    {opciones.sucursales.length > 1 && <option value="sucursal">Por sucursal</option>}
                    <option value="centro_costo">Por centro de costo</option>
                  </select>
                </label>
              </>
            )}
          </div>
          {!comparacion && !error && <p className="text-sm text-stone-500">Cargando…</p>}
          {comparacion && actual && modo === 'periodos' && comparacion.a && comparacion.b && (
            <ComparaPeriodos metricas={visibles} actual={actual} etiquetaA={rango(desde, hasta)} etiquetaB={rango(desdeB, hastaB)}
              a={comparacion.a} b={comparacion.b} desgloseA={comparacion.desgloseA!} desgloseB={comparacion.desgloseB!} />
          )}
          {comparacion && actual && modo !== 'periodos' && comparacion.grupos && (
            <ComparaGrupos datos={comparacion.grupos} metricas={visibles} actual={actual}
              titulo={MODOS.find((m) => m.clave === modo)!.nombre} elegidos={modo === 'empleado' ? empleados : []} />
          )}
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------- pestañas

const tablaMeses = (datos: Datos, columnas: { titulo: string; valores: (number | null)[]; formato: Formato }[]) => ({
  encabezado: 'Mes', filas: datos.meses.map((m) => mesCorto(m, true)),
  columnas: columnas.map((c) => ({ titulo: c.titulo, valores: c.valores.map((v) => formatear(v, c.formato)) })),
})

function serieDe(datos: Datos, m: Metrica, color: string, nombre = m.nombre): Serie {
  const porClave = Object.fromEntries(datos.filas.map((f) => [f.clave, f]))
  return { nombre, color, valores: datos.meses.map((mes) => valor(porClave[mes], m)) }
}
const metricaDe = (clave: string) => METRICAS.find((m) => m.clave === clave)!

function PestanaNomina({ datos }: { datos: Datos }) {
  const r = datos.resumen
  const costo = datos.secciones.costo
  const categorias = datos.meses.map((m) => mesCorto(m))
  const titulos = datos.meses.map((m) => mesCorto(m, true))
  // Del costo al neto: los segmentos suman el bruto (y, con el aporte del empleador, el costo total).
  const composicion: Serie[] = [
    serieDe(datos, metricaDe('neto'), SERIES[0], 'Neto'),
    serieDe(datos, metricaDe('aportes_trabajador'), SERIES[1], 'IPS del trabajador'),
    serieDe(datos, metricaDe('descuentos'), SERIES[2], 'Descuentos'),
    ...(costo ? [serieDe(datos, metricaDe('aportes_patronales'), SERIES[3], 'IPS del empleador')] : []),
  ]
  const porMes = Object.fromEntries(datos.filas.map((f) => [f.clave, f]))
  const pct = (clave: string) => datos.meses.map((m) => (porMes[m]?.bruto ? porcentaje(n(porMes[m][clave]), n(porMes[m].bruto)) : null))
  const porcentajes: Serie[] = [
    { nombre: 'IPS del trabajador', color: SERIES[1], valores: pct('aportes_trabajador') },
    { nombre: 'Descuentos', color: SERIES[2], valores: pct('descuentos') },
    ...(costo ? [{ nombre: 'IPS del empleador', color: SERIES[3], valores: pct('aportes_patronales') }] : []),
  ]
  const brutoTotal = datos.filas.reduce((s, f) => s + n(f.bruto), 0)
  const haberes = (datos.conceptos ?? []).filter((c) => c.tipo === 'haber')
  const restas = (datos.conceptos ?? []).filter((c) => c.tipo !== 'haber')
  const nota = (v: number) => {
    const p = porcentaje(v, brutoTotal)
    return p === null ? '' : `(${p.toLocaleString('es-PY', { maximumFractionDigits: 1 })} % del bruto)`
  }
  const tarjetas = ['bruto', 'neto', 'aportes_trabajador', 'descuentos', ...(costo ? ['costo_empleador'] : []), 'empleados_liquidados'].map(metricaDe)
  const sinNomina = !datos.filas.some((f) => f.bruto !== undefined)

  return (
    <div className="space-y-4">
      {r ? (
        <div>
          <p className="mb-2 text-sm text-stone-600">Último mes con nómina cerrada: <strong>{mesCorto(String(r.mes.mes), true)}</strong></p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            {tarjetas.map((m) => (
              <Indicador key={m.clave} etiqueta={m.nombre} valor={formatear(valor(r.mes, m), m.formato)}>
                <Variacion actual={valor(r.mes, m) ?? undefined} anterior={valor(r.anterior, m) ?? undefined} etiqueta={`vs ${mesCorto(String(r.anterior.mes))}`} />
                <Variacion actual={valor(r.mes, m) ?? undefined} anterior={valor(r.anio_anterior, m) ?? undefined} etiqueta={`vs ${mesCorto(String(r.anio_anterior.mes))}`} />
              </Indicador>
            ))}
          </div>
        </div>
      ) : <p className="rounded-xl bg-white p-4 text-sm text-stone-500 ring-1 ring-stone-200">Todavía no hay nóminas cerradas con estos filtros.</p>}
      {!sinNomina && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel titulo={costo ? 'Del costo del empleador al neto, por mes' : 'Del bruto al neto, por mes'}
            subtitulo={costo ? 'Neto + IPS del trabajador + descuentos = bruto; más el IPS del empleador = costo total.' : 'Neto + IPS del trabajador + descuentos = bruto.'}
            series={composicion}
            tabla={tablaMeses(datos, [...composicion.map((s) => ({ titulo: s.nombre, valores: s.valores, formato: 'gs' as Formato })),
              { titulo: 'Bruto', valores: serieDe(datos, metricaDe('bruto'), '').valores, formato: 'gs' },
              ...(costo ? [{ titulo: 'Costo total', valores: serieDe(datos, metricaDe('costo_empleador'), '').valores, formato: 'gs' as Formato }] : [])])}>
            <Columnas categorias={categorias} titulos={titulos} series={composicion} formato={formatoDe('gs')} total={costo ? 'Costo total' : 'Bruto'} />
          </Panel>
          <Panel titulo="IPS y descuentos en % del bruto" subtitulo="Qué parte del bruto se va en cada concepto, mes a mes."
            series={porcentajes} tabla={tablaMeses(datos, porcentajes.map((s) => ({ titulo: s.nombre, valores: s.valores, formato: '%' })))}>
            <Lineas categorias={categorias} titulos={titulos} series={porcentajes} formato={formatoDe('%')} formatoEje={ejeDe('%')} />
          </Panel>
          <Panel titulo="Haberes del período" subtitulo={`Total ${guaranies(brutoTotal)} · cada concepto y su parte del bruto.`}
            tabla={{ encabezado: 'Concepto', filas: haberes.map((c) => c.nombre), columnas: [
              { titulo: 'Importe', valores: haberes.map((c) => guaranies(c.total)) },
              { titulo: '% del bruto', valores: haberes.map((c) => formatear(porcentaje(n(c.total), brutoTotal), '%')) }] }}>
            <Barras filas={haberes.map((c) => ({ etiqueta: c.nombre, valores: [n(c.total)], nota: nota(n(c.total)) }))}
              series={[{ nombre: 'Importe', color: SERIES[0] }]} formato={formatoDe('gs')} />
          </Panel>
          <Panel titulo="Descuentos y aportes del período" subtitulo="Lo que se descuenta del bruto (y el aporte del empleador, si podés verlo)."
            tabla={{ encabezado: 'Concepto', filas: restas.map((c) => c.nombre), columnas: [
              { titulo: 'Importe', valores: restas.map((c) => guaranies(c.total)) },
              { titulo: '% del bruto', valores: restas.map((c) => formatear(porcentaje(n(c.total), brutoTotal), '%')) }] }}>
            <Barras filas={restas.map((c) => ({ etiqueta: c.nombre, valores: [n(c.total)], nota: nota(n(c.total)) }))}
              series={[{ nombre: 'Importe', color: SERIES[2] }]} formato={formatoDe('gs')} />
          </Panel>
        </div>
      )}
    </div>
  )
}

function PestanaPersonal({ datos }: { datos: Datos }) {
  const categorias = datos.meses.map((m) => mesCorto(m))
  const titulos = datos.meses.map((m) => mesCorto(m, true))
  const s = datos.secciones
  const altasBajas = [serieDe(datos, metricaDe('altas'), SERIES[0]), serieDe(datos, metricaDe('bajas'), SERIES[1])]
  const una = (clave: string) => [serieDe(datos, metricaDe(clave), SERIES[0])]
  const panel = (clave: string, titulo: string, subtitulo: string, forma: 'lineas' | 'columnas') => {
    const m = metricaDe(clave)
    const series = una(clave)
    const Forma = forma === 'lineas' ? Lineas : Columnas
    return (
      <Panel titulo={titulo} subtitulo={subtitulo} tabla={tablaMeses(datos, [{ titulo: m.nombre, valores: series[0].valores, formato: m.formato }])}>
        <Forma categorias={categorias} titulos={titulos} series={series} formato={formatoDe(m.formato)} formatoEje={ejeDe(m.formato)} enteros={m.formato === 'n'} />
      </Panel>
    )
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {s.personal && panel('dotacion', 'Dotación', 'Empleados activos al cierre de cada mes.', 'lineas')}
      {s.personal && (
        <Panel titulo="Altas y bajas" subtitulo="Ingresos y egresos de cada mes." series={altasBajas}
          tabla={tablaMeses(datos, altasBajas.map((x) => ({ titulo: x.nombre, valores: x.valores, formato: 'n' })))}>
          <Columnas categorias={categorias} titulos={titulos} series={altasBajas} formato={formatoDe('n')} apiladas={false} enteros />
        </Panel>
      )}
      {s.asistencia && panel('ausentismo', 'Ausentismo', 'Días de ausencia sobre los días laborables (presentes, ausentes y licencias).', 'lineas')}
      {s.asistencia && panel('horas_extra', 'Horas extra autorizadas', 'Total de cada mes.', 'columnas')}
      {s.asistencia && panel('horas_tardanza', 'Tardanzas', 'Horas de llegada tarde sumadas en el mes.', 'columnas')}
      {s.asistencia && panel('ausencias', 'Ausencias', 'Días de ausencia sin licencia.', 'columnas')}
    </div>
  )
}

function PestanaLicencias({ datos }: { datos: Datos }) {
  const categorias = datos.meses.map((m) => mesCorto(m))
  const titulos = datos.meses.map((m) => mesCorto(m, true))
  const tipos = datos.licencias_por_tipo ?? []
  const totalDias = tipos.reduce((t, x) => t + n(x.dias), 0)
  const dias = [serieDe(datos, metricaDe('dias_licencia'), SERIES[0])]
  const horas = [serieDe(datos, metricaDe('horas_permiso'), SERIES[0])]
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel titulo="Días de licencia por mes" subtitulo="Licencias aprobadas, en el mes en que empiezan."
        tabla={tablaMeses(datos, [{ titulo: 'Días', valores: dias[0].valores, formato: 'n' }])}>
        <Columnas categorias={categorias} titulos={titulos} series={dias} formato={formatoDe('n')} enteros />
      </Panel>
      <Panel titulo="Permisos por horas" subtitulo="Horas de permiso aprobadas en cada mes."
        tabla={tablaMeses(datos, [{ titulo: 'Horas', valores: horas[0].valores, formato: 'h' }])}>
        <Columnas categorias={categorias} titulos={titulos} series={horas} formato={formatoDe('h')} />
      </Panel>
      <Panel titulo="Por tipo de licencia" subtitulo={`Días del período (${formatear(totalDias, 'n')} en total) y su parte.`} className="lg:col-span-2"
        tabla={{ encabezado: 'Tipo', filas: tipos.map((t) => t.tipo), columnas: [
          { titulo: 'Solicitudes', valores: tipos.map((t) => String(t.solicitudes)) },
          { titulo: 'Días', valores: tipos.map((t) => formatear(n(t.dias), 'n')) },
          { titulo: '% de los días', valores: tipos.map((t) => formatear(porcentaje(n(t.dias), totalDias), '%')) },
          { titulo: 'Horas', valores: tipos.map((t) => formatear(n(t.horas), 'h')) }] }}>
        {tipos.length === 0 ? <p className="text-sm text-stone-500">Sin licencias aprobadas en el período.</p> : (
          <Barras filas={tipos.map((t) => ({
            etiqueta: t.tipo, valores: [n(t.dias)],
            nota: `${totalDias ? `(${formatear(porcentaje(n(t.dias), totalDias), '%')})` : ''} · ${t.solicitudes} solicitud${t.solicitudes === 1 ? '' : 'es'}${n(t.horas) ? ` · ${formatear(n(t.horas), 'h')} h` : ''}`,
          }))} series={[{ nombre: 'Días', color: SERIES[0] }]} formato={formatoDe('n')} />
        )}
      </Panel>
    </div>
  )
}

// ----------------------------------------------------------- comparaciones

function ComparaPeriodos({ metricas, actual, etiquetaA, etiquetaB, a, b, desgloseA, desgloseB }: {
  metricas: Metrica[]; actual: Metrica; etiquetaA: string; etiquetaB: string; a: Datos; b: Datos; desgloseA: Datos; desgloseB: Datos
}) {
  const totalA = a.filas[0]
  const totalB = b.filas[0]
  const series = [{ nombre: `A · ${etiquetaA}`, color: SERIES[0] }, { nombre: `B · ${etiquetaB}`, color: SERIES[1] }]
  const claves = [...new Set([...desgloseA.filas, ...desgloseB.filas].map((f) => f.clave))]
  const porClave = (d: Datos) => Object.fromEntries(d.filas.map((f) => [f.clave, f]))
  const ma = porClave(desgloseA)
  const mb = porClave(desgloseB)
  const filas = claves.map((c) => ({ etiqueta: String((ma[c] ?? mb[c]).etiqueta), valores: [valor(ma[c], actual) ?? 0, valor(mb[c], actual) ?? 0] }))
    .sort((x, y) => y.valores[0] - x.valores[0])
  const sinPromedio = (m: Metrica) => m.clave === 'dotacion' ? ' (al cierre)' : ''
  return (
    <div className="grid gap-4 2xl:grid-cols-2">
      <section className="min-w-0 rounded-xl bg-white p-4 ring-1 ring-stone-200">
        <h2 className="mb-2 font-semibold text-stone-900">Período A contra período B</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-max text-sm">
            <thead className="text-left text-xs text-stone-500">
              <tr><th className="py-1 pr-2">Indicador</th><th className="px-2 py-1 text-right">A · {etiquetaA}</th><th className="px-2 py-1 text-right">B · {etiquetaB}</th>
                <th className="px-2 py-1 text-right">Diferencia</th><th className="py-1 pl-2 text-right">Variación</th></tr>
            </thead>
            <tbody>
              {metricas.map((m) => {
                const va = valor(totalA, m)
                const vb = valor(totalB, m)
                const dif = va !== null && vb !== null ? va - vb : null
                const variacion = dif !== null && vb ? (dif / Math.abs(vb)) * 100 : null
                return (
                  <tr key={m.clave} className={`border-t border-stone-100 ${m.clave === actual.clave ? 'bg-stone-50 font-medium' : ''}`}>
                    <td className="py-1 pr-2 text-stone-700">{m.nombre}{sinPromedio(m)}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{formatear(va, m.formato)}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{formatear(vb, m.formato)}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{dif === null ? '—' : `${dif > 0 ? '+' : ''}${formatear(dif, m.formato === '%' ? 'n' : m.formato)}${m.formato === '%' ? ' pp' : ''}`}</td>
                    <td className="py-1 pl-2 text-right tabular-nums">{m.formato === '%' || variacion === null ? '—' : `${variacion > 0 ? '+' : ''}${variacion.toLocaleString('es-PY', { maximumFractionDigits: 1 })} %`}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-stone-500">Montos sumados en cada período; los porcentajes se calculan sobre el total del período (pp = puntos porcentuales).</p>
      </section>
      <Panel titulo={`${actual.nombre}: A contra B`} subtitulo="Desglose de cada período." series={series}
        tabla={{ encabezado: 'Grupo', filas: filas.map((f) => f.etiqueta), columnas: [
          { titulo: 'A', valores: filas.map((f) => formatear(f.valores[0], actual.formato)) },
          { titulo: 'B', valores: filas.map((f) => formatear(f.valores[1], actual.formato)) }] }}>
        {filas.length === 0 ? <p className="text-sm text-stone-500">Sin datos.</p> : <Barras filas={filas} series={series} formato={formatoDe(actual.formato)} />}
      </Panel>
    </div>
  )
}

function ComparaGrupos({ datos, metricas, actual, titulo, elegidos }: { datos: Datos; metricas: Metrica[]; actual: Metrica; titulo: string; elegidos: number[] }) {
  // Sin dato del indicador en el rango (ej. alguien que ya no estaba) no entra en la comparación.
  const filas = datos.filas.filter((f) => valor(f, actual) !== null).sort((x, y) => (valor(y, actual) ?? 0) - (valor(x, actual) ?? 0))
  const total = filas.reduce((t, f) => t + (valor(f, actual) ?? 0), 0)
  // Líneas: los empleados elegidos (en el orden en que se eligieron) o los primeros del ranking.
  // El color queda atado a cada grupo (por su posición en esa lista), no a su lugar en el ranking.
  const enLineas = (elegidos.length ? elegidos.map((id) => datos.filas.find((f) => f.clave === String(id))).filter(Boolean) as FilaConMeses[]
    : filas.slice(0, MAXIMO_LINEAS).sort((x, y) => x.etiqueta.localeCompare(y.etiqueta))).slice(0, MAXIMO_LINEAS)
  const series: Serie[] = enLineas.map((f, i) => ({ nombre: f.etiqueta, color: SERIES[i], valores: (f.meses ?? []).map((m) => valor(m, actual)) }))
  const categorias = datos.meses.map((m) => mesCorto(m))
  const titulos = datos.meses.map((m) => mesCorto(m, true))
  const columnasDetalle = metricas.filter((m) => ['bruto', 'neto', 'aportes_trabajador', 'descuentos', 'costo_empleador', 'descuentos_pct',
    'dias_licencia', 'ausentismo', 'horas_extra', 'dotacion'].includes(m.clave))
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel titulo={`${actual.nombre} por ${titulo.toLowerCase()}`}
          subtitulo={actual.suma ? 'Total del rango y su parte sobre el total.' : actual.clave === 'dotacion' ? 'Al cierre del rango.' : 'Sobre el total del rango.'}
          tabla={{ encabezado: titulo, filas: filas.map((f) => f.etiqueta), columnas: [
            { titulo: actual.nombre, valores: filas.map((f) => formatear(valor(f, actual), actual.formato)) },
            ...(actual.suma ? [{ titulo: '% del total', valores: filas.map((f) => formatear(porcentaje(valor(f, actual) ?? 0, total), '%')) }] : [])] }}>
          {filas.length === 0 ? <p className="text-sm text-stone-500">Sin datos.</p> : (
            <Barras filas={filas.map((f) => ({
              etiqueta: f.etiqueta, valores: [valor(f, actual) ?? 0],
              nota: actual.suma && total ? `(${formatear(porcentaje(valor(f, actual) ?? 0, total), '%')})` : undefined,
            }))} series={[{ nombre: actual.nombre, color: SERIES[0] }]} formato={formatoDe(actual.formato)} />
          )}
        </Panel>
        <Panel titulo={`${actual.nombre}, mes a mes`}
          subtitulo={elegidos.length ? 'Empleados elegidos en el filtro.' : `Los ${Math.min(MAXIMO_LINEAS, filas.length)} primeros del ranking (elegí empleados en el filtro para ver otros).`}
          series={series} tabla={{ encabezado: 'Mes', filas: titulos, columnas: series.map((s) => ({ titulo: s.nombre, valores: s.valores.map((v) => formatear(v, actual.formato)) })) }}>
          <Lineas categorias={categorias} titulos={titulos} series={series} formato={formatoDe(actual.formato)} formatoEje={ejeDe(actual.formato)} enteros={actual.formato === 'n'} />
        </Panel>
      </div>
      <section className="min-w-0 rounded-xl bg-white p-4 ring-1 ring-stone-200">
        <h2 className="mb-2 font-semibold text-stone-900">Detalle por {titulo.toLowerCase()}</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-max text-sm">
            <thead className="text-left text-xs text-stone-500">
              <tr><th className="py-1 pr-2">{titulo}</th>{columnasDetalle.map((m) => <th key={m.clave} className="px-2 py-1 text-right">{m.nombre}</th>)}</tr>
            </thead>
            <tbody>
              {filas.map((f) => (
                <tr key={f.clave} className="border-t border-stone-100">
                  <td className="py-1 pr-2 text-stone-700">{f.etiqueta}</td>
                  {columnasDetalle.map((m) => <td key={m.clave} className="px-2 py-1 text-right tabular-nums">{formatear(valor(f, m), m.formato)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
