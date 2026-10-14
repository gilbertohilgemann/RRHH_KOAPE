import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { ChevronLeft, Eye, FileUp } from 'lucide-react'
import api from '../services/api'
import CampoFecha from '../components/CampoFecha'
import { mensajeDeError } from '../formato'
import type { Paginado, Registro } from '../tipos'

interface VistaPrevia { encabezado: string[]; tiene_encabezado: boolean; filas: { fila: number; columnas: string[] }[]; total_filas: number }

const claseCampo = 'w-full rounded-lg border border-stone-300 bg-white p-2 focus:outline-none focus:ring-2 focus:ring-marca-600'

/** Importar un archivo CSV de marcaciones: elegir perfil (y reloj), ver las
 * primeras filas tal cual vienen, y validar. Validar NO crea marcas: deja el
 * archivo en revisión; las marcas se crean al confirmar en la pantalla
 * siguiente. */
export default function ImportarMarcaciones() {
  const navegar = useNavigate()
  const [perfiles, setPerfiles] = useState<Registro[]>([])
  const [relojes, setRelojes] = useState<Registro[]>([])
  const [perfil, setPerfil] = useState('')
  const [reloj, setReloj] = useState('')
  const [archivo, setArchivo] = useState<File | null>(null)
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [notas, setNotas] = useState('')
  const [vista, setVista] = useState<VistaPrevia | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [trabajando, setTrabajando] = useState(false)

  useEffect(() => {
    api.get<Paginado<Registro>>('/perfiles-importacion/', { params: { activo: true, por_pagina: 100 } }).then((r) => setPerfiles(r.data.results)).catch(() => undefined)
    api.get<Paginado<Registro>>('/relojes-externos/', { params: { activo: true, por_pagina: 100 } }).then((r) => setRelojes(r.data.results)).catch(() => undefined)
  }, [])

  const perfilElegido = perfiles.find((p) => String(p.id) === perfil)
  const pideReloj = perfilElegido?.identificador === 'codigo_reloj'

  // Al elegir un reloj con perfil habitual, se propone ese perfil.
  const elegirReloj = (id: string) => {
    setReloj(id)
    const habitual = relojes.find((r) => String(r.id) === id)?.perfil_importacion
    if (habitual && !perfil) setPerfil(String(habitual))
  }

  const errorDe = (err: unknown, porDefecto: string) => {
    const datos = axios.isAxiosError(err) ? err.response?.data : null
    if (datos && typeof datos === 'object') {
      const primero = Object.values(datos as Record<string, unknown>).find((v) => Array.isArray(v))
      if (Array.isArray(primero)) return String(primero[0])
    }
    return mensajeDeError(datos, porDefecto)
  }

  const verPrevia = async () => {
    if (!archivo) return
    setError(null)
    setTrabajando(true)
    const datos = new FormData()
    datos.append('archivo', archivo)
    if (perfil) datos.append('perfil', perfil)
    try {
      setVista((await api.post<VistaPrevia>('/importaciones/vista_previa/', datos)).data)
    } catch (err) {
      setVista(null)
      setError(errorDe(err, 'No se pudo leer el archivo.'))
    } finally {
      setTrabajando(false)
    }
  }

  const validar = async (e: FormEvent) => {
    e.preventDefault()
    if (!archivo || !perfil) return
    setError(null)
    setTrabajando(true)
    const datos = new FormData()
    datos.append('archivo', archivo)
    datos.append('perfil', perfil)
    if (reloj) datos.append('reloj', reloj)
    if (desde) datos.append('periodo_desde', desde)
    if (hasta) datos.append('periodo_hasta', hasta)
    if (notas) datos.append('notas', notas)
    try {
      const r = await api.post<Registro>('/importaciones/', datos)
      navegar(`/asistencia/importaciones/${r.data.id}`)
    } catch (err) {
      setError(errorDe(err, 'No se pudo validar el archivo.'))
    } finally {
      setTrabajando(false)
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <div className="mb-4 flex items-center gap-2">
          <Link to="/m/importaciones" aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100"><ChevronLeft /></Link>
          <h1 className="text-xl font-bold text-stone-900 sm:text-2xl">Importar marcaciones</h1>
        </div>
        <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Las marcas de un archivo no se verifican en persona: el archivo es la fuente que entregás vos. Igual se validan el formato,
          los códigos, las fechas y los duplicados, y queda registrado quién lo subió.
        </p>
        <form onSubmit={validar} className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-stone-800">Reloj {pideReloj && <span className="text-red-700">*</span>}
            <select value={reloj} onChange={(e) => elegirReloj(e.target.value)} className={`mt-1 ${claseCampo}`}>
              <option value="">— Sin reloj (archivo con formato de Koape) —</option>
              {relojes.map((r) => <option key={r.id} value={r.id}>{String(r.texto)}</option>)}
            </select>
          </label>
          <label className="block text-sm font-medium text-stone-800">Perfil de importación <span className="text-red-700">*</span>
            <select value={perfil} onChange={(e) => { setPerfil(e.target.value); setVista(null) }} required className={`mt-1 ${claseCampo}`}>
              <option value="">— Elegí un perfil —</option>
              {perfiles.map((p) => <option key={p.id} value={p.id}>{String(p.texto)}</option>)}
            </select>
            {perfiles.length === 0 && <span className="mt-1 block text-xs text-stone-500">No hay perfiles: creá uno en Asistencia → Perfiles de importación.</span>}
          </label>
          <label className="block text-sm font-medium text-stone-800 sm:col-span-2">Archivo CSV <span className="text-red-700">*</span>
            <input type="file" accept=".csv,.txt,text/csv,text/plain" required onChange={(e) => { setArchivo(e.target.files?.[0] ?? null); setVista(null) }}
              className={`mt-1 ${claseCampo} file:mr-3 file:rounded-md file:border-0 file:bg-marca-50 file:px-3 file:py-1 file:text-marca-900`} />
          </label>
          <label className="block text-sm font-medium text-stone-800">Período desde (opcional)
            <CampoFecha valor={desde} onCambio={setDesde} className="mt-1" />
          </label>
          <label className="block text-sm font-medium text-stone-800">Hasta (opcional)
            <CampoFecha valor={hasta} onCambio={setHasta} className="mt-1" />
          </label>
          <label className="block text-sm font-medium text-stone-800 sm:col-span-2">Notas
            <input value={notas} onChange={(e) => setNotas(e.target.value)} maxLength={500} className={`mt-1 ${claseCampo}`}
              placeholder="Ej. marcas de la primera quincena de marzo" />
          </label>
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 sm:col-span-2">{error}</p>}
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            <button type="button" onClick={verPrevia} disabled={!archivo || trabajando}
              className="flex items-center gap-1 rounded-lg border border-marca-700 px-4 py-2 text-sm font-medium text-marca-800 hover:bg-marca-50 disabled:opacity-50">
              <Eye size={16} /> Vista previa
            </button>
            <button type="submit" disabled={!archivo || !perfil || (pideReloj && !reloj) || trabajando}
              className="flex items-center gap-1 rounded-lg bg-marca-700 px-4 py-2 text-sm font-medium text-white hover:bg-marca-600 disabled:opacity-50">
              <FileUp size={16} /> {trabajando ? 'Procesando…' : 'Validar archivo'}
            </button>
          </div>
        </form>
      </div>

      {vista && (
        <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
          <h2 className="mb-1 font-semibold text-stone-800">Vista previa ({vista.total_filas} filas)</h2>
          <p className="mb-3 text-sm text-stone-500">
            Así se lee el archivo con {perfilElegido ? `el perfil "${String(perfilElegido.texto)}"` : 'punto y coma y UTF-8'}. En el perfil, cada
            columna se indica por su nombre (encabezado) o por su número.
          </p>
          <div className="overflow-x-auto rounded-lg border border-stone-200">
            <table className="w-full min-w-max text-sm">
              <thead className="bg-marca-50 text-left text-stone-700">
                <tr>
                  <th className="px-2 py-1.5">Fila</th>
                  {vista.encabezado.map((c, i) => <th key={i} className="px-2 py-1.5">{i + 1}. {vista.tiene_encabezado ? c : ''}</th>)}
                </tr>
              </thead>
              <tbody>
                {vista.filas.map((f) => (
                  <tr key={f.fila} className="border-t border-stone-100">
                    <td className="px-2 py-1 text-stone-500">{f.fila}</td>
                    {f.columnas.map((c, i) => <td key={i} className="px-2 py-1 font-mono text-xs">{c}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
