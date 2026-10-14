import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ChevronLeft, Plus, Search } from 'lucide-react'
import api from '../services/api'
import CampoFecha from '../components/CampoFecha'
import { buscarModulo } from '../modulos'
import { valorVisible } from '../formato'
import { puedeCrear, puedeVer } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Paginado, Registro } from '../tipos'

const POR_PAGINA = 25

/** Listado genérico de un módulo (ver modulos.ts): búsqueda, filtros,
 * paginación y acceso al formulario de cada registro. */
export default function Listado() {
  const { clave } = useParams()
  const modulo = buscarModulo(clave)
  const { usuario } = useSesion()
  const navegar = useNavigate()
  const ubicacion = useLocation()
  const [parametros] = useSearchParams()
  const mensaje = (ubicacion.state as { mensaje?: string } | null)?.mensaje

  const [buscar, setBuscar] = useState('')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [pagina, setPagina] = useState(1)
  const [sucursal, setSucursal] = useState('')
  const [filtros, setFiltros] = useState<Record<string, string>>({})
  const [sucursales, setSucursales] = useState<Registro[]>([])
  const [datos, setDatos] = useState<Paginado<Registro> | null>(null)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const filtraSucursal = Boolean(modulo?.filtroSucursal)

  useEffect(() => {
    if (!filtraSucursal) return
    api.get<Paginado<Registro>>('/sucursales/', { params: { por_pagina: 200 } })
      .then((r) => setSucursales(r.data.results))
      .catch(() => setSucursales([]))
  }, [filtraSucursal])

  // Al cambiar de módulo se arranca de cero (con los filtros que vengan en la dirección, ej. ?estado=activo).
  useEffect(() => {
    setBuscar('')
    setDesde('')
    setHasta('')
    setSucursal('')
    setPagina(1)
    setDatos(null)
    const iniciales: Record<string, string> = {}
    for (const f of buscarModulo(clave)?.filtrosLista ?? []) {
      const v = parametros.get(f.nombre)
      if (v) iniciales[f.nombre] = v
    }
    setFiltros(iniciales)
  }, [clave, parametros])

  useEffect(() => {
    if (!modulo) return
    const temporizador = window.setTimeout(() => {
      setCargando(true)
      setError(null)
      const params: Record<string, string | number> = { page: pagina, por_pagina: POR_PAGINA }
      if (buscar.trim()) params.buscar = buscar.trim()
      if (desde) params.desde = desde
      if (hasta) params.hasta = hasta
      if (sucursal) params.sucursal = sucursal
      for (const [k, v] of Object.entries(filtros)) if (v) params[k] = v
      api.get<Paginado<Registro>>(`/${modulo.endpoint}/`, { params })
        .then((r) => setDatos(r.data))
        .catch(() => setError('No se pudieron cargar los registros.'))
        .finally(() => setCargando(false))
    }, 250)
    return () => window.clearTimeout(temporizador)
  }, [modulo, buscar, desde, hasta, sucursal, filtros, pagina])

  if (!modulo || !puedeVer(usuario, modulo)) {
    return <p className="rounded-xl bg-white p-6">Esta sección no existe o no tenés acceso. <Link to="/" className="underline">Volver al panel</Link></p>
  }

  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.count / POR_PAGINA)) : 1
  const campoDe = (nombre: string) => modulo.campos.find((c) => c.nombre === nombre)

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Link to="/" aria-label="Volver al panel" className="rounded-md p-1 text-stone-500 hover:bg-stone-100">
            <ChevronLeft />
          </Link>
          <h1 className="text-xl font-bold text-stone-900 sm:text-2xl">{modulo.titulo}</h1>
        </div>
        {puedeCrear(usuario, modulo) && (
          <Link to={modulo.rutaNuevo ?? `/m/${modulo.clave}/nuevo`}
            className="flex items-center gap-1 rounded-lg bg-marca-700 px-4 py-2 text-sm font-medium text-white hover:bg-marca-600">
            <Plus size={18} /> Nuevo
          </Link>
        )}
      </div>

      {mensaje && <p className="mb-4 rounded-lg bg-marca-50 px-3 py-2 text-sm text-marca-900">{mensaje}</p>}

      <div className="mb-4 flex flex-wrap gap-2">
        <label className="relative min-w-[12rem] flex-1">
          <Search size={16} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400" />
          <input type="search" placeholder="Buscar…" value={buscar}
            onChange={(e) => { setBuscar(e.target.value); setPagina(1) }}
            className="w-full rounded-lg border border-stone-300 p-2 pl-8 focus:outline-none focus:ring-2 focus:ring-marca-600" />
        </label>
        {modulo.filtrosLista?.map((f) => (
          <label key={f.nombre} className="flex items-center gap-2 text-sm text-stone-600">
            {f.etiqueta}
            <select value={filtros[f.nombre] ?? ''} onChange={(e) => { setFiltros((v) => ({ ...v, [f.nombre]: e.target.value })); setPagina(1) }}
              className="rounded-lg border border-stone-300 p-2">
              <option value="">Todos</option>
              {f.opciones.map((o) => <option key={o.valor} value={o.valor}>{o.texto}</option>)}
            </select>
          </label>
        ))}
        {filtraSucursal && sucursales.length > 1 && (
          <label className="flex items-center gap-2 text-sm text-stone-600">
            Sucursal
            <select value={sucursal} onChange={(e) => { setSucursal(e.target.value); setPagina(1) }}
              className="rounded-lg border border-stone-300 p-2">
              <option value="">Todas</option>
              {sucursales.map((s) => <option key={s.id} value={s.id}>{String(s.nombre)}</option>)}
            </select>
          </label>
        )}
        {modulo.campoFecha && (
          <>
            <label className="flex items-center gap-2 text-sm text-stone-600">
              Desde
              <CampoFecha valor={desde} onCambio={(v) => { setDesde(v); setPagina(1) }} className="w-40" aria-label="Desde" />
            </label>
            <label className="flex items-center gap-2 text-sm text-stone-600">
              Hasta
              <CampoFecha valor={hasta} onCambio={(v) => { setHasta(v); setPagina(1) }} className="w-40" aria-label="Hasta" />
            </label>
          </>
        )}
      </div>

      {error && <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}

      <div className="overflow-x-auto rounded-lg border border-stone-200">
        <table className="w-full min-w-max text-sm">
          <thead className="bg-marca-50 text-left text-stone-700">
            <tr>{modulo.columnas.map((c) => <th key={c.campo} className="px-3 py-2 font-semibold">{c.etiqueta}</th>)}</tr>
          </thead>
          <tbody>
            {datos?.results.map((r) => (
              <tr key={r.id} onClick={() => navegar(modulo.rutaDetalle ? modulo.rutaDetalle(r.id) : `/m/${modulo.clave}/${r.id}`)}
                className={`cursor-pointer border-t border-stone-100 hover:bg-marca-50/60 ${modulo.colorFila?.(r) ?? ''}`}>
                {modulo.columnas.map((c) => (
                  <td key={c.campo} className="max-w-xs truncate px-3 py-2">{valorVisible(r, c.campo, campoDe(c.campo))}</td>
                ))}
              </tr>
            ))}
            {datos && datos.results.length === 0 && (
              <tr><td colSpan={modulo.columnas.length} className="px-3 py-6 text-center text-stone-500">No hay registros.</td></tr>
            )}
            {!datos && cargando && (
              <tr><td colSpan={modulo.columnas.length} className="px-3 py-6 text-center text-stone-500">Cargando…</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {datos && datos.count > 0 && (
        <div className="mt-3 flex items-center justify-between text-sm text-stone-600">
          <span>{datos.count} registro{datos.count === 1 ? '' : 's'}</span>
          <div className="flex items-center gap-2">
            <button type="button" disabled={!datos.previous} onClick={() => setPagina((p) => p - 1)}
              className="rounded-md border border-stone-300 px-3 py-1 disabled:opacity-40">Anterior</button>
            <span>{pagina} / {totalPaginas}</span>
            <button type="button" disabled={!datos.next} onClick={() => setPagina((p) => p + 1)}
              className="rounded-md border border-stone-300 px-3 py-1 disabled:opacity-40">Siguiente</button>
          </div>
        </div>
      )}
    </div>
  )
}
