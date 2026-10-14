import { useEffect, useMemo, useState, type ReactNode } from 'react'
import api from '../services/api'
import { buscarModulo } from '../modulos'
import CampoFecha from './CampoFecha'
import EditorFilas from './EditorFilas'
import { aEntradaFechaHora } from '../formato'
import SelectorRelacion from './SelectorRelacion'
import type { Campo, Opcion, Paginado, Registro } from '../tipos'

interface Props {
  campo: Campo
  valores: Record<string, unknown>
  error?: string
  esNuevo: boolean
  onCambio: (cambios: Record<string, unknown>) => void
}

const claseInput = (invalido: boolean) =>
  `w-full rounded-lg border bg-white p-2 focus:outline-none focus:ring-2 focus:ring-marca-600 disabled:bg-stone-50 ${invalido ? 'border-red-500' : 'border-stone-300'}`

/** Casillas para elegir varias opciones; `valor` es la lista elegida. */
function Casillas({ id, opciones, valor, onCambio }: { id: string; opciones: Opcion[]; valor: string[]; onCambio: (v: string[]) => void }) {
  if (opciones.length === 0) return <p className="text-sm text-stone-500">No hay opciones para elegir.</p>
  return (
    <div id={id} className="flex flex-wrap gap-x-5 gap-y-2 rounded-lg border border-stone-300 bg-white p-2">
      {opciones.map((o) => (
        <label key={o.valor} className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4 accent-marca-700" checked={valor.includes(o.valor)}
            onChange={(e) => onCambio(e.target.checked ? [...valor, o.valor] : valor.filter((v) => v !== o.valor))} />
          {o.texto}
        </label>
      ))}
    </div>
  )
}

/** Varios registros de otro módulo (ej. sucursales), con casillas. */
function RelacionMultiple({ id, modulo, valor, onCambio }: { id: string; modulo: string; valor: number[]; onCambio: (v: number[]) => void }) {
  const destino = buscarModulo(modulo)
  const [opciones, setOpciones] = useState<Opcion[]>([])
  useEffect(() => {
    if (!destino) return
    api.get<Paginado<Registro>>(`/${destino.endpoint}/`, { params: { por_pagina: 200 } })
      .then((r) => setOpciones(r.data.results.map((x) => ({ valor: String(x.id), texto: String(x.texto ?? x.id) }))))
      .catch(() => setOpciones([]))
  }, [destino])
  return (
    <Casillas id={id} opciones={opciones} valor={valor.map(String)} onCambio={(v) => onCambio(v.map(Number))} />
  )
}

export default function CampoFormulario({ campo, valores, error, esNuevo, onCambio }: Props) {
  const id = `campo-${campo.nombre}`
  const valor = valores[campo.nombre]
  const texto = valor === null || valor === undefined ? '' : String(valor)
  const invalido = Boolean(error)
  const cambiar = (v: unknown) => onCambio({ [campo.nombre]: v })
  const requerido = campo.requerido || (esNuevo && campo.requeridoAlCrear)
  // Filtros fijos + los que toman el valor de otro campo (memorizados por su
  // contenido: un objeto nuevo en cada dibujo haría buscar sin fin).
  const dependencias = Object.entries(campo.filtrosDe ?? {}).map(([p, c]) => [p, valores[c]] as const)
  const faltaDependencia = dependencias.some(([, v]) => v === null || v === undefined || v === '')
  const claveFiltros = JSON.stringify({ ...campo.filtros, ...Object.fromEntries(dependencias.map(([p, v]) => [p, String(v ?? '')])) })
  const filtros = useMemo(() => JSON.parse(claveFiltros) as Record<string, string>, [claveFiltros])

  if (campo.soloLectura) {
    return (
      <div>
        <p className="mb-1 block text-sm font-medium text-stone-800">{campo.etiqueta}</p>
        <p className="rounded-lg border border-stone-200 bg-stone-50 p-2 text-stone-700">{texto || '—'}</p>
      </div>
    )
  }

  if (campo.tipo === 'filas') {
    return <EditorFilas campo={campo} valor={valor} error={error} onCambio={cambiar} />
  }

  if (campo.tipo === 'booleano') {
    return (
      <div className="sm:col-span-2">
        <label htmlFor={id} className="flex items-center gap-2 text-sm font-medium text-stone-800">
          <input id={id} type="checkbox" checked={valor === true} onChange={(e) => cambiar(e.target.checked)}
            className="h-5 w-5 accent-marca-700" />
          {campo.etiqueta}
        </label>
        {error && <p className="mt-1 text-sm text-red-700">{error}</p>}
      </div>
    )
  }

  let control: ReactNode
  switch (campo.tipo) {
    case 'textoLargo':
      control = <textarea id={id} rows={3} value={texto} onChange={(e) => cambiar(e.target.value)} className={claseInput(invalido)} />
      break
    case 'entero':
      control = <input id={id} type="number" inputMode="numeric" step="1" value={texto} onChange={(e) => cambiar(e.target.value)} className={claseInput(invalido)} />
      break
    case 'decimal':
      control = <input id={id} type="number" inputMode="decimal" step="any" value={texto} onChange={(e) => cambiar(e.target.value)} className={claseInput(invalido)} />
      break
    case 'fecha':
      control = <CampoFecha id={id} valor={texto} onCambio={cambiar} invalido={invalido} />
      break
    case 'fechaHora':
      control = <input id={id} type="datetime-local" value={aEntradaFechaHora(valor)} onChange={(e) => cambiar(e.target.value)} className={claseInput(invalido)} />
      break
    case 'hora':
      control = <input id={id} type="time" value={texto.slice(0, 5)} onChange={(e) => cambiar(e.target.value)} className={claseInput(invalido)} />
      break
    case 'correo':
      control = <input id={id} type="email" value={texto} onChange={(e) => cambiar(e.target.value)} className={claseInput(invalido)} />
      break
    case 'clave':
      control = <input id={id} type="password" autoComplete="new-password" value={texto} onChange={(e) => cambiar(e.target.value)}
        placeholder={esNuevo ? '' : 'Sin cambios'} className={claseInput(invalido)} />
      break
    case 'opciones':
      control = (
        <select id={id} value={texto} onChange={(e) => cambiar(e.target.value)} className={claseInput(invalido)}>
          {!campo.requerido && <option value="">— Sin especificar —</option>}
          {campo.opciones?.map((o) => <option key={o.valor} value={o.valor}>{o.texto}</option>)}
        </select>
      )
      break
    case 'color': {
      const valido = /^#[0-9a-f]{6}$/i.test(texto)
      control = (
        <div className="flex items-center gap-2">
          <input id={id} type="color" value={valido ? texto : String(campo.porDefecto ?? '#E9264B')}
            onChange={(e) => cambiar(e.target.value.toUpperCase())}
            className={`h-10 w-14 cursor-pointer rounded-lg border bg-white p-1 ${invalido ? 'border-red-500' : 'border-stone-300'}`} />
          <span className="font-mono text-sm text-stone-600">{valido ? texto.toUpperCase() : 'el de Koape'}</span>
          {valido && (
            <button type="button" onClick={() => cambiar('')} className="text-xs text-stone-500 underline hover:text-stone-800">
              Volver al de Koape
            </button>
          )}
        </div>
      )
      break
    }
    case 'seleccionMultiple':
      control = <Casillas id={id} opciones={campo.opciones ?? []} valor={Array.isArray(valor) ? valor.map(String) : []} onCambio={cambiar} />
      break
    case 'relacionMultiple':
      control = <RelacionMultiple id={id} modulo={campo.relacion ?? ''} valor={Array.isArray(valor) ? valor.map(Number) : []} onCambio={cambiar} />
      break
    case 'archivo':
      control = (
        <input id={id} type="file" accept="application/pdf,image/jpeg,image/png,image/webp"
          onChange={(e) => cambiar(e.target.files?.[0] ?? null)}
          className={`${claseInput(invalido)} file:mr-3 file:rounded-md file:border-0 file:bg-marca-50 file:px-3 file:py-1 file:text-marca-900`} />
      )
      break
    case 'relacion':
      if (faltaDependencia) {
        control = <input id={id} type="text" disabled placeholder={`Elegí primero: ${Object.values(campo.filtrosDe ?? {}).join(', ')}`}
          className={claseInput(invalido)} />
        break
      }
      control = (
        <SelectorRelacion
          id={id}
          modulo={campo.relacion ?? ''}
          filtros={filtros}
          sinNueva={campo.sinNueva}
          valor={typeof valor === 'number' ? valor : null}
          texto={String(valores[`${campo.nombre}_texto`] ?? '')}
          invalido={invalido}
          onCambio={(nuevoId, nuevoTexto) => onCambio({ [campo.nombre]: nuevoId, [`${campo.nombre}_texto`]: nuevoTexto })}
        />
      )
      break
    default:
      control = <input id={id} type="text" value={texto} maxLength={campo.maxLength}
        onChange={(e) => cambiar(e.target.value)} className={claseInput(invalido)} />
  }

  return (
    <div className={['textoLargo', 'seleccionMultiple', 'relacionMultiple'].includes(campo.tipo) ? 'sm:col-span-2' : ''}>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-stone-800">
        {campo.etiqueta}{requerido && <span className="text-red-700"> *</span>}
      </label>
      {control}
      {campo.ayuda && !error && <p className="mt-1 text-xs text-stone-500">{campo.ayuda}</p>}
      {error && <p className="mt-1 text-sm text-red-700">{error}</p>}
    </div>
  )
}
