import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus } from 'lucide-react'
import api from '../services/api'
import { MODULOS } from '../modulos'
import { valorVisible } from '../formato'
import { puedeCrear, puedeVer } from '../permisos'
import { useSesion } from '../services/sesionContexto'
import type { Modulo, Paginado, Registro } from '../tipos'

/** Una sección del legajo: los registros de un módulo (contratos, sueldos,
 * documentos, cuentas) de este empleado, con acceso a cada uno y a cargar
 * uno nuevo ya con el empleado elegido. */
function Seccion({ modulo, empleado, volver, soloVer }: { modulo: Modulo; empleado: Registro; volver: string; soloVer?: boolean }) {
  const { usuario } = useSesion()
  const [filas, setFilas] = useState<Registro[] | null>(null)
  const columnas = modulo.columnas.filter((c) => c.campo !== 'empleado')

  useEffect(() => {
    api.get<Paginado<Registro>>(`/${modulo.endpoint}/`, { params: { empleado: empleado.id, por_pagina: 50 } })
      .then((r) => setFilas(r.data.results))
      .catch(() => setFilas([]))
  }, [modulo, empleado.id, empleado.modificado])

  const conVolver = (ruta: string) => `${ruta}${ruta.includes('?') ? '&' : '?'}volver=${encodeURIComponent(volver)}`
  const nuevo = conVolver(`/m/${modulo.clave}/nuevo?empleado=${empleado.id}&empleado_texto=${encodeURIComponent(String(empleado.texto ?? ''))}`)
  const Icono = modulo.icono

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-semibold text-stone-800"><Icono size={18} className="text-marca-700" /> {modulo.titulo}</h2>
        {!soloVer && puedeCrear(usuario, modulo) && (
          <Link to={nuevo} className="flex items-center gap-1 rounded-lg border border-marca-700 px-3 py-1.5 text-sm font-medium text-marca-800 hover:bg-marca-50">
            <Plus size={16} /> Nuevo
          </Link>
        )}
      </div>
      {filas === null ? <p className="text-sm text-stone-500">Cargando…</p> : filas.length === 0 ? (
        <p className="text-sm text-stone-500">Sin registros.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-max text-sm">
            <thead className="text-left text-stone-500">
              <tr>{columnas.map((c) => <th key={c.campo} className="py-1 pr-3 font-medium">{c.etiqueta}</th>)}</tr>
            </thead>
            <tbody>
              {filas.map((r) => (
                <tr key={r.id} className={`border-t border-stone-100 ${modulo.colorFila?.(r) ?? ''}`}>
                  {columnas.map((c, i) => (
                    <td key={c.campo} className="py-1.5 pr-3">
                      {i === 0
                        ? <Link to={conVolver(`/m/${modulo.clave}/${r.id}`)} className="text-marca-800 underline">{valorVisible(r, c.campo, modulo.campos.find((x) => x.nombre === c.campo))}</Link>
                        : valorVisible(r, c.campo, modulo.campos.find((x) => x.nombre === c.campo))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/** Debajo de la ficha del empleado (y en "Mi ficha", solo para ver). */
export default function LegajoEmpleado({ empleado, soloVer, volver }: { empleado: Registro; soloVer?: boolean; volver?: string }) {
  const { usuario } = useSesion()
  const modulos = MODULOS.filter((m) => m.enLegajo && puedeVer(usuario, m))
  return (
    <>
      {modulos.map((m) => (
        <Seccion key={m.clave} modulo={m} empleado={empleado} soloVer={soloVer} volver={volver ?? `/m/empleados/${empleado.id}`} />
      ))}
    </>
  )
}
