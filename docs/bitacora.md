# Bitácora de cambios

Qué se cambió, cuándo y por qué. Lo más reciente arriba.

## 14/10/2026 — Despliegue en el VPS (Fedora) y admin también en el dominio

- `deploy/fedora/` adaptado de KOAPE-PORCINO para `hhrr.koapesystem.com` (mismo VPS que PORCINO, usuario
  `webuser`, carpeta `/home/webuser/HHRR_KOAPE`): gunicorn en 127.0.0.1:8014, admin por IP en el puerto 8006,
  `CLAVE_CIFRADO` generada una sola vez, la app usa `/api` en el mismo dominio, backup diario y cálculo nocturno de la
  asistencia. El servidor se preparó con SQLite (el PostgreSQL del VPS es compartido: se pasará con
  `4-migrar-a-postgres.sh`, que no toca `pg_hba.conf`).
- **Admin también en `https://hhrr.koapesystem.com/admin/`** (pedido del cliente), además de la ip:puerto: nginx lo
  pasa a gunicorn y `ADMIN_HOSTS` lleva el dominio. `2-instalar-app.sh` lo suma solo a un `.env` ya existente.

## 14/10/2026 — Repositorio en GitHub y dirección de ingreso propia por empresa

- **GitHub**: repositorio privado `gilbertohilgemann/RRHH_KOAPE` (rama `main`). Igual que PORCINO: se lee por HTTPS y
  se sube por SSH con una clave propia del repositorio (`~/.ssh/id_ed25519_koape_rrhh_push`, alias `github-koape-rrhh`,
  publicada como deploy key con escritura). Los `.gitignore` excluyen `.env`, la base, `privado/`, `backups/`, `venv`
  y `node_modules`. La contraseña inicial fija del superusuario (convención de PORCINO) está en el código: el
  repositorio tiene que seguir siendo privado y en el servidor se cambia al entrar.
- **Dirección de ingreso por empresa** (pedido del cliente): `Empresa.direccion_acceso` (única, minúsculas, números y
  guiones; no puede ser una palabra que usa el sistema: admin, api, ingresar, terminal…). `hhrr.koapesystem.com/<dirección>`
  muestra el logo, el nombre y los colores de esa empresa (`GET /api/acceso/<dirección>/`, público, solo nombre y
  marca, con límite de pedidos) y por ahí solo entran sus usuarios (y la plataforma); si no corresponde, el mismo
  mensaje que una contraseña errónea, y queda en la auditoría. Sin dirección (o con una inexistente), el ingreso
  estándar de Koape. Al salir o al vencer la sesión se vuelve a la dirección por la que se entró. La asigna la
  plataforma (el administrador de la empresa la ve pero no la cambia). La demo usa `/demo`.
- `frontend/.env.production` (`VITE_API_URL=/api`) para el servidor, donde nginx sirve la aplicación y la API en el
  mismo dominio.
- **Pruebas**: 282, todas OK (3 nuevas).

## 14/10/2026 — Fase 11: aguinaldo, liquidación final, planillas MTESS/IPS y reportes

- **Aguinaldo**: liquidación de tipo "aguinaldo" en un período especial del año (`liquidar.crear_aguinaldo`). Toma,
  de las nóminas cerradas del año (sin las rectificadas), los haberes que cuentan para el aguinaldo
  (TOTAL_REMUNERACIONES_ANIO), aplica la regla del concepto AGUINALDO y descuenta lo ya pagado en el año (por ejemplo,
  en una liquidación final). Avisa si faltan meses cerrados. No lleva los conceptos automáticos. Los períodos
  especiales no cierran la asistencia del año.
- **Liquidación final** (`LiquidacionFinal` + corrida de tipo "liquidación final"): período especial desde el día
  siguiente a la última nómina cerrada del empleado hasta el egreso. Salario pendiente con el cálculo regular,
  vacaciones no gozadas (saldo × valor del día; al cerrar salen del saldo con un movimiento), preaviso e
  indemnización según la causal y la antigüedad (con parámetros legales, no constantes), aguinaldo proporcional y el
  saldo completo de anticipos y préstamos (con aviso). La nómina regular excluye a quien tiene liquidación final; no
  se calcula si el empleado está en una nómina sin cerrar. El aguinaldo y la liquidación final se rectifican con su
  mismo tipo.
- **Datos de referencia EN BORRADOR, SIN VERIFICAR**: conjunto global PY-EGRESO (preaviso 30/45/60/90 días por
  antigüedad; causales con preaviso e indemnización: despido injustificado; 15 días de indemnización por año; fracción
  de 6 meses = año) y conceptos VACACIONES_CAUSADAS, PREAVISO e INDEMNIZACION con sus reglas en borrador.
- **App nueva `cumplimiento`**: planillas oficiales (IPS mensual de aportes; MTESS anual de sueldos y jornales y de
  empleados y obreros) armadas desde las nóminas cerradas, con validación por empleado (falta el número de asegurado,
  la cédula, el sexo, la fecha de nacimiento…; salario imponible por debajo del mínimo), exportación a CSV/Excel y
  registro de presentación (con comprobante), rechazo o anulación. Con errores no se registra la presentación.
  PROPUESTA: el formato de cada sistema oficial tiene que verificarse.
- **Reportes** (`core/reportes.py`, `/api/reportes/`): nómina por concepto y por empleado, horas y asistencia,
  contratos por vencer, cambios salariales, anticipos y préstamos, vacaciones, base del aguinaldo, legajos e
  importaciones de marcas. Cada uno con su permiso y el aislamiento por empresa, sucursal y empleado; exportación a
  CSV/Excel con `core/exportar.py` (protegida contra fórmulas; las exportaciones quedan en la auditoría). El perfil
  Empleado no tiene reportes generales.
- **Permisos** (`FASE_11`): Administrador todo; Gestor prepara liquidaciones finales y planillas (no registra la
  presentación).
- **Frontend**: Liquidaciones finales (con "Calcular y revisar la liquidación", que lleva a la corrida), aguinaldo en
  "Calcular una liquidación", Planillas MTESS / IPS (detalle con errores por empleado y exportación) y el grupo
  Reportes con filtros, vista previa y exportación. Las acciones pueden llevar a otra pantalla con la respuesta.
- **Red**: la PC cambió de IP por DHCP (192.168.1.36 → 192.168.1.45): se actualizó `URL_APP` en `backend/.env` para el
  QR de la terminal (y CLAUDE.md).
- **Pruebas**: 279, todas OK (10 nuevas). Prueba de humo contra el servidor: 10 reportes para el administrador y
  ninguno para el empleado, legajos del gestor, Excel generado, planilla MTESS de empleados con sus advertencias, el
  gestor no puede registrar la presentación.

## 14/10/2026 — Fase 10: nómina (períodos, cálculo, cierre, rectificación, recibos, pagos y costo del empleador)

- **Modelos** (app `nomina`): `PeriodoNomina`, `CorridaNomina` (calculada → revisada → aprobada → cerrada; anulada;
  la rectificación es otra corrida enlazada), `LiquidacionEmpleado` (días, minutos, bruto, descuentos, aportes, neto,
  aportes y costo del empleador, provisión de aguinaldo aparte, advertencias y errores), `LineaNomina` (concepto con
  copia de código/nombre/tipo, cantidad, tasa, base, importe con signo, regla, origen y explicación), `PagoNomina`,
  `ReciboSueldo` (numeración correlativa por empresa y año con `SecuenciaDocumento`, tomada con bloqueo) y
  `AsignacionCostoPatronal`. `ConceptoNomina.aplicacion` dice si el concepto lo calcula la nómina sola (por su regla),
  solo por novedades, en el aguinaldo o en la liquidación final.
- **Motor** (`nomina/motor.py`): contrato y sueldo aprobado vigentes (sin ellos, error que bloquea la aprobación);
  días activos; asistencia del período (ausencias no justificadas, licencias no pagas, extras AUTORIZADAS separadas en
  diurnas, nocturnas y en feriado o descanso, horas nocturnas); valor del día según la base del esquema (mensual,
  quincenal, semanal, jornal, por hora; comisión/destajo/mixta como mensual con aviso); conceptos automáticos con sus
  reglas, conceptos fijos, novedades aprobadas, BASE_IPS, aportes, descuentos autorizados (con su tope total) y cuotas.
  Cada importe con su explicación. Recalcular reemplaza las liquidaciones: no duplica nada.
- **Bloqueos** (§8 y §9): si usa reglas legales o de cálculo sin aprobar, la corrida es una SIMULACIÓN y no se
  aprueba; con un empleado con errores, tampoco. Separación opcional de quien calcula y quien aprueba.
- **Cierre** (`nomina/liquidar.py`): marca las novedades y cuotas como aplicadas una sola vez, pone los anticipos y
  préstamos sin saldo como recuperados/cancelados, guarda el costo del empleador y cierra el período.
  `periodo_cerrado()` ya no es un gancho vacío: la asistencia, la importación y las licencias respetan los períodos
  cerrados. Cerrada, la liquidación no se recalcula ni se anula: se **rectifica** (otra corrida enlazada, con motivo,
  que rehace el período con los datos actuales; se paga la diferencia; la original queda intacta y marcada).
- **Recibos y pagos**: recibos numerados (R2026-000001…) desde la corrida cerrada; publicados, cada empleado ve los
  suyos, sin el aporte ni el costo del empleador; pantalla para imprimir o guardar en PDF desde el navegador (sin
  librerías nuevas). Pagos por transferencia a la cuenta principal, con confirmación o anulación.
- **Costo del empleador**: informe por centro de costo, departamento, sucursal o empleado; la provisión de aguinaldo
  va aparte y no suma (§4.6).
- **Permisos** (`FASE_10`): Administrador todo; Gestor prepara períodos, calcula, revisa y emite recibos (no aprueba,
  cierra, rectifica, paga ni ve el costo del empleador); Empleado, sus recibos publicados.
- **Frontend**: Liquidaciones (calcular, detalle con totales, advertencias, acciones según estado y permiso, y el
  desglose por empleado con la explicación de cada línea), Períodos, Recibos (imprimibles), Pagos, Costo del empleador
  y "Mis recibos" del empleado. Manuales actualizados.
- **Pruebas**: 269, todas OK (13 nuevas: mensual completo con IPS separados, ausencias, solo extras autorizadas,
  novedades/cuotas/anticipo recuperado, simulación bloqueada, errores bloquean, cierre definitivo, rectificación con
  diferencia, recibos numerados, pagos, permisos y otra empresa). Prueba de humo con la demo: 8 empleados calculados
  como simulación (reglas en borrador), explicación por línea, aprobación bloqueada, el gestor no ve el costo.

## 14/10/2026 — Fase 9: novedades, descuentos autorizados, anticipos y préstamos

- **App nueva `novedades`**: `Novedad` (movimiento de un período con concepto, cantidad, tasa o monto; pendiente →
  aprobada / rechazada → aplicada por la nómina; aplicada no se anula: se rectifica), `DescuentoAutorizado` (cuota
  sindical, embargo, compra…; siempre con documento de autorización o la orden judicial, y autorización escrita del
  empleado salvo embargos), `Anticipo` (solicitado → aprobado con monto → pagado → recuperado), `Prestamo` (aprobar
  exige la autorización firmada; cuota fija, con interés mensual opcional por sistema francés) y `CuotaRecuperacion`
  (una por mes; el saldo es la suma de las pendientes; únicas por anticipo/préstamo y número para que nunca se
  descuenten dos veces). "El saldo se pagó aparte" deja las cuotas pendientes como pagadas aparte, sin borrarlas.
- **Decisión**: comisiones y bonos son novedades de los conceptos COMISION (base de ventas × %) y BONO (monto), en
  lugar de tablas aparte; la comisión calcula su importe sola.
- **Conceptos nuevos** (globales): CUOTA_SINDICAL, EMBARGO_JUDICIAL y DESCUENTO_AUTORIZADO.
- **Permisos** (`FASE_9`): Administrador carga, aprueba, paga y desembolsa; Gestor carga (no aprueba ni paga);
  Empleado ve lo suyo y pide anticipos para sí. Separación opcional de quien carga y quien aprueba.
- **Frontend**: módulos Novedades, Anticipos, Préstamos (con "Ver plan de cuotas"), Descuentos autorizados (todos
  también en el legajo) y Cuotas a descontar; "Mis anticipos y descuentos" del empleado con "Pedir un anticipo"; las
  acciones admiten otra etiqueta para el texto (ej. "Referencia de la transferencia"). Manuales actualizados.
- **Pruebas**: 256, todas OK (14 nuevas). Prueba de humo contra el servidor: el empleado pide un anticipo en 2 cuotas,
  el gestor no puede aprobarlo, el administrador lo aprueba y lo paga, se generan las 2 cuotas y el empleado las ve.

## 14/10/2026 — Fase 8: reglas legales versionadas y conceptos salariales

- **App nueva `legal`**: `ConjuntoReglas` (versión de un conjunto de parámetros con fuente oficial, vigencia y estado
  borrador → revisado → aprobado → retirado; global de Koape o propio de una empresa, que tiene prioridad),
  `ParametroLegal` (valor numérico, de texto o estructurado, unidad, vigencia propia opcional, referencia) y
  `RegimenSeguridadSocial` (tasas del trabajador y del empleador). `legal/servicios.py` resuelve el valor vigente en
  una fecha; para liquidar solo valen los aprobados (`ReglaNoAprobada` explica qué falta), para simular también los
  borradores, con advertencia. Aprobar exige otra persona que la que revisó (cuatro ojos, PROPUESTA); aprobado no se
  edita: "Crear versión nueva" lo copia como borrador y, al aprobarla, cierra la vigencia de la anterior si no tenía fin.
- **App nueva `nomina`** (por ahora sin liquidar): `ConceptoNomina` (haber, descuento, aporte del trabajador, aporte
  del empleador, informativo; a qué bases afecta; un aporte del empleador nunca afecta el neto), `ReglaConcepto`
  (condición + fórmula con vigencia, redondeo, prioridad y aprobación; aprobada no se edita) y `ConceptoRecurrente`
  (conceptos fijos de un empleado, con aprobación si el concepto la exige y finalización con fecha y motivo).
- **Fórmulas seguras** (`nomina/expresiones.py`): análisis con `ast`, nunca `eval`; solo números, variables en
  MAYÚSCULAS, operaciones, comparaciones, `A if C else B` y `min/max/abs/redondear`; cálculo con Decimal.
  **Redondeo centralizado** en `nomina/redondeo.py` (al guaraní por defecto). "Probar" calcula una regla con valores
  de ejemplo (`nomina/variables.py`) y los parámetros legales, sin guardar nada.
- **Datos de referencia EN BORRADOR, SIN VERIFICAR**: conjunto PY-LABORAL desde el 01/07/2026 (salario mínimo
  3.044.000 y jornal 117.077 que reporta la especificación, recargos de horas extra 50 % / 100 %, nocturno 30 %,
  feriado 100 %, divisores, bonificación familiar 5 %, horario nocturno 20–06) e IPS general 9 % / 16,5 %; 15
  conceptos y 9 reglas de referencia. Nada vale para liquidar hasta que se verifique y se apruebe.
- **Permisos** (`FASE_8`): Administrador carga, revisa y aprueba reglas legales propias, conceptos, reglas de cálculo
  y conceptos fijos; Gestor consulta la configuración y carga conceptos fijos (no los aprueba); Empleado ve sus
  conceptos fijos. Las reglas globales solo las toca la plataforma. Separación opcional de quien carga y quien aprueba
  (la misma opción de la empresa que en licencias y horas extra).
- **Frontend**: grupo "Nómina" (conceptos fijos —también en el legajo—, conceptos, reglas de cálculo con "Probar",
  reglas legales con parámetros y regímenes en filas, parámetros vigentes en una fecha); acción de tipo "resultado";
  el editor de filas acepta decimales y fechas vacías. Manuales actualizados.
- **Pruebas**: 242, todas OK (25 nuevas, entre ellas fórmulas peligrosas rechazadas y acceso por perfil y empresa).
  Prueba de humo contra el servidor: sin aprobados no hay parámetros vigentes; simulando, 16 con advertencia;
  "Probar" de IPS del trabajador = 315.000 sobre 3.500.000.

## 14/10/2026 — Fase 7: licencias, permisos, vacaciones y certificados médicos

- **App nueva `licencias`**: `TipoLicencia` (catálogo global + de cada empresa: paga, descuenta vacaciones, exige
  documento, días hábiles o corridos, permisos por horas, máximo de días, fuente legal y verificado),
  `SolicitudLicencia` (pendiente → aprobada / rechazada / cancelada; días calculados en el servidor; sin
  superposiciones), `MovimientoVacaciones` (el saldo es la suma; nunca se editan ni se borran), `EscalaVacaciones`
  (días por antigüedad) y `CertificadoMedico` (sin diagnóstico).
- **Reglas** (`licencias/servicios.py`): aprobar valida saldo y documento y genera el goce; cancelar una aprobada
  devuelve los días con una corrección (y respeta `periodo_cerrado()`); devengo por aniversario idempotente.
- **Motor de asistencia**: el día con licencia aprobada queda en estado `licencia` (nuevo, con enlace a la licencia; no
  es ausencia ni genera horas extra); un permiso por horas corre el inicio o el fin del tramo para la tardanza y la
  salida anticipada. Aprobar o cancelar recalcula los días ya pasados.
- **Datos de referencia SIN VERIFICAR** (migración `licencias/0002`): vacaciones, reposo médico, maternidad (126 días),
  paternidad (14), duelo (3), matrimonio (3), examen y permiso particular sin goce; escala 12 / 18 / 30 días (1–5, 5–10,
  10 o más años). Cada uno con su fuente; hay que revisarlos.
- **API**: `tipos-licencia`, `escala-vacaciones`, `licencias` (+ `aprobar`, `rechazar`, `cancelar`; el empleado pide y
  cancela solo lo suyo pendiente; separación opcional de quien carga y quien aprueba), `movimientos-vacaciones`
  (+ `saldo`, `saldos`, `devengar`; a mano solo ajustes, vencimientos y correcciones), `certificados-medicos`.
- **Permisos** (`FASE_7`): Administrador y Gestor cargan, aprueban, devengan y ajustan (el Gestor solo consulta tipos y
  escala); Empleado pide licencias para sí y ve su saldo y sus certificados.
- **Frontend**: grupo "Licencias" en el menú (licencias y permisos, saldo de vacaciones con devengo anual, certificados,
  tipos, escala; también en el legajo), "Mis licencias" del empleado, estado "Licencia" en la asistencia. Demo: devengo
  del último aniversario y vacaciones aprobadas de Lucía en diciembre. Manuales actualizados.
- **Pruebas**: 217, todas OK (20 nuevas, 4 de acceso por perfil, sucursal y otra empresa en `cuentas/tests.py`). Prueba de humo contra el servidor: el empleado pide un permiso por horas y
  vacaciones, no puede aprobar; el gestor aprueba y cancela; saldos de todos los empleados.

## 14/10/2026 — Fase 6: motor de asistencia, ajustes y horas extra

- **Modelos** (app `asistencia`): `DiaAsistencia` (resultado por empleado y día, con explicación, versión y revisión),
  `AjusteMarcacion` (agregar o anular marcas, con aprobación), `AutorizacionHorasExtra`; `IncidenciaAsistencia` suma
  tipos (tardanza, salida anticipada, ausencia, marca faltante, extra sin autorizar, trabajo en franco/feriado),
  minutos, estado "justificada" y marca de automática; `ConfiguracionMarcacion` suma horario nocturno (dato a
  verificar), mínimos de extra y de salida anticipada, y separación de quien pide y quien aprueba.
- **Motor** (`asistencia/motor.py`): horario, feriado y marcas vigentes en la fecha; asignación de marcas a días de
  trabajo (turnos de noche); pares; descuento del hueco entre tramos y del descanso no marcado; tardanza con
  tolerancia; salida anticipada; ordinario / extra candidato / autorizado; nocturnas; estados; incidencias
  automáticas que respetan las resueltas; explicación línea por línea. Recalcula solo al marcar, importar, revertir
  y aprobar; `manage.py calcular_asistencia`.
- Durante las pruebas se encontraron y corrigieron dos errores del propio motor: el almuerzo programado se descontaba
  aunque el empleado no hubiera trabajado en ese horario, y el hueco entre tramos no se descontaba si se marcaba solo
  entrada y salida. Ahora el descuento es por lo trabajado dentro del descanso.
- **API**: `dias-asistencia` (+ `calcular`, `revisar`, detalle con marcas e incidencias), `ajustes-marcacion` y
  `autorizaciones-extra` (+ `aprobar`, `rechazar`; el empleado pide solo para sí).
- **Permisos** (`FASE_6`, migración `asistencia/0009`): Administrador todo; Gestor calcula, revisa, carga y aprueba
  ajustes, carga horas extra (no las aprueba); Empleado ve su asistencia y pide correcciones.
- **Frontend**: "Asistencia diaria" (filtros, calcular período), detalle del día (números, explicación, marcas
  tachadas si están anuladas, incidencias, accesos para corregir y autorizar), "Mi asistencia" del empleado, módulos
  de ajustes y horas extra (también en el legajo), campo de fecha y hora. Manuales actualizados.
- **Corrección de fechas**: las entradas de las fases 4 y 5 y del QR invertido decían 15/10/2026; eran del 14/10/2026
  (corregido en la bitácora, el plan, el README y los comentarios del código).
- **Pruebas**: 197, todas OK (23 nuevas). Prueba de humo contra el servidor: período calculado (112 días), detalle
  con explicación, el empleado ve solo sus días, una marca por QR recalcula el día sola.

## 14/10/2026 — Fase 5: importación de marcaciones CSV

- **Modelos** (app `asistencia`): `RelojExterno`, `MapeoEmpleadoReloj` (código del reloj → empleado, con vigencia y
  sin superposición), `PerfilImportacion` (separador, codificación, encabezado, columnas por nombre o número,
  formatos explícitos, valores de entrada/salida, id de evento, zona horaria, modo reloj externo / predefinido /
  confiado, versión), `LoteImportacion` (archivo privado, SHA-256, perfil y versión, período, contadores, estados) y
  `FilaImportacion` (cada fila con su resultado y motivo). `Marcacion` suma `lote_importacion`, `reloj` y anulación
  lógica; su huella pasa a ser única solo entre marcas no anuladas.
- **Lógica** (`asistencia/importacion.py`): vista previa sin guardar; validación de cada fila con motivo (código
  desconocido, formato de fecha, futura, fuera del período, empleado fuera de su período laboral, tipo no reconocido,
  faltan columnas); duplicados por huella o id de evento dentro del archivo y contra lo importado; reimportación
  idempotente con aviso; confirmación transaccional; reversión que anula sin borrar (con el control de nómina cerrada
  preparado para la fase 10); errores en CSV/XLSX con protección contra fórmulas; límites de tamaño y filas.
- **API**: `relojes-externos`, `codigos-reloj`, `perfiles-importacion`, `importaciones` (+ `vista_previa`,
  `confirmar`, `cancelar`, `revertir`, `errores`) y `filas-importacion`.
- **Permisos** (`FASE_5`, migración `asistencia/0007`): Administrador todo; Gestor importa, confirma y corrige códigos
  de reloj, pero no configura perfiles ni revierte.
- **Frontend**: "Importar marcaciones" (vista previa con número de columna) y el detalle del lote (resumen, filas
  filtrables, descargas de errores, confirmar / cancelar / revertir); módulos de relojes, códigos de reloj (también en
  el legajo) y perfiles. Manuales actualizados.
- **Arreglo**: el serializador base agregaba "creado por/modificado por" a modelos sin esos campos (el listado de
  intentos rechazados habría fallado); ahora los omite, con prueba.
- Demo: reloj "Reloj del depósito", su perfil y los códigos 101–108; archivo `docs/ejemplos/marcaciones_reloj_demo.csv`
  (80 marcas válidas de 5 días y 4 filas con problemas a propósito).
- **Pruebas**: 174, todas OK (23 nuevas: coma / punto y coma, con y sin encabezado, UTF-8 / Latin-1, fecha y hora
  juntas o separadas, fecha ambigua, turno noche, código desconocido, empleado de baja, fila inválida, duplicados,
  reimportación, lote parcial, reversión, permisos). Prueba de humo contra el servidor con el archivo de ejemplo:
  80 válidas, 3 rechazadas, 1 duplicada; reimportado: 0 válidas, 81 duplicadas.

## 14/10/2026 — El QR no abría en el celular

**Problema**: al escanear el QR de la terminal, el celular no abría la aplicación.
**Causas**: (1) error de código: el QR armaba el enlace con la dirección desde la que se abrió la terminal; abierta
como `localhost` en la PC, el teléfono intentaba abrir su propio "localhost". (2) En esta PC el firewall de Windows
(red marcada "Pública") no dejaba entrar a los puertos 5204/8004 desde otros dispositivos. Además la PC está en
dos redes (WiFi Casa 2 = 192.168.1.36, Ingenio-Gilgemann = 192.168.2.3).
**Arreglo**: `GET /api/terminal/yo/` devuelve `url_app` (de `URL_APP` en el .env, o el host pedido cambiando
localhost por la IP de la red local) y la terminal arma el QR con eso y lo muestra debajo ("Abre …"); prueba nueva
`test_el_enlace_del_qr_nunca_es_localhost`. En esta PC: `URL_APP=http://192.168.1.36:5204` en `backend/.env`
(la red del celular, elegida por el cliente) y regla de firewall "Koape RRHH (red local)": entrada TCP 5204 y
8004 solo desde la red local (`LocalSubnet`), creada con permiso de administrador del cliente.
**Seguía sin abrir**: el firewall que manda en esta PC es el de **AVG Antivirus** (registrado como firewall de
Windows, servicio "AVG Firewall Service"), que bloqueaba la red por estar marcada "Pública". Se marcó "WiFi Casa 2"
como red **Privada** en Windows (`Set-NetConnectionProfile`, con permiso de administrador) y AVG dejó pasar al
celular: el cliente entró a la aplicación desde el teléfono.
**Verificado por el cliente con su celular real**: QR proyectado en `/terminal` (PC), escaneado con la cámara del
teléfono → `/marcar/<token>` → marca registrada y mostrada en ambas pantallas. Pendiente: HTTPS para que el botón
"Escanear QR" dentro de la aplicación pueda usar la cámara (por HTTP el navegador no la habilita).

## 14/10/2026 — QR invertido: la terminal proyecta, el empleado escanea

**Pedido del cliente**: invertir la modalidad A. El servidor genera un QR dinámico que se proyecta en la pantalla
de la terminal; el empleado, con su sesión iniciada en el celular, lo escanea desde "Ingreso / egreso por QR"; al
registrarse, ambas pantallas muestran legajo, nombre, hora:minuto:segundo y la foto (si tiene).

- `TokenQR` (QR del empleado) se reemplazó por `QRDinamico` (QR de la terminal): cambia cada 20 s (antes 60; las
  configuraciones con el valor anterior pasan a 20 con la migración `0005`) y, con la nueva opción
  `qr_un_solo_uso` (activada por defecto), apenas alguien marca con él, así una foto reenviada no sirve. 10 s de
  gracia después de vencer. Consumo atómico; un rechazo (ej. antirrebote) no gasta el QR.
- API: `GET /api/terminal/qr/?actual=&desde=` (la pantalla, cada segundo: QR vigente —token solo cuando cambia— y
  marcas nuevas), `POST /api/marcador/qr/` (el empleado con su sesión), `GET /api/terminal/foto/<marca>/` (solo la
  de quien marcó en esa terminal, 5 minutos). Se quitaron `mi-qr/` y el `POST /api/terminal/qr/`.
- Permiso `asistencia.solicitar_qr_propio` reemplazado por `asistencia.marcar_con_qr` (migración `0004`).
- **Foto del empleado**: `Empleado.foto` privada (fuera de /media/), achicada a 600 px y sin EXIF; acción
  `GET/POST/DELETE /api/empleados/<id>/foto/` (ver = quien ve el legajo; subir/quitar = quien lo modifica), auditada.
- Frontend: pantalla `/terminal` con el QR grande, cuenta regresiva y la tarjeta de quien marcó (foto, legajo,
  nombre, hora con segundos); "Ingreso / egreso por QR" en el celular con escáner (jsQR) y elección de
  entrada/salida si la empresa lo pide; ruta `/marcar/<token>` para la cámara normal del teléfono (y vuelta a esa
  ruta después de iniciar sesión); sección Foto en el legajo. Manuales actualizados.
- **Pruebas**: 151, todas OK. Prueba de humo contra el servidor: foto subida, QR de la pantalla escaneado, ambas
  pantallas con E003 Lucía Martínez y la hora con segundos, foto servida a la terminal, QR nuevo tras el uso, QR
  usado rechazado.

## 14/10/2026 — Fase 4: marcador propio (QR temporal y código fijo)

- **App `asistencia`**: `ConfiguracionMarcacion` (por empresa), `TerminalMarcacion` (clave propia mostrada una
  sola vez, se guarda su huella), `CredencialMarcacion` (código fijo numérico aleatorio, HMAC para buscarlo + copia
  cifrada para mostrarlo con permiso, revocar/rotar), `TokenQR` (token aleatorio de un solo uso, vence en 60 s
  configurables, solo su huella), `Marcacion` (inmutable; método, verificación, terminal, credencial o QR),
  `IntentoMarcacion` (cada rechazo) e `IncidenciaAsistencia` (secuencias incoherentes; la fase 6 la amplía).
- **Lógica** en `asistencia/marcador.py`: hora del servidor, consumo atómico del QR, legajo bloqueado para marcas
  simultáneas, antirrebote, entrada/salida automática o elegida, incidencia sin tocar marcas, bloqueo de la terminal
  tras 10 intentos desconocidos en 5 minutos. Límites de pedidos: 12 QR/minuto, 120 lecturas/minuto por terminal.
- **API**: empleado (`/api/marcador/mi-qr/`, `mi-qr/<id>/`, `mi-codigo/`, `mi-marcador/`), terminal
  (`/api/terminal/yo|qr|codigo/` con `Authorization: Terminal <clave>`) y RR. HH. (configuración, terminales con
  `generar_clave`, códigos con `revelar`/`revocar`, marcas, intentos e incidencias de solo consulta / revisión).
- **Permisos** (`FASE_4`, migración `asistencia/0002`): Administrador configura terminales y códigos; Gestor
  consulta marcas y resuelve incidencias (no ve terminales ni códigos); Empleado pide su QR y ve sus marcas.
- **Frontend**: "Marcar asistencia" (QR con cuenta regresiva y confirmación del servidor, código propio), pantalla
  de terminal `/terminal` (vinculación con clave, cámara con jsQR o lector USB, teclado, resultado grande, colores y
  logo de la empresa), grupo "Asistencia" (marcaciones, incidencias, terminales, códigos fijos, intentos,
  configuración). Las pantallas con QR se cargan bajo demanda. Nuevas dependencias: `qrcode`, `jsqr`.
- La demo habilita el código fijo, crea la terminal "Entrada principal" (imprime su clave) y el código de Lucía.
- **Pruebas**: 143, todas OK (27 nuevas con los criterios de §6 bis). Prueba de humo contra el servidor: QR pedido,
  leído por la terminal, confirmado en el celular, reutilización rechazada, antirrebote.

## 14/10/2026 — Menú lateral desplegable

**Pedido**: que los títulos de grupo del menú (Personal, Jornada, Estructura, Administración) se comporten como
menú y sus módulos como submenú. `MenuLateral.tsx`: cada grupo es un botón con ícono (`menu.ts → ICONO_GRUPO`)
que despliega o cierra su submenú (con sangría y línea a la izquierda); el grupo de la pantalla abierta se
despliega solo y los grupos abiertos se recuerdan en el navegador (`localStorage`, opcional). En el celular, el
menú se cierra al elegir una opción, no al abrir un grupo. Manual actualizado. `npm run build`: OK.

## 14/10/2026 — Fase 3: jornada, horarios y feriados

- **App `jornada`**: `RegimenJornada` (catálogo; diurna 8 h/48 h, nocturna 7 h/42 h y mixta 7:30 h/45 h
  precargadas como referencia **sin verificar**), `Horario` + `TramoHorario` (varios tramos por día, cruce de
  medianoche, descanso pago o no, tolerancia; tramos superpuestos rechazados, también domingo noche con el lunes;
  advertencias visibles contra los máximos del régimen), `AsignacionHorario` (vigencias sin superponer, la anterior
  abierta se cierra sola; no antes del ingreso) y `CalendarioFeriados` + `DiaFeriado` (nacional 2026 global sin
  verificar + calendarios propios). Funciones `horario_vigente()` y `feriado_en()` para la fase 6, y consulta
  `GET /api/asignaciones-horario/vigente/?empleado=&fecha=`.
- **Común**: `ConAnidadosSerializer` (filas hijas guardadas con el padre en una transacción) y
  `datos_auditoria_extra()` para auditar esas filas.
- **Permisos** (`FASE_3`, migración `jornada/0002`): Administrador configura y asigna; Gestor consulta y asigna
  horarios; Empleado ve su horario y los feriados.
- **Frontend**: grupo "Jornada" (asignaciones, horarios, feriados, regímenes), editor de filas con "copiar el
  lunes a martes–viernes", advertencias del servidor en el formulario, errores por fila; el horario aparece en el
  legajo y en Mi ficha. Manuales actualizados. La demo suma los horarios Oficina y Depósito asignados.
- **Pruebas**: 116, todas OK (20 nuevas). `npm run build`: OK. Prueba de humo contra el servidor: horarios,
  horario del empleado y consulta de un feriado.
- Nota: durante el trabajo el autorecargador del backend se detuvo por un error transitorio de `urls.py` (ruta
  registrada antes de su import, ya corregido); se reinició con `start.ps1 restart`.

## 14/10/2026 — Fase 2: contratos, salarios, documentos y cuentas bancarias

- **App `contratos`**: `EsquemaSalarial` (catálogo global + por empresa; 8 globales precargados),
  `ContratoEmpleado` (borrador → vigente → finalizado / anulado; sin contratos vigentes superpuestos; plazo
  fijo y temporal exigen fin; no antes del ingreso) y `HistorialSalarial` (pendiente → aprobado / anulado;
  activar el contrato abre el primer sueldo; aprobar cierra el anterior el día previo; nunca vigencias
  solapadas; finalizar el contrato cierra el sueldo y anula pendientes). El empleado ve solo sus sueldos aprobados.
- **Documentos del legajo**: `TipoDocumento` (8 globales; "Certificado médico" confidencial) y
  `DocumentoEmpleado` en almacenamiento privado (`core/archivos.py`): contenido real validado, SHA-256,
  nombre aleatorio en disco, descarga auditada, confidenciales solo con permiso o propios, anulación con motivo.
- **Cuentas bancarias**: número cifrado con Fernet (`core/cifrado.py`, nueva variable `CLAVE_CIFRADO` que
  generan `install.sh` / `install.ps1` solo si falta), últimos 4 dígitos para mostrar, `revelar` con permiso
  y auditado, una sola cuenta principal activa por empleado. Nueva dependencia: `cryptography`.
- **Catálogos globales**: `core.models.CatalogoEmpresa` + `CatalogoViewSet` (una empresa no modifica los globales).
- **Permisos**: `cuentas/perfiles.py` organizado por fases (`FASE_1`, `FASE_2`); la migración
  `contratos/0002_datos_iniciales` suma los de la fase 2 a los perfiles existentes (antes, un grupo ya creado
  nunca recibía permisos de módulos nuevos).
- **Frontend**: módulos Contratos, Historial salarial, Documentos, Cuentas (desde el legajo), Esquemas
  salariales y Tipos de documento; sección de legajo debajo de cada empleado y en Mi ficha; acciones por
  registro; campo de archivo (multipart); formularios bloqueados según el estado. Manuales actualizados.
- `cargar_datos_demo` suma un contrato vigente por empleado y una cuenta de ejemplo.
- **Pruebas**: 96, todas OK (32 nuevas). `makemigrations --check`: sin cambios. `npm run build`: OK. Prueba de
  humo contra el servidor: contratos, sueldo visto por el empleado, cuenta enmascarada, subida y descarga de un PDF.

## 13/10/2026 — Identidad de Koape y personalización por empresa

**Pedido**: usar el logo de Koape y permitir que cada empresa se personalice. El manual de marcas no llegó
(solo el logo): los colores salen del logo y quedan centralizados para ajustarlos cuando llegue.

- Logo recortado en `frontend/public/logo-koape.png`, `favicon.png` y `backend/core/static/core/logo-koape.png`.
- Paleta de Koape tomada del logo: principal `#E9264B`, secundario `#F7941D`, degradado
  `#D9418A → #E9264B → #F7941D → #EEF01A` (franja superior). Definida en `frontend/src/index.css`
  (variables `--marca` / `--marca-secundario`, paleta `marca-*` calculada con `color-mix`) y en
  `plataforma/models.py` (`COLOR_PRIMARIO_KOAPE`, `COLOR_SECUNDARIO_KOAPE`).
- Admin con logo, franja y acentos de Koape (`core/static/core/admin-koape.css`).
- **Por empresa**: `Empresa.color_primario`, `color_secundario` (validados #RRGGBB; el principal con
  contraste mínimo 3:1 con texto blanco) y `logo` (acción `POST/DELETE /api/empresas/<id>/logo/`, solo
  PNG/JPG/WEBP de hasta 2 MB, auditada). La sesión trae `marca` y la app la aplica sola (`src/marca.ts`):
  encabezado con el logo y nombre de la empresa; el pie siempre dice "Desarrollado por Koape".
- Pantalla "Datos de la empresa": sección Personalización (colores) y logo con vista previa. Manuales actualizados.
- Pruebas: 64, todas OK (8 nuevas en `plataforma/tests.py`). `npm run build` OK.

## 13/10/2026 — Fase 0 y fase 1: arranque del proyecto

**Fase 0 (diagnóstico)**: la carpeta solo tenía las convenciones y el paquete
técnico; no había repositorio, `Company`, `EventLog`, RBAC ni definiciones XML
que reutilizar. Se tomó `KOAPE-PORCINO` como referencia de estructura e
infraestructura. Decisiones y plan en `docs/plan-fases.md`. El cliente eligió
**nombres en castellano** (como PORCINO) en lugar del inglés con `internalId`
de la especificación.

**Fase 1 (hecho)**:
- Esqueleto `backend/` (Django 5.2 + DRF + Jazzmin) y `frontend/` (React + Vite + TS + Tailwind v4), puertos 8004/5204.
- `core`: `RegistroBase`/`RegistroEmpresa` (auditoría de carga), `EventoAuditoria` (bitácora con valores
  anteriores y nuevos, sin edición ni borrado), `alcance.py` (empresa → sucursal → empleado), API base con
  validación `full_clean`, denegación por defecto (`view_` también para leer) y auditoría automática; sesión
  por token con throttling y auditoría de ingresos (también los fallidos).
- `plataforma`: `Empresa` (RUC, números patronales IPS/MTESS, zona horaria) y `Sucursal`.
- `cuentas`: `Perfil` (empresa, sucursales, legajo); perfiles iniciales Koape, Administrador, Gestor RR. HH.
  y Empleado según la matriz §11 bis; API de usuarios para el Administrador sin autoelevación de
  privilegios ni grupo Koape; `restablecer_perfiles`.
- `empleados`: `Departamento` (jerarquía sin ciclos), `Puesto`, `CentroCosto`, `Empleado` (código y documento
  únicos por empresa, baja lógica y reactivación con motivo, ficha propia sin observaciones internas) e
  `HistorialAsignacion` automático.
- `migracion` (copiada de PORCINO): migración SQLite ⇄ PostgreSQL, backup completo sin rastros del
  repositorio, manual del administrador.
- Frontend: ingreso, panel con indicadores, menú lateral por permisos, listado y formulario genéricos
  (`modulos.ts`), baja/reactivación e historial del empleado, detalle de auditoría, Mi ficha, manual.
- Instaladores y arranque Windows/Linux (de PORCINO, adaptados), `crear_admin`, `cargar_datos_demo`.
- **Pruebas**: 56 pruebas del backend, todas OK (aislamiento entre empresas y sucursales, los tres perfiles,
  Gestor sin altas/bajas/usuarios/configuración, ficha propia, autoelevación, auditoría con valores previos,
  baja lógica, historial, backup sin `.git`, admin por host). `makemigrations --check`: sin cambios.
  `npm run build`: OK. Prueba de humo con `start.ps1`: ingreso, listado, resumen, frontend y admin responden.
