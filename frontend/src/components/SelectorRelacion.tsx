import { useEffect, useRef, useState } from 'react'
import { Plus, X } from 'lucide-react'
import api from '../services/api'
import { buscarModulo } from '../modulos'
import type { Paginado, Registro } from '../tipos'

interface Props {
  id: string
  modulo: string
  valor: number | null
  texto: string
  invalido?: boolean
  /** Filtros fijos que se mandan a la API (ej. { admite_animales: 'true' }). */
  filtros?: Record<string, string>
  /** Sin el botón "+ Nueva" (ej. el supervisor de un empleado). */
  sinNueva?: boolean
  onCambio: (id: number | null, texto: string) => void
}

/** Campo para elegir un registro relacionado (persona, galpón, corral...)
 * buscando por texto contra la API, en vez de un desplegable con todo: la
 * agenda de personas puede tener cientos de filas. */
export default function SelectorRelacion({ id, modulo, valor, texto, invalido, filtros, sinNueva, onCambio }: Props) {
  const destino = buscarModulo(modulo)
  const [busqueda, setBusqueda] = useState('')
  const [abierto, setAbierto] = useState(false)
  const [resultados, setResultados] = useState<Registro[]>([])
  const [buscando, setBuscando] = useState(false)
  const contenedor = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!abierto || !destino) return
    const temporizador = window.setTimeout(() => {
      setBuscando(true)
      api.get<Paginado<Registro>>(`/${destino.endpoint}/`, { params: { ...filtros, buscar: busqueda, por_pagina: 15 } })
        .then((r) => setResultados(r.data.results))
        .catch(() => setResultados([]))
        .finally(() => setBuscando(false))
    }, 250)
    return () => window.clearTimeout(temporizador)
  }, [busqueda, abierto, destino, filtros])

  // Cierra la lista al tocar fuera del campo.
  useEffect(() => {
    const cerrar = (e: MouseEvent) => {
      if (contenedor.current && !contenedor.current.contains(e.target as Node)) setAbierto(false)
    }
    document.addEventListener('mousedown', cerrar)
    return () => document.removeEventListener('mousedown', cerrar)
  }, [])

  if (!destino) return <p className="text-sm text-red-700">Módulo relacionado desconocido: {modulo}</p>

  const elegir = (registro: Registro) => {
    onCambio(registro.id, textoDe(registro))
    setAbierto(false)
    setBusqueda('')
  }

  return (
    <div ref={contenedor} className="relative">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            id={id}
            type="text"
            autoComplete="off"
            value={abierto ? busqueda : texto}
            placeholder={valor ? '' : `Buscar ${destino.singular}…`}
            onFocus={() => setAbierto(true)}
            onChange={(e) => setBusqueda(e.target.value)}
            className={`w-full rounded-lg border bg-white p-2 pr-8 focus:outline-none focus:ring-2 focus:ring-marca-600 ${invalido ? 'border-red-500' : 'border-stone-300'}`}
          />
          {valor !== null && !abierto && (
            <button
              type="button"
              aria-label="Quitar"
              onClick={() => onCambio(null, '')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-700"
            >
              <X size={16} />
            </button>
          )}
        </div>
        {!sinNueva && (
          <a
            href={`/m/${destino.clave}/nuevo`}
            target="_blank"
            rel="noreferrer"
            title={`Cargar ${destino.singular} nuevo (se abre en otra pestaña)`}
            className="flex items-center gap-1 rounded-lg border border-stone-300 bg-white px-2 text-sm text-marca-800 hover:bg-stone-50"
          >
            <Plus size={16} /> Nueva
          </a>
        )}
      </div>

      {abierto && (
        <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-stone-200 bg-white shadow-lg">
          {buscando && <li className="px-3 py-2 text-sm text-stone-500">Buscando…</li>}
          {!buscando && resultados.length === 0 && (
            <li className="px-3 py-2 text-sm text-stone-500">Sin resultados.</li>
          )}
          {!buscando && resultados.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => elegir(r)}
                className={`block w-full px-3 py-2 text-left text-sm hover:bg-marca-50 ${r.id === valor ? 'font-semibold text-marca-800' : ''}`}
              >
                {textoDe(r)}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Texto legible del registro: el campo `texto` que agrega la API (es el
 * mismo __str__ que se ve en el admin de Django). */
function textoDe(r: Registro): string {
  return String(r.texto ?? r.id)
}
