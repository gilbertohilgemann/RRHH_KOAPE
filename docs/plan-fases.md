# Koape RR. HH. — Diagnóstico y plan por fases

Fase 0 de la especificación (`Koape_RRHH_Paquete_Tecnico/Especificacion_Tecnica_Koape_RRHH.md` §1 y §15).

## Diagnóstico (13/10/2026)

- **No hay repositorio previo**: la carpeta solo trae las convenciones y el paquete técnico.
  No existen `Company`, `EventLog`, RBAC ni definiciones XML (`PayRoll.modulo.xml`,
  `*.windows.xml`, `record.xml`) que reutilizar: se construye desde cero.
- **Proyecto de referencia**: `KOAPE-PORCINO` (en producción). Se copian su estructura e
  infraestructura: Django 5.2 + DRF + Jazzmin, React + Vite + TS + Tailwind v4, auditoría
  común (`RegistroBase`), aislamiento centralizado (`core/alcance.py`), API genérica,
  perfiles como grupos de Django, app `migracion` (migración SQLite ⇄ PostgreSQL, backup,
  manual) e instaladores Linux/Windows.
- **Puertos**: backend **8004**, frontend **5204** (los otros sistemas de esta PC usan
  8000–8003, 8100 y 5173/5174/5183/5201/5203).

## Decisiones tomadas

| Tema | Decisión | Motivo |
|---|---|---|
| Nombres de tablas y campos | **Castellano**, como PORCINO (`Empleado`, `fecha_ingreso`, PK `id`) | Lo decidió el cliente (13/10/2026). La especificación pedía inglés PascalCase con `internalId` solo "si coincide con el proyecto"; las convenciones exigen castellano |
| Multiempresa | `plataforma.Empresa` + `plataforma.Sucursal`; todo registro transaccional lleva `empresa` y la fija el servidor | §1 de la especificación (nunca confiar en el id del navegador) |
| Usuarios | Usuarios de Django + `cuentas.Perfil` (empresa, sucursales, empleado vinculado) | Reutiliza la identidad de Django, como PORCINO |
| Perfiles | Grupos de Django: **Administrador**, **Gestor RR. HH.**, **Empleado** (+ `Koape` = plataforma) | §11 bis; permisos atómicos = permisos de Django, ajustables desde el admin |
| Alcance de un usuario | Una empresa por usuario; sucursales opcionales (vacío = todas) | Simplifica el aislamiento. Un usuario con varias empresas queda como PROPUESTA |
| Auditoría | `core.EventoAuditoria`: quién, cuándo, qué, valores anteriores y nuevos. Nunca se edita ni se borra | Reemplaza al `EventLog` que la especificación pedía reutilizar (no existe) |
| Bajas | Siempre lógicas (empleados, empresas, sucursales); la API no borra legajos | §4 y §11 bis |
| QR de asistencia (modalidad A) | **Invertido**: la terminal proyecta un QR dinámico que genera el servidor; el empleado lo escanea con su celular, con su sesión iniciada. Ambas pantallas muestran legajo, nombre, hora:min:seg y foto | Lo pidió el cliente (14/10/2026). La especificación tenía el QR en el celular y el lector en la terminal. Para que una foto del QR reenviada no sirva, el QR cambia cada 20 s y apenas alguien lo usa (configurable) |
| Recibos en PDF | Pantalla del recibo para **imprimir o guardar en PDF desde el navegador** | No suma librerías ni instalaciones; un PDF generado en el servidor queda como PROPUESTA (14/10/2026) |
| Corrección de una nómina cerrada | **Rectificación** enlazada (se paga la diferencia); no hay "reabrir" | La especificación pide no sobrescribir históricos; reabrir queda como PROPUESTA (14/10/2026) |
| Comisiones y bonos | Son **novedades** de los conceptos COMISION y BONO (no tablas aparte) | Mismo flujo de carga y aprobación que cualquier novedad; la comisión guarda base y % (14/10/2026) |
| Monitoreo de Visitas | No se incluye | Es opcional en las convenciones y este es un sistema interno |

## Fases

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Esqueleto, infraestructura (migración, backup, manual, instaladores), empresas, sucursales, usuarios y perfiles, aislamiento, auditoría, legajo básico (departamentos, puestos, centros de costo, empleados con baja lógica e historial de asignaciones) | Hecha (13/10/2026) |
| 2 | Contratos, historial salarial (sin vigencias solapadas), documentos del legajo, cuentas bancarias cifradas | Hecha (14/10/2026) |
| 3 | Regímenes de jornada, horarios con tramos, asignación de turnos, calendarios de feriados | Hecha (14/10/2026) |
| 4 | Marcador propio: terminales, QR temporal (modalidad A), código fijo (B), configuración por empresa | Hecha (14/10/2026) |
| 5 | Importación CSV (modalidad C y relojes externos): perfiles, staging, vista previa, deduplicación, errores descargables | Hecha (14/10/2026) |
| 6 | Motor de asistencia: días calculados, incidencias, ajustes manuales aprobados, horas extra autorizadas | Hecha (14/10/2026) |
| 7 | Licencias, permisos y vacaciones (saldo por movimientos), certificados médicos | Hecha (14/10/2026) |
| 8 | Reglas legales versionadas (fuente, vigencia, aprobación) y conceptos salariales | Hecha (14/10/2026) |
| 9 | Novedades: comisiones, bonos, descuentos, anticipos y préstamos con cuotas | Hecha (14/10/2026) |
| 10 | Nómina: períodos, corridas, líneas explicables, cierre, rectificación, pagos, recibos PDF, costo patronal | Hecha (14/10/2026) |
| 11 | Aguinaldo, liquidación final, preparación MTESS/IPS, reportes | Hecha (14/10/2026) |

## Pendientes de definir con el cliente

1. **Verificar** los máximos de jornada de los regímenes y el calendario nacional de feriados 2026 (cargados como referencia sin verificar).
1. **HTTPS** en producción: sin certificado, las terminales no pueden usar la cámara para leer el QR (sí un lector USB).
1. **Horario nocturno** (20:00 a 06:00) configurado como dato a verificar hasta la fase 8.
1. **Verificar** los tipos de licencia (días de duelo, matrimonio, maternidad, paternidad; quién paga el reposo) y la escala de vacaciones (12/18/30 días hábiles), cargados como referencia sin verificar.
1. **Devengo de vacaciones**: hoy lo genera RR. HH. con un botón (*Saldo de vacaciones → Generar devengo anual*); se puede programar también como tarea del servidor.
1. **Programar** `manage.py calcular_asistencia --ayer` cada noche en el servidor (así aparecen las ausencias sin marcas).
1. **Parámetros legales reales** (salario mínimo por categoría, tasas IPS, recargos): ya están cargados como
   referencia en el conjunto PY-LABORAL **en borrador** (Nómina → Reglas legales). Bloquean la liquidación real
   hasta que alguien los verifique con fuentes oficiales y otra persona los apruebe (§9). Salario mínimo por
   categoría: cargar un conjunto por régimen o actividad cuando se definan.
1. **PROPUESTA a confirmar**: aprobar reglas legales exige dos personas (quien revisa y quien aprueba).
1. **Antes de producción, verificar y aprobar** (Nómina → Reglas legales): PY-LABORAL y PY-EGRESO (preaviso,
   indemnización, causales), las reglas de cálculo de referencia y los formatos de las planillas MTESS/IPS contra los
   sistemas oficiales (REI del IPS, planillas del MTESS). Hasta entonces la nómina real queda en simulación.
1. **Empleados sin IPS** (`Aporta al IPS` desmarcado en el legajo): confirmar en qué casos lo admite la normativa
   (por ejemplo, jubilados o regímenes especiales) y si alguno lleva otro aporte en lugar del IPS.
1. **Criterios del egreso a verificar**: base de la indemnización (hoy el valor del día del sueldo vigente, no un
   promedio), descuento del saldo completo de préstamos al egreso, si las vacaciones causadas cuentan para IPS.
1. **Criterios de liquidación a verificar** (con un profesional laboral-contable): pago de feriados a jornaleros
   (hoy se pagan, con aviso), horas extra de un día nocturno como extra nocturna, trabajo en día de descanso con el
   recargo de feriado, divisor de 30 días para el mensual, sueldo de esquemas con comisión como mensual.
1. **Límite de descuentos y cuotas sobre el sueldo**: la fase 10 lo controlará con un parámetro legal o de la empresa
   (definir el tope y si es legal o política interna). Importar comisiones desde un archivo queda como PROPUESTA.
1. **Bonificación familiar**: el concepto existe, pero la regla necesita la cantidad de hijos con derecho, dato
   que el legajo todavía no tiene (definir con el cliente).
2. ¿El sistema corre en un servidor propio o junto a PORCINO en el mismo VPS?
3. ¿Repositorio en GitHub, como PORCINO?
