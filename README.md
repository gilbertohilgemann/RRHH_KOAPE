# Koape RR. HH. — Legajos, asistencia y nómina (Paraguay)

Sistema multiempresa de recursos humanos: legajos, contratos, horarios,
marcaciones (marcador propio con QR dinámico en la terminal escaneado desde el celular, código fijo e importación CSV),
asistencia, licencias, novedades, nómina, aguinaldo, liquidación final, costo
patronal y preparación de información para MTESS/IPS.

- **Especificación**: [`Koape_RRHH_Paquete_Tecnico/`](Koape_RRHH_Paquete_Tecnico/) (especificación técnica y modelo DBML de referencia).
- **Diagnóstico, decisiones y plan por fases**: [`docs/plan-fases.md`](docs/plan-fases.md).
- **Bitácora de cambios**: [`docs/bitacora.md`](docs/bitacora.md). Cada cambio suma su entrada en el mismo trabajo.
- **Para Claude**: [`CLAUDE.md`](CLAUDE.md).
- **Repositorio**: `github.com/gilbertohilgemann/RRHH_KOAPE` (privado).
- **Convenciones obligatorias**: [`Convenciones-de-Proyecto.txt`](Convenciones-de-Proyecto.txt).
- **Proyecto de referencia**: `KOAPE-PORCINO` (misma estructura e infraestructura).

> Estado (14/10/2026): **fases 1 a 11 terminadas: el plan completo de la especificación** (fase 2: contratos, historial salarial, documentos privados y cuentas bancarias cifradas; fase 3: regímenes, horarios con tramos, asignaciones y feriados; fase 4: marcador propio con QR dinámico invertido —la terminal lo proyecta, el empleado lo escanea— y código fijo; fase 5: importación de marcaciones CSV con revisión, deduplicación y reversión; fase 6: motor de asistencia con ajustes y horas extra autorizadas; fase 7: licencias, permisos por horas, saldo de vacaciones por movimientos y certificados médicos; fase 8: reglas legales versionadas con aprobación, conceptos salariales y fórmulas seguras; fase 9: novedades, descuentos autorizados, anticipos y préstamos con cuotas; fase 10: nómina con líneas explicadas, cierre, rectificación, recibos, pagos y costo del empleador; fase 11: aguinaldo, liquidación final, planillas MTESS/IPS y reportes; ver la bitácora). Fase 1 — empresas, sucursales, usuarios con
> perfiles (Administrador, Gestor RR. HH., Empleado) y aislamiento, auditoría,
> legajos (departamentos, puestos, centros de costo, empleados con baja lógica e
> historial de asignaciones), migración SQLite ⇄ PostgreSQL, backup, manuales e
> instaladores. Las fases siguientes están en `docs/plan-fases.md`.

## Estructura del proyecto

```
RRHH-KOAPE/
├── backend/                 # Django 5.2 + Django REST Framework (admin con Jazzmin)
│   ├── config/              # settings.py, urls.py, formatos de fecha dd/mm/aaaa
│   ├── core/                # Auditoría (RegistroBase, EventoAuditoria), aislamiento (alcance.py),
│   │                          API base, sesión, migración a Postgres, usuario admin fijo, datos demo
│   ├── plataforma/          # Empresas y sucursales
│   ├── cuentas/             # Perfil del usuario (empresa, sucursales, legajo), perfiles iniciales, API de usuarios
│   ├── empleados/           # Departamentos, puestos, centros de costo, empleados, historial de asignaciones,
│   │                          tipos de documento, documentos privados, cuentas bancarias cifradas
│   ├── contratos/           # Esquemas salariales, contratos e historial salarial
│   ├── jornada/             # Regímenes de jornada, horarios con tramos, asignaciones de horario, feriados
│   ├── asistencia/          # Marcador: configuración, terminales, códigos fijos, QR dinámico, marcas, intentos, incidencias
│   ├── licencias/           # Tipos de licencia, solicitudes y aprobación, saldo de vacaciones, escala, certificados médicos
│   ├── legal/               # Reglas legales versionadas: conjuntos, parámetros, regímenes de seguridad social
│   ├── nomina/              # Conceptos, reglas de cálculo (fórmulas seguras), conceptos fijos, redondeo; períodos,
│   │                          liquidaciones (motor.py, liquidar.py), recibos, pagos, costo del empleador
│   ├── novedades/           # Novedades (comisiones, bonos…), descuentos autorizados, anticipos, préstamos y sus cuotas
│   ├── cumplimiento/        # Planillas MTESS / IPS desde las nóminas cerradas (validación y exportación)
│   └── migracion/           # Infraestructura: migrar SQLite/Postgres, backup, manual del administrador
├── frontend/                # React + Vite + TypeScript + Tailwind CSS v4
│   └── src/
│       ├── modulos.ts       # Definición de cada pantalla (campos, columnas, endpoint)
│       ├── pages/           # Ingreso, Panel, Listado y Formulario genéricos, Mi ficha, Manual
│       ├── components/      # Diseño, menú, campos, acciones del empleado, detalle de auditoría
│       └── services/        # api.ts (axios) y sesión
├── docs/                    # Plan por fases y bitácora
├── install.sh / start.sh    # Linux
└── install.bat/.ps1, start.bat/.ps1   # Windows
```

## Instalación y ejecución

### Windows (desarrollo local)

Requisitos: [Python 3.11+](https://www.python.org/downloads/) (con "Add python.exe to PATH") y [Node.js LTS](https://nodejs.org/).
El instalador **no instala nada a nivel sistema**: si falta alguno, avisa y se frena.

```powershell
install.bat        # una sola vez (o de nuevo al actualizar el código)
start.bat          # start | stop | status | restart | logs
```

- `install.bat` → arma `backend\venv`, `backend\.env` (con `SECRET_KEY` nueva),
  aplica migraciones, crea el usuario admin fijo e instala el frontend.
- `start.bat` → backend (`runserver`) y frontend (`vite`) en segundo plano, sin
  abrir ventanas; PID en `.run\`, logs en `logs\`. Si un puerto está ocupado por
  otra cosa, **no arranca ahí** y avisa. `stop` mata el árbol completo de procesos.
- Muestra también la dirección para abrirlo **desde el celular** en la misma red Wi-Fi.

> En esta PC `pip` falla con error de certificado (intercepción TLS): exportar las
> raíces de Windows a un `.pem` e instalar con `pip install --cert <archivo.pem>`
> (ver `CLAUDE.md`).

### Linux (servidor)

Se corre con un **usuario común**. Los pasos que tocan el sistema (paquetes con
`dnf`, firewall, servicio de systemd) usan `sudo` y siempre preguntan antes.

```bash
chmod +x install.sh start.sh
./install.sh
./start.sh            # start | stop | status | restart | update
```

- `install.sh`: revisa dependencias (pide permiso antes de instalar), arma el
  entorno, crea `backend/.env` con `SECRET_KEY` real, pregunta el dominio/IP
  (completa `ALLOWED_HOSTS` y CORS), deja el sitio en SQLite, PostgreSQL aparte y
  opcional, crea el usuario admin fijo y, si se contesta que sí, el servicio
  systemd `koape-rrhh`.
- `start.sh update` es lo que se usa para desplegar una versión nueva:
  dependencias, migraciones, estáticos, build y reinicio.

| Qué | Dirección |
|---|---|
| Aplicación | http://localhost:5204 |
| Admin (plataforma) | http://127.0.0.1:8004/admin/ |
| API | http://127.0.0.1:8004/api/ |

Los puertos son **8004** (backend) y **5204** (frontend), distintos de los otros
sistemas de Koape en la misma PC. Están en `start.ps1`, `start.sh`,
`install.sh`, `frontend/vite.config.ts`, `frontend/src/services/api.ts` y
`backend/config/settings.py` (CORS): si se cambian, hay que cambiarlos en todos.

### Usuario administrador fijo

Los instaladores crean (o resetean) el usuario **`admin`** con contraseña
**`Admin*2026`** en cada instalación (`manage.py crear_admin`, idempotente).

> ⚠ Es la misma contraseña en todas las instalaciones: **cambiala desde /admin/
> apenas entres por primera vez**.

### Datos de demostración

`manage.py cargar_datos_demo --clave '<clave>'` crea la "Empresa Demo S.A."
(2 sucursales, estructura y 8 empleados ficticios) y los usuarios `admin_demo`,
`gestor_demo` y `empleado_demo` con esa clave. Es idempotente.

## Modelos de datos

Casi todos heredan de `core.models.RegistroBase` (auditoría: `creado_por`,
`creado`, `modificado_por`, `modificado`) y los de una empresa de
`RegistroEmpresa` (campo `empresa`, que fija siempre el servidor).

| App | Modelo | Qué guarda |
|---|---|---|
| plataforma | `Empresa` | Nombre, razón social, RUC, números patronales IPS/MTESS, zona horaria, moneda, activa; personalización: logo, color principal y secundario |
| plataforma | `Sucursal` | Código (único por empresa), nombre, ciudad, activa |
| cuentas | `Perfil` | Empresa del usuario, sucursales a las que está limitado (vacío = todas), legajo (perfil Empleado) |
| empleados | `Departamento`, `Puesto`, `CentroCosto` | Estructura de la empresa (código único por empresa; departamentos y centros con jerarquía) |
| empleados | `Empleado` | Legajo: documento, nombres, datos personales, contacto, ingreso/egreso, estado, asignación (sucursal, departamento, puesto, centro de costo, supervisor), observaciones internas, foto (privada) |
| empleados | `HistorialAsignacion` | Vigencias de cada asignación del empleado (lo escribe el sistema) |
| empleados | `TipoDocumento` | Catálogo (globales + de cada empresa): confidencial, pide vencimiento |
| empleados | `DocumentoEmpleado` | Archivo privado del legajo: tipo, nombre original, tipo real, tamaño, SHA-256, emisión/vencimiento, confidencial, vigente/anulado |
| empleados | `CuentaBancaria` | Banco, tipo, número **cifrado** + últimos 4 dígitos, titular, principal (una por empleado), activa |
| contratos | `EsquemaSalarial` | Catálogo (globales + de cada empresa): base de cálculo (hora, día, semana, quincena, mes, comisión, destajo, mixta) y frecuencia de pago |
| contratos | `ContratoEmpleado` | Tipo, fechas, prueba, esquema, frecuencia, salario inicial, moneda; borrador → vigente → finalizado / anulado |
| jornada | `RegimenJornada` | Catálogo (globales + de cada empresa): diurna/nocturna/mixta, máximos diario y semanal en minutos, fuente, verificado |
| jornada | `Horario` + `TramoHorario` | Horario semanal: régimen, tolerancia, descanso pago; tramos por día (varios por día, cruce de medianoche, descanso) |
| jornada | `AsignacionHorario` | Horario de cada empleado con vigencia (nunca superpuestas; la anterior abierta se cierra sola) |
| jornada | `CalendarioFeriados` + `DiaFeriado` | Calendario de un año (nacional global + propios de cada empresa) y sus días |
| asistencia | `ConfiguracionMarcacion` | Por empresa: modalidades (QR, código fijo, CSV), vigencia del QR, modo entrada/salida, antirrebote, horas máximas de turno, largo del código |
| asistencia | `TerminalMarcacion` | Dispositivo autorizado: tipo (QR, código, híbrida), sucursal, huella de su clave, última conexión |
| asistencia | `CredencialMarcacion` | Código fijo del empleado: HMAC para buscarlo + copia cifrada, versión, activa/revocada |
| asistencia | `QRDinamico` | QR que proyecta una terminal: huella del token, vence, estado (vigente/usado/reemplazado/vencido), marcas registradas |
| asistencia | `Marcacion` | Marca inmutable: empleado, fecha y hora del servidor, tipo, método, nivel de verificación, terminal, código fijo o QR usado |
| asistencia | `RelojExterno` / `MapeoEmpleadoReloj` | Reloj de otra marca / qué empleado es cada código del reloj (con vigencia, sin superponer) |
| asistencia | `PerfilImportacion` | Cómo leer un CSV: separador, codificación, encabezado, columnas (nombre o número), formatos explícitos, valores de entrada/salida, zona horaria, versión |
| asistencia | `LoteImportacion` + `FilaImportacion` | Archivo importado (privado, SHA-256, perfil y versión, período, contadores, estado validado/confirmado/cancelado/revertido) y cada fila con su resultado y motivo |
| asistencia | `DiaAsistencia` | Resultado del día por empleado (lo escribe el motor): programado, trabajado, descanso, tardanza, salida anticipada, ordinario, extra candidato/autorizado, nocturno, feriado, marcas faltantes, estado, explicación, versión, revisión |
| asistencia | `AjusteMarcacion` | Agregar una marca que faltó o anular una errónea; pendiente → aprobado (crea marca manual o anula) / rechazado |
| asistencia | `AutorizacionHorasExtra` | Minutos de extra solicitados y aprobados por día; sin aprobación no hay extra autorizado |
| asistencia | `IntentoMarcacion` / `IncidenciaAsistencia` | Intentos rechazados (auditoría y bloqueo) / anomalías de secuencia para revisar |
| contratos | `HistorialSalarial` | Sueldo con vigencia (desde/hasta), tarifas hora/día opcionales, motivo; pendiente → aprobado / anulado, quién y cuándo aprobó |
| core | `EventoAuditoria` | Bitácora: quién, cuándo, qué registro, acción, valores anteriores y nuevos, IP |

## Patrones importantes a conocer antes de tocar el código

- **Aislamiento** (`core/alcance.py`): el único lugar que decide qué filas ve
  cada usuario. Toda consulta de la API pasa por `alcance.filtrar()`. Cada
  modelo declara `ruta_empresa`, y si corresponde `ruta_sucursal` y
  `ruta_empleado`; un modelo sin `ruta_empresa` hace fallar el filtro (a
  propósito). Las relaciones que llegan en un pedido se restringen al alcance
  (un id de otra empresa responde "no existe"). **Cada cambio de acceso tiene
  que tener su prueba en `cuentas/tests.py`.**
- **Perfiles = grupos de Django** (`cuentas/perfiles.py`): Koape (plataforma),
  Administrador, Gestor RR. HH., Empleado. Se crean solos al migrar con sus
  permisos iniciales y se ajustan desde el admin; `manage.py
  restablecer_perfiles --confirmar` vuelve a los iniciales. Cada fase nueva
  suma ahí los permisos de sus modelos.
- **Denegación por defecto** (`core/api/permisos.py`): la API exige el permiso
  de Django de cada lectura (`view_`) y escritura (`add_`, `change_`,
  `delete_`), o el que declare `permisos_acciones` en el viewset (ej.
  `empleados.dar_baja_empleado`). El frontend recibe la lista en
  `/api/sesion/yo/` y solo oculta lo que la API igual rechazaría.
- **Perfil Empleado**: su legajo sale del perfil del usuario en el servidor,
  nunca de un id del navegador. Ve su ficha sin las observaciones internas
  (`FichaPropiaSerializer`).
- **Usuarios** (`cuentas/api.py`): el Administrador crea usuarios de su
  empresa; nunca asigna el grupo Koape, no se cambia sus propios perfiles ni se
  desactiva; los usuarios no se borran.
- **Auditoría automática** (`core/auditoria.py`): la API base y el admin
  registran cada alta, modificación (solo los campos cambiados, con valor
  anterior y nuevo) y borrado en la misma transacción; las acciones propias
  (baja, reactivación, ingreso, cambio de perfiles) llaman a `registrar()`.
  `EventoAuditoria` no se edita ni se borra.
- **Bajas lógicas**: empleados, empresas, sucursales y usuarios nunca se borran
  (`permite_borrar = False` en el viewset). La baja de un empleado
  (`/dar_baja/`) y su reactivación (`/reactivar/`) exigen motivo.
- **Historial de asignaciones**: `Empleado.save()` cierra la vigencia anterior
  y abre una nueva cuando cambia sucursal, departamento, puesto, centro de costo
  o supervisor.
- **Validación del modelo siempre** (`RegistroSerializer.validate`): corre
  `full_clean()` con los datos nuevos, así las reglas de negocio (misma
  empresa, sin ciclos, fechas coherentes) valen igual por la API y por el admin.
- **Frontend dirigido por configuración** (`frontend/src/modulos.ts`): listado
  y formulario genéricos; cada módulo declara campos y columnas con los nombres
  **exactos** del modelo de Django. Nada de datos escritos en el frontend.
- **API privada con token** (`/api/sesion/ingresar/`, con throttling 10/minuto);
  ingresos e intentos fallidos quedan en la auditoría.
- **Catálogos globales + propios** (`core.models.CatalogoEmpresa`,
  `core.api.base.CatalogoViewSet`): empresa vacía = ítem global; cada empresa
  ve los globales y los suyos, pero solo modifica los suyos.
- **Estados con acciones propias** (contratos y sueldos): se editan solo en
  borrador / pendiente; los cambios de estado son acciones con su permiso
  (`activar`, `finalizar`, `anular`, `aprobar`, `rechazar`) y quedan en la
  auditoría. Activar un contrato abre su primer sueldo; aprobar un sueldo
  cierra el anterior el día previo y nunca deja vigencias solapadas
  (`contratos/models.py`). `sueldo_vigente(empleado, fecha)` da el sueldo de
  una fecha.
- **Archivos privados** (`core/archivos.py`): en `backend/privado/` con nombre
  aleatorio; se valida el contenido real (PDF/JPG/PNG/WEBP, máx. 10 MB), se
  guarda la huella SHA-256 y se descargan solo por la API (auditado). Los
  confidenciales los ve quien tiene `empleados.ver_documento_confidencial` y el
  propio empleado.
- **Cifrado** (`core/cifrado.py`): los números de cuenta van cifrados con
  `CLAVE_CIFRADO` (Fernet, en `.env`, la generan los instaladores una sola
  vez). Nunca se descifran para listados ni para la bitácora; `revelar` lo
  hace a pedido, con permiso y auditado.
- **Permisos de cada fase** (`cuentas/perfiles.py`): `FASE_N` + una migración
  de datos que llama a `sumar_en_migracion()`, así las instalaciones existentes
  reciben los permisos nuevos sin perder los ajustes del admin.
- **Frontend: legajo y acciones**: los módulos con `enLegajo` aparecen debajo
  de la ficha del empleado (`LegajoEmpleado`, con alta precargada vía
  `?empleado=…&volver=…`); las `acciones` de cada módulo las dibuja
  `AccionesRegistro`; `soloLecturaSi` bloquea el formulario según el estado.
- **Filas anidadas** (`core.api.base.ConAnidadosSerializer`): tramos de un horario y días de un calendario se
  guardan con su padre en una sola operación (se reemplazan todas, cada una con su `full_clean` y el conjunto con
  `validar_anidados`); el modelo padre declara `datos_auditoria_extra()` para que la auditoría las incluya. En el
  frontend: campo `filas` con `subcampos` (`EditorFilas`).
- **Jornada** (`jornada/models.py`): `horario_vigente(empleado, fecha)` y `feriado_en(empresa, fecha)` son la
  base del motor de asistencia (fase 6). Los máximos de los regímenes solo generan `advertencias` (visibles, no
  bloquean); los tramos superpuestos (también el domingo noche con el lunes) se rechazan.
- **Marcador** (`asistencia/marcador.py`, un solo lugar para las modalidades): QR **invertido** (decisión del cliente,
  14/10/2026): la pantalla `/terminal` pide cada segundo `GET /api/terminal/qr/?actual=&desde=` (el QR vigente, con el
  token solo cuando cambia, y las marcas nuevas en esa terminal); el QR lleva el enlace `/marcar/<token>` y el empleado lo
  envía con su sesión a `POST /api/marcador/qr/`. El QR cambia cada `vigencia_qr_segundos` y, con `qr_un_solo_uso`,
  apenas alguien lo usa (consumo atómico); 10 s de gracia tras vencer. Hora del servidor; legajo bloqueado (`select_for_update`) para ordenar
  marcas simultáneas; antirrebote; entrada/salida automática o elegida; secuencias incoherentes = marca + incidencia;
  cada rechazo queda en `IntentoMarcacion` y 10 códigos/QR desconocidos en 5 minutos bloquean la terminal. Las
  terminales se autentican con su propia clave (`Authorization: Terminal …`, `asistencia/autenticacion.py`); la pantalla
  `/terminal` del frontend no usa usuario. Foto del empleado privada (`Empleado.foto`, achicada a 600 px sin EXIF,`core/archivos.preparar_foto`); la terminal solo ve la de quien marcó en ella en los últimos 5 minutos. La cámara
  dentro del navegador exige HTTPS (o localhost); sin eso, el QR se escanea con la cámara normal del teléfono (abre
  `/marcar/<token>`).
- **Importación CSV** (`asistencia/importacion.py`): nunca directo a marcas; `crear_lote` valida cada fila (código por
  códigos de reloj, legajo o cédula según el perfil; formato de fecha explícito; empleado activo en esa fecha; período;
  futuro; entrada/salida) y marca duplicadas por huella normalizada o id de evento, dentro del archivo y contra lo
  importado; `confirmar` crea las marcas en una transacción (método `csv`, verificación `archivo_importado`);
  `revertir` las anula (`Marcacion.anulada`, la huella es única solo entre no anuladas) y consulta`periodo_cerrado()`, que la fase 10 conecta a la nómina. Errores descargables en CSV/XLSX con protección contra
  fórmulas. Ejemplo para probar: `docs/ejemplos/marcaciones_reloj_demo.csv` (perfil y reloj de la demo).
- **Motor de asistencia** (`asistencia/motor.py`): `calcular(empleado, desde, hasta)` precarga marcas, horarios,
  feriados y autorizaciones y escribe un `DiaAsistencia` por día con su `explicacion`. Cada marca pertenece al día cuyo
  horario la cubre (4 h antes del primer tramo a 8 h después del último; en empate, el borde de tramo más cercano: turnos
  de noche). Pares entrada–salida; faltantes = incidencia, nunca se inventan. Se descuenta el hueco entre tramos trabajado
  y el descanso de tramo no marcado. Extra candidato ≠ autorizado. Incidencias automáticas regeneradas en cada cálculo (las resueltas o justificadas se respetan). Recalcula solo al marcar, importar, revertir y aprobar ajustes/extras (`recalcular_despues`, al confirmarse la transacción); `manage.py calcular_asistencia` para períodos (programarlo `--ayer` cada noche). Ajustes y horas extra con separación opcional de quien pide y quien aprueba.
- **Licencias y vacaciones** (`licencias/`): las reglas están en `licencias/servicios.py` (`aprobar`, `rechazar`,
  `cancelar`, `devengar`). Los días se calculan en el servidor (`contar_dias`: hábiles según el horario vigente y sin
  feriados, o corridos). Sin superposiciones entre licencias del mismo empleado (salvo permisos por horas en franjas
  distintas). El saldo de vacaciones es la suma de `MovimientoVacaciones` (devengo por aniversario según
  `EscalaVacaciones`, goce al aprobar, ajustes, correcciones); nunca se editan ni se borran: cancelar una licencia
  aprobada devuelve los días con una corrección. El motor marca el día como `licencia` (no es ausencia) y un permiso por
  horas corre el inicio o el fin del tramo para la tardanza. Tipos y escala globales "sin verificar" (fuente legal en
  cada uno). Certificados médicos sin diagnóstico; el archivo es un documento confidencial del legajo.
- **Reglas legales** (`legal/servicios.py`): ningún mínimo, tasa, recargo ni divisor va en el código. `parametro()`,
  `regimen()` y `vigentes()` resuelven el valor de una fecha (propios de la empresa antes que globales; la versión más
  nueva). Sin un conjunto **aprobado** lanzan `ReglaNoAprobada` (bloquea la liquidación real); con `simulacion=True`
  usan borradores y avisan. Ciclo: borrador → revisado → aprobado (otra persona) → retirado; aprobado no se edita, se
  crea una versión nueva. Los regímenes aportan las variables `IPS_TASA_TRABAJADOR` / `IPS_TASA_PATRONAL`.
- **Fórmulas** (`nomina/expresiones.py`): nunca `eval`. Se analizan con `ast` contra una lista blanca (números,
  variables en MAYÚSCULAS, operaciones, comparaciones, `if/else`, `min/max/abs/redondear`) y se calculan con Decimal.
  Todo importe pasa por `nomina/redondeo.redondear()`. Las variables de la liquidación están documentadas en
  `nomina/variables.py` (las calculará la fase 10).
- **Novedades, anticipos y préstamos** (`novedades/servicios.py`): todo cambio de estado pasa por ahí. Anticipos y
  préstamos generan `CuotaRecuperacion` al pagarse o desembolsarse (una por mes, única por número); el saldo es la
  suma de las pendientes. La nómina (fase 10) marcará cada cuota y cada novedad como aplicada (campo `corrida`), así
  recalcular no descuenta dos veces. Los descuentos exigen autorización documentada (§8).
- **Nómina** (`nomina/motor.py` calcula; `nomina/liquidar.py` cambia estados): ver el docstring de cada uno. Claves:
  todo valor legal sale de `legal/servicios.vigentes()`; cada `LineaNomina` guarda su explicación y una copia del
  concepto; con reglas sin aprobar la corrida es una simulación que no se aprueba; cerrar marca novedades y cuotas
  como aplicadas (campo `corrida`) y cierra el período (`liquidar.periodo_cerrado()`, que consultan asistencia,
  importación y licencias); una cerrada solo se rectifica con otra corrida enlazada. El aporte del empleador nunca
  resta del neto y no se muestra en el recibo del trabajador ni a quien no tiene `nomina.ver_costo_patronal`.
  Un empleado con `aporta_ips=False` no lleva los aportes automáticos cuya `base_por_defecto` es `BASE_IPS` y no va
  en la planilla del IPS (ni su recibo lleva el número patronal: `LiquidacionEmpleado.aporta_ips` guarda el dato al
  calcular). Con `sin_control_asistencia=True` la asistencia no se calcula y la nómina paga el valor completo
  (`_Liquidador._programado` para jornal y hora). Los anticipos pagados tienen su `ReciboAnticipo` numerado, que la
  línea de cada cuota cita en la nómina.
- **Aguinaldo y egreso**: corridas de tipo `aguinaldo` y `liquidacion_final` (períodos `especial`, que no cierran la
  asistencia). El aguinaldo suma las líneas de haberes con `afecta_base_aguinaldo` de las corridas cerradas no
  rectificadas del año y resta lo ya pagado (conceptos con `aplicacion='aguinaldo'`). La liquidación final usa los
  conceptos con `aplicacion='liquidacion_final'` y las variables ANIOS_ANTIGUEDAD, ANIOS_INDEMNIZACION, DIAS_PREAVISO,
  CORRESPONDE_PREAVISO, CORRESPONDE_INDEMNIZACION y SALDO_VACACIONES, calculadas con los parámetros de PY-EGRESO.
- **Reportes y exportaciones**: un reporte nuevo se agrega con el decorador `@reporte(...)` en `core/reportes.py`
  (permiso, filtros, columnas; filtrar siempre con `alcance.filtrar`). Toda exportación pasa por `core/exportar.py`.
- **Tablero**: `core/tablero.py` (`GET /api/tablero/?agrupar=mes|total|departamento|sucursal|centro_costo|empleado&por_mes=1`)
  suma por bloques (nómina cerrada, licencias, asistencia, dotación); cada bloque exige su permiso y no viene si falta.
  Un indicador nuevo se suma en el bloque y en `METRICAS` de `frontend/src/pages/Tablero.tsx`. Los gráficos
  (`components/Graficos.tsx`) usan la paleta `SERIES` en orden fijo (validada para daltonismo): no agregar colores sueltos.
- **Dirección de ingreso por empresa**: `Empresa.direccion_acceso` → `rrhh.koapesystem.com/<dirección>` (ruta
  `/:direccion` del frontend, la última antes del comodín: las rutas fijas tienen prioridad). `GET /api/acceso/<dirección>/`
  da nombre y marca sin sesión; `POST /api/sesion/ingresar/` con `empresa` solo acepta usuarios de esa empresa (o la
  plataforma). Las palabras reservadas están en `plataforma.models.DIRECCIONES_RESERVADAS`: si se agrega una ruta de
  primer nivel al frontend, sumarla ahí.
- **Identidad y personalización**: la identidad de Koape (logo y colores del
  logo) es la de la plataforma y la de toda empresa sin la suya. Cada empresa
  puede cargar logo y colores principal/secundario (`Empresa.marca()`); la
  sesión los manda y `frontend/src/marca.ts` reemplaza las variables CSS
  `--marca` / `--marca-secundario` (toda la paleta `marca-*` se recalcula en
  `index.css`). En el frontend nunca se usan colores fijos de Tailwind para la
  marca (`teal-*`, etc.): siempre `marca-*` o `acento-*`.
- **Patrón de apps "sin tabla"** (`migracion/`): `MigracionBaseDatos` y
  `ManualUsuario` (`managed = False`) solo existen para tener su entrada en el
  admin.
- **Manuales**: el del administrador de plataforma en
  `backend/migracion/templates/admin/migracion/manual.html`; el de la
  aplicación en `frontend/src/pages/Manual.tsx` (ruta `/manual`). Cada
  sección nueva suma su entrada en el mismo trabajo.
- **Desarrollo sin fricción**: con `DEBUG=True` se aceptan todos los hosts y
  orígenes CORS; el frontend arma la URL de la API desde el host desde el que
  se abre (`VITE_API_URL` solo si está seteada). Con `DEBUG=False` se exige la
  lista explícita y la `SECRET_KEY`.
- **Windows**: `start.ps1 stop` usa `taskkill /PID <pid> /T /F` (mata el árbol
  completo). Los `.ps1` van sin tildes (PowerShell 5.1 los lee como ANSI) y los
  `.sh` con finales LF (`.gitattributes`).
- **Monitoreo de Visitas**: no se incluye (opcional; sistema interno).

## Migración de Base de Datos y Backup (app `migracion`)

En `/admin/` → **Migración de Base de Datos → Migración** (solo superusuarios):
backup completo en `.zip` (código, `media/`, `privado/`, base SQLite y `pg_dump`
si corre en PostgreSQL; sin `venv/`, `node_modules/`, `__pycache__/`, `dist/`,
`.vite/`, `staticfiles/`, `.run/`, `logs/` ni rastros del repositorio), migrar
a PostgreSQL, volver a SQLite y traer los datos de PostgreSQL a SQLite. Por
terminal: `manage.py migrate_to_postgres --dbname rrhh_db --user rrhh_user --password '...'`.

## Variables de entorno (`backend/.env`)

| Variable | Para qué |
|---|---|
| `SECRET_KEY` | La generan los instaladores; obligatoria con `DEBUG=False` |
| `CLAVE_CIFRADO` | Clave Fernet de los números de cuenta. La generan los instaladores **una sola vez**; si se pierde o cambia, esos números no se pueden leer. Obligatoria con `DEBUG=False` |
| `DEBUG` | `True` en desarrollo, `False` en producción |
| `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` | Hosts y orígenes permitidos (solo con `DEBUG=False`) |
| `SECURE_SSL_REDIRECT` | `False` mientras no haya certificado HTTPS |
| `CSRF_TRUSTED_ORIGINS` | Orígenes HTTPS desde los que se entra al admin |
| `URL_APP` | Dirección pública de la aplicación (enlaces del manual del admin) |
| `ADMIN_HOSTS` | `host:puerto` por los que responde el admin; vacío = sin restricción |
| `IMPORTACION_MAX_BYTES` / `IMPORTACION_MAX_FILAS` | Tamaño (por defecto 5 MB) y filas (50.000) máximos de un CSV de marcaciones |
| `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Base de datos (`sqlite` por defecto) |

Frontend (`frontend/.env`): `VITE_API_URL`, vacía = mismo host, puerto 8004.

## Pruebas

```powershell
cd backend
venv\Scripts\python manage.py test          # Windows
venv/bin/python manage.py test              # Linux
```

Escenario compartido (dos empresas, sucursales, un usuario por perfil) en
`backend/core/datos_prueba.py`.
