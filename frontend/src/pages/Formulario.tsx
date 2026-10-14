import { Fragment, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import axios from 'axios'
import { ChevronLeft, Save, Trash2 } from 'lucide-react'
import api from '../services/api'
import { useSesion } from '../services/sesionContexto'
import AccionesEmpleado from '../components/AccionesEmpleado'
import AccionesRegistro from '../components/AccionesRegistro'
import LegajoEmpleado from '../components/LegajoEmpleado'
import FotoEmpleado from '../components/FotoEmpleado'
import CampoFormulario from '../components/CampoFormulario'
import DetalleAuditoria from '../components/DetalleAuditoria'
import LogoEmpresa from '../components/LogoEmpresa'
import { buscarModulo } from '../modulos'
import { hoyIso, mensajeDeError } from '../formato'
import { puedeBorrar, puedeCrear, puedeModificar, puedeVer } from '../permisos'
import type { Campo, Marca, Registro, TipoCampo } from '../tipos'

// Tipos cuyo campo vacío se manda como null (en Django son null=True). Los de
// texto se mandan como cadena vacía, que es lo que Django guarda para ellos.
const VACIO_ES_NULL: TipoCampo[] = ['entero', 'decimal', 'fecha', 'fechaHora', 'relacion']

function valoresIniciales(campos: Campo[], parametros: URLSearchParams): Record<string, unknown> {
  const valores: Record<string, unknown> = {}
  for (const c of campos) {
    if (c.porDefecto === 'hoy') valores[c.nombre] = hoyIso()
    else if (c.porDefecto !== undefined) valores[c.nombre] = c.porDefecto
    else valores[c.nombre] = ['relacion', 'archivo'].includes(c.tipo) ? null : ['seleccionMultiple', 'relacionMultiple', 'filas'].includes(c.tipo) ? [] : ''
    // Valores fijados desde otra pantalla (ej. el legajo: ?empleado=3&empleado_texto=…).
    const fijo = parametros.get(c.nombre)
    if (fijo !== null) {
      valores[c.nombre] = ['relacion', 'entero'].includes(c.tipo) ? Number(fijo) : fijo
      valores[`${c.nombre}_texto`] = parametros.get(`${c.nombre}_texto`) ?? fijo
    }
  }
  return valores
}

function armarEnvio(campos: Campo[], valores: Record<string, unknown>, esNuevo: boolean): Record<string, unknown> | FormData {
  const envio: Record<string, unknown> = {}
  for (const c of campos) {
    if (c.soloLectura) continue
    const v = valores[c.nombre]
    // La contraseña (o el número de cuenta) vacía al editar no se manda: no se cambia.
    if (c.tipo === 'clave' && !esNuevo && !v) continue
    envio[c.nombre] = (v === '' || v === undefined) && VACIO_ES_NULL.includes(c.tipo) ? null : v
  }
  if (!Object.values(envio).some((v) => v instanceof File)) return envio
  // Con archivos se manda como formulario multipart.
  const formulario = new FormData()
  for (const [nombre, v] of Object.entries(envio)) {
    if (v === null || v === undefined) continue
    if (Array.isArray(v)) v.forEach((item) => formulario.append(nombre, String(item)))
    else if (v instanceof File) formulario.append(nombre, v)
    else formulario.append(nombre, typeof v === 'boolean' ? (v ? 'true' : 'false') : String(v))
  }
  return formulario
}

/** Mensaje legible de un error de DRF: ['texto'] o, en filas anidadas,
 * [{}, {campo: ['texto']}] → 'Fila 2 · campo: texto'. */
function textoError(mensajes: unknown[]): string {
  const i = mensajes.findIndex((m) => typeof m === 'string' || (m && typeof m === 'object' && Object.keys(m).length > 0))
  if (i < 0) return 'Revisá este campo.'
  const m = mensajes[i]
  if (typeof m === 'string') return m
  const [campo, detalle] = Object.entries(m as Record<string, unknown>)[0]
  const texto = Array.isArray(detalle) ? String(detalle[0]) : String(detalle)
  return `Fila ${i + 1} · ${campo === 'non_field_errors' ? '' : `${campo}: `}${texto}`
}

/** Formulario genérico de un módulo (ver modulos.ts): alta, vista y edición. */
export default function Formulario() {
  const { clave, id } = useParams()
  const [parametros] = useSearchParams()
  const modulo = buscarModulo(clave)
  const { usuario, actualizar } = useSesion()
  const navegar = useNavigate()
  // Mensaje de la pantalla anterior (ej. al volver al legajo después de generar un código).
  const mensajeRecibido = (useLocation().state as { mensaje?: string } | null)?.mensaje
  const esNuevo = !id
  const campos = useMemo(() => (modulo?.campos ?? []).filter((c) => esNuevo || !c.soloAlCrear), [modulo, esNuevo])

  const [valores, setValores] = useState<Record<string, unknown>>({})
  const [errores, setErrores] = useState<Record<string, string>>({})
  const [errorGeneral, setErrorGeneral] = useState<string | null>(null)
  const [cargando, setCargando] = useState(!esNuevo)
  const [guardando, setGuardando] = useState(false)
  // Para volver a leer el registro después de una acción (ej. dar de baja).
  const [version, setVersion] = useState(0)

  useEffect(() => {
    if (!modulo) return
    setErrores({})
    setErrorGeneral(null)
    if (esNuevo) {
      setValores(valoresIniciales(campos, parametros))
      setCargando(false)
      return
    }
    if (version === 0) setCargando(true)
    api.get<Registro>(`/${modulo.endpoint}/${id}/`)
      // Los campos secretos (contraseña, número de cuenta) nunca llegan: arrancan vacíos.
      .then((r) => setValores({ ...r.data, password: '', numero: '' }))
      .catch(() => setErrorGeneral('No se encontró el registro.'))
      .finally(() => setCargando(false))
  }, [modulo, id, esNuevo, campos, version, parametros])

  if (!modulo || !puedeVer(usuario, modulo)) {
    return <p className="rounded-xl bg-white p-6">Esta sección no existe o no tenés acceso. <Link to="/" className="underline">Volver al panel</Link></p>
  }

  // La empresa propia no tiene lista a la que volver: se vuelve al panel.
  // ?volver=…: desde el legajo de un empleado se vuelve a él.
  const volver = parametros.get('volver') ?? (modulo.clave === 'empresa' && usuario?.empresa ? '/' : `/m/${modulo.clave}`)
  const irA = (mensaje: string) => navegar(volver, { state: { mensaje } })

  const guardar = async (e: FormEvent) => {
    e.preventDefault()
    setGuardando(true)
    setErrores({})
    setErrorGeneral(null)
    const envio = armarEnvio(campos, valores, esNuevo)
    try {
      if (esNuevo) {
        const r = await api.post<Registro>(`/${modulo.endpoint}/`, envio)
        irA(modulo.mensajeAlCrear ? modulo.mensajeAlCrear(r.data) : `Se guardó: ${modulo.singular}.`)
      } else {
        await api.patch(`/${modulo.endpoint}/${id}/`, envio)
        // Los cambios en la propia empresa o en uno mismo pueden cambiar la sesión.
        if (modulo.clave === 'empresa' || modulo.clave === 'usuarios') actualizar()
        irA('Cambios guardados.')
      }
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 400 && err.response.data && typeof err.response.data === 'object') {
        const porCampo: Record<string, string> = {}
        for (const [campo, mensajes] of Object.entries(err.response.data as Record<string, unknown>)) {
          if (Array.isArray(mensajes) && mensajes.length) porCampo[campo] = textoError(mensajes)
        }
        setErrores(porCampo)
        const sinCampo = Object.keys(porCampo).filter((c) => !campos.some((x) => x.nombre === c))
        setErrorGeneral(sinCampo.length && sinCampo[0] !== 'non_field_errors'
          ? `${sinCampo[0]}: ${porCampo[sinCampo[0]]}`
          : mensajeDeError(err.response.data, 'Revisá los campos marcados en rojo.'))
      } else if (axios.isAxiosError(err) && err.response) {
        setErrorGeneral(mensajeDeError(err.response.data, 'No tenés permiso para hacer esto.'))
      } else {
        setErrorGeneral('No se pudo guardar. Revisá la conexión con el servidor.')
      }
    } finally {
      setGuardando(false)
    }
  }

  const eliminar = async () => {
    if (!window.confirm(`¿Borrar este registro (${modulo.singular})? No se puede deshacer.`)) return
    try {
      await api.delete(`/${modulo.endpoint}/${id}/`)
      irA('Registro borrado.')
    } catch (err) {
      setErrorGeneral(axios.isAxiosError(err) ? mensajeDeError(err.response?.data, 'No se pudo borrar.') : 'No se pudo borrar.')
    }
  }

  const soloLectura = esNuevo
    ? !puedeCrear(usuario, modulo)
    : !puedeModificar(usuario, modulo) || Boolean(modulo.soloLecturaSi?.(valores as Registro))

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-stone-200 sm:p-6">
        <div className="mb-5 flex items-center gap-2">
          <Link to={volver} aria-label="Volver" className="rounded-md p-1 text-stone-500 hover:bg-stone-100">
            <ChevronLeft />
          </Link>
          <h1 className="text-xl font-bold text-stone-900 sm:text-2xl">
            {esNuevo ? `Nuevo: ${modulo.singular}` : `${soloLectura ? 'Ver' : 'Editar'} ${modulo.singular}`}
          </h1>
        </div>

        {!esNuevo && modulo.clave === 'empleados' && valores.estado === 'baja' && (
          <p className="mb-4 rounded-lg bg-stone-100 px-3 py-2 text-sm text-stone-700">
            Dado de baja el <strong>{String(valores.fecha_egreso ?? '').split('-').reverse().join('/')}</strong>
            {valores.motivo_egreso ? `: ${String(valores.motivo_egreso)}` : ''}.
          </p>
        )}

        {mensajeRecibido && <p className="mb-4 rounded-lg bg-marca-50 px-3 py-2 text-sm text-marca-900">{mensajeRecibido}</p>}

        {/* Avisos que calcula el servidor (ej. un horario por encima del máximo del régimen). */}
        {!cargando && Array.isArray(valores.advertencias) && valores.advertencias.length > 0 && (
          <ul className="mb-4 list-disc space-y-1 rounded-lg border border-amber-300 bg-amber-50 py-2 pl-8 pr-3 text-sm text-amber-900">
            {(valores.advertencias as string[]).map((a) => <li key={a}>{a}</li>)}
          </ul>
        )}

        {cargando ? (
          <p className="text-stone-500">Cargando…</p>
        ) : modulo.clave === 'auditoria' ? (
          <DetalleAuditoria evento={valores as Registro} />
        ) : (
          <form onSubmit={guardar} noValidate>
            <fieldset disabled={soloLectura} className="grid gap-4 sm:grid-cols-2">
              {campos.map((c) => (
                <Fragment key={c.nombre}>
                  {c.seccion && (
                    <h2 className="border-b border-marca-100 pb-1 pt-2 font-semibold text-stone-700 sm:col-span-2">{c.seccion}</h2>
                  )}
                  <CampoFormulario campo={c} valores={valores} error={errores[c.nombre]} esNuevo={esNuevo}
                    onCambio={(cambios) => setValores((v) => {
                      const nuevos: Record<string, unknown> = { ...v, ...cambios }
                      // Si cambia un campo del que dependen otros (ej. el empleado → su contrato), se vacían.
                      for (const otro of campos) {
                        if (Object.values(otro.filtrosDe ?? {}).some((dep) => dep in cambios && cambios[dep] !== v[dep])) {
                          nuevos[otro.nombre] = null
                          nuevos[`${otro.nombre}_texto`] = ''
                        }
                      }
                      return nuevos
                    })} />
                </Fragment>
              ))}
            </fieldset>

            {errorGeneral && <p className="mt-5 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{errorGeneral}</p>}

            {!soloLectura && (
              <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs text-stone-500">
                  {valores.creado_por ? `Cargado por ${String(valores.creado_por)}` : ''}
                </p>
                <div className="flex gap-2">
                  {!esNuevo && puedeBorrar(usuario, modulo) && (
                    <button type="button" onClick={eliminar}
                      className="flex items-center gap-1 rounded-lg border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50">
                      <Trash2 size={16} /> Borrar
                    </button>
                  )}
                  <button type="submit" disabled={guardando}
                    className="flex items-center gap-1 rounded-lg bg-marca-700 px-5 py-2 text-sm font-medium text-white hover:bg-marca-600 disabled:opacity-60">
                    <Save size={16} /> {guardando ? 'Guardando…' : 'Guardar'}
                  </button>
                </div>
              </div>
            )}
          </form>
        )}
        {modulo.clave === 'auditoria' && errorGeneral && <p className="mt-5 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{errorGeneral}</p>}
      </div>

      {!esNuevo && !cargando && modulo.acciones && (
        <AccionesRegistro modulo={modulo} registro={valores as Registro} onCambio={() => setVersion((v) => v + 1)} />
      )}

      {!esNuevo && !cargando && modulo.clave === 'empresa' && (
        <LogoEmpresa empresa={Number(id)} marca={valores.marca as Marca | undefined} editable={!soloLectura}
          onCambio={() => { setVersion((v) => v + 1); actualizar() }} />
      )}

      {!esNuevo && !cargando && modulo.clave === 'empleados' && (
        <>
          <FotoEmpleado empleado={Number(id)} tieneFoto={valores.tiene_foto === true} editable={puedeModificar(usuario, modulo)}
            onCambio={() => setVersion((v) => v + 1)} />
          <AccionesEmpleado empleado={valores as Registro} onCambio={() => setVersion((v) => v + 1)} />
          <LegajoEmpleado empleado={valores as Registro} />
        </>
      )}
    </div>
  )
}
