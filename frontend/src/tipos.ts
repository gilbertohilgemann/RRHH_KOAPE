import type { LucideIcon } from 'lucide-react'

export type TipoCampo =
  | 'texto'
  | 'textoLargo'
  | 'correo'
  | 'entero'
  | 'decimal'
  | 'fecha'
  | 'booleano'
  | 'opciones'
  | 'relacion'
  /** Varias opciones fijas (`opciones`), con casillas; se envía la lista de valores. */
  | 'seleccionMultiple'
  /** Varios registros de otro módulo (`relacion`), con casillas; se envía la lista de ids. */
  | 'relacionMultiple'
  /** Contraseña: nunca se muestra; vacía al editar = no se cambia. */
  | 'clave'
  /** Color #RRGGBB con el selector del navegador (vacío = el de Koape). */
  | 'color'
  /** Archivo (PDF o imagen): el formulario se envía como multipart. */
  | 'archivo'
  /** Hora hh:mm. */
  | 'hora'
  /** Fecha y hora (se envía en la hora local; el servidor la guarda con su zona horaria). */
  | 'fechaHora'
  /** Filas hijas editables en una tabla (ej. tramos de un horario): lista de objetos con subcampos. */
  | 'filas'

export interface Opcion {
  valor: string
  texto: string
}

export interface Campo {
  nombre: string
  etiqueta: string
  tipo: TipoCampo
  requerido?: boolean
  opciones?: Opcion[]
  /** Clave del módulo al que apunta un campo 'relacion' o 'relacionMultiple'. */
  relacion?: string
  /** Para 'relacion': filtros fijos de la búsqueda (ej. { activo: 'true' }). */
  filtros?: Record<string, string>
  /** Para 'relacion': filtros que toman el valor de otro campo ({ parámetro: campo },
   * ej. { empleado: 'empleado' }). Hasta que ese campo tenga valor no se puede elegir. */
  filtrosDe?: Record<string, string>
  /** Para 'relacion': sin el botón "+ Nueva". */
  sinNueva?: boolean
  ayuda?: string
  /** Largo máximo de un texto (igual al max_length del modelo). */
  maxLength?: number
  /** Valor inicial al crear un registro nuevo. */
  porDefecto?: 'hoy' | string | number | boolean | string[]
  /** Título de sección que se muestra antes de este campo en el formulario. */
  seccion?: string
  /** Obligatorio solo al crear (ej. la contraseña inicial). */
  requeridoAlCrear?: boolean
  /** Solo aparece al crear (ej. el archivo de un documento, que después no se reemplaza). */
  soloAlCrear?: boolean
  /** Se muestra pero no se edita nunca desde el formulario (lo escribe el sistema). */
  soloLectura?: boolean
  /** Para 'filas': las columnas de cada fila. */
  subcampos?: Campo[]
  /** Para 'filas' con 'dia_semana': botón para copiar las filas del lunes a martes–viernes. */
  copiarLunes?: boolean
}

/** Acción propia de un registro (activar, aprobar, anular, descargar...). */
export interface Accion {
  /** Nombre de la acción en la API: POST <endpoint>/<id>/<accion>/ */
  accion: string
  etiqueta: string
  /** Permiso de Django que hace falta (el frontend solo oculta el botón; la API decide). */
  permiso: string
  visibleSi?: (registro: Registro) => boolean
  /** Pide un motivo antes de confirmar. */
  pideMotivo?: boolean
  /** Otra etiqueta para ese texto (ej. "Referencia del pago"); se envía igual como `motivo`. */
  etiquetaMotivo?: string
  /** Después de la acción, ir a esta dirección armada con la respuesta (ej. la liquidación calculada). */
  irA?: (respuesta: Registro) => string
  /** Pide una fecha antes de confirmar: nombre del campo que se envía y su etiqueta. */
  pideFecha?: { campo: string; etiqueta: string }
  /** Texto de confirmación (si no pide datos). */
  confirmar?: string
  peligrosa?: boolean
  /** 'descarga' = baja el archivo (GET); 'revelar' = muestra lo que devuelve (ej. número de cuenta);
   * 'resultado' = muestra el `texto` que devuelve, sin cambiar nada (ej. probar una fórmula). */
  tipo?: 'post' | 'descarga' | 'revelar' | 'resultado'
}

export interface Columna {
  campo: string
  etiqueta: string
}

export type Grupo = 'Personal' | 'Jornada' | 'Asistencia' | 'Licencias' | 'Nómina' | 'Reportes' | 'Estructura' | 'Administración'

export interface FiltroLista {
  nombre: string
  etiqueta: string
  opciones: Opcion[]
}

export interface Modulo {
  clave: string
  titulo: string
  singular: string
  grupo: Grupo
  icono: LucideIcon
  descripcion: string
  /** Ruta dentro de la API, sin barras (ej. 'centros-costo'). */
  endpoint: string
  /** Modelo de Django ('app.modelo'), para saber qué permisos tiene el usuario sobre él. */
  modelo: string
  /** Permiso que reemplaza a los view/add/change del modelo (ej. usuarios). */
  permisoPropio?: string
  campos: Campo[]
  columnas: Columna[]
  /** Campo por el que filtra el rango de fechas del listado (si tiene). */
  campoFecha?: string
  /** El listado se puede filtrar por sucursal. */
  filtroSucursal?: boolean
  /** Filtros de lista fija en el listado (ej. estado del empleado). */
  filtrosLista?: FiltroLista[]
  /** La API permite borrar (los legajos y sucursales no se borran: se dan de baja). */
  permiteBorrar?: boolean
  /** No se crea desde la aplicación (ej. la empresa, la auditoría). */
  sinAlta?: boolean
  /** Nunca se edita (ej. la auditoría). */
  soloLectura?: boolean
  /** Color de fondo de cada fila del listado según el registro (clase de Tailwind). */
  colorFila?: (registro: Registro) => string
  /** Ya guardado, no se edita según su estado (ej. un contrato vigente). */
  soloLecturaSi?: (registro: Registro) => boolean
  /** Acciones propias del registro, debajo del formulario. */
  acciones?: Accion[]
  /** Se ve en el legajo de cada empleado (sección con sus registros y alta precargada). */
  enLegajo?: boolean
  /** No aparece en el menú ni en el panel (se usa desde el legajo). */
  oculto?: boolean
  /** Pantalla propia en vez del listado genérico (ej. una configuración). */
  rutaPropia?: string
  /** Pantalla propia para ver un registro (en vez del formulario genérico). */
  rutaDetalle?: (id: number) => string
  /** Pantalla propia para crear (en vez del formulario genérico). */
  rutaNuevo?: string
  /** Mensaje al volver después de crear, con la respuesta de la API (ej. el código generado). */
  mensajeAlCrear?: (respuesta: Registro) => string
}

export type Registro = { id: number } & Record<string, unknown>

export interface Paginado<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface Marca {
  /** Dirección completa del logo de la empresa, o null (se usa el de Koape). */
  logo: string | null
  color_primario: string
  color_secundario: string
  personalizada: boolean
}

export type Nivel ='plataforma' | 'administrador' | 'gestor' | 'empleado'

export interface DatosUsuario {
  usuario: string
  nombre: string
  nivel: Nivel
  /** Nombres de los grupos de Django: 'Administrador', 'Gestor RR. HH.', 'Empleado', 'Koape'. */
  perfiles: string[]
  empresa: { id: number; nombre: string } | null
  /** Logo y colores de su empresa (los de Koape si no cargó los suyos o es la plataforma). */
  marca: Marca
  /** Sucursales a las que está limitado (vacío = todas). */
  sucursales: { id: number; nombre: string }[]
  /** Su legajo, si tiene el perfil Empleado. */
  empleado: { id: number; codigo: string; nombre: string } | null
  /** Permisos de Django del usuario ('app.codigo'); ['*'] = todos (plataforma). */
  permisos: string[]
}
