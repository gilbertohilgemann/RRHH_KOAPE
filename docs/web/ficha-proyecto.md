# Ficha para koapesystem.com/proyectos — Koape RR. HH.

Textos para el formulario "Añadir Proyecto / Caso de Éxito". Imágenes: `docs/web/flyers/flyer-1.png` … `flyer-5.png`
(2400×1600, relación 3:2; la 1 es la imagen principal).

## Datos

| Campo | Valor |
|---|---|
| **Título** | Koape RR. HH. — Recursos humanos y nómina |
| **Slug** | koape-rrhh |
| **Cliente** | Koape Sistemas EAS (producto propio) |
| **Tecnologías** | Django, Django REST Framework, React, TypeScript, Tailwind CSS, PostgreSQL, Nginx, QR dinámico |
| **Proyecto internacional** | No |
| **Países con cobertura** | Paraguay |
| **En producción** | Sí |
| **Rol de Koape** | Propio |
| **Link del proyecto** | https://rrhh.koapesystem.com |
| **Destacar en Inicio** | Sí |
| **Año** | 2026 |
| **Orden** | 0 (o el que corresponda junto a los otros productos) |
| **Activo** | Sí |

## Descripción

Koape RR. HH. es un sistema web de recursos humanos y nómina pensado para empresas de Paraguay. Reúne en un solo lugar el
legajo de cada empleado, la asistencia, las licencias, las novedades y la liquidación de sueldos, hasta el recibo, el
aguinaldo, la liquidación final y las planillas para IPS y MTESS.

**Asistencia sin papeles.** La terminal de la empresa muestra un código QR que cambia cada pocos segundos; el empleado lo
escanea con su celular y la marca queda registrada al instante con la hora del servidor, confirmada en las dos pantallas
con su legajo, su nombre y su foto. También admite código fijo y la importación de relojes de otras marcas. Tardanzas,
ausencias, horas nocturnas y horas extra se calculan solas, y las horas extra se pagan solo si están autorizadas.

**Una nómina que se explica.** Cada línea del recibo indica de dónde sale: base, cantidad, tasa y regla aplicada. El
sistema toma sueldos, asistencia, licencias, comisiones, bonos, descuentos autorizados y cuotas de anticipos y préstamos;
la liquidación se revisa, se aprueba y se cierra, y una nómina cerrada no se modifica: se corrige con una rectificación.
Calcula aportes al IPS del trabajador y del empleador por separado, el costo total para la empresa y el aguinaldo, y
arma la liquidación final según la causal y la antigüedad.

**Reglas legales bajo control.** Salario mínimo, recargos y tasas no están escritos en el programa: se cargan como reglas
versionadas, con su fuente, su vigencia y su aprobación.

**Cada empleado, con lo suyo.** Desde el celular, cada persona ve su asistencia, sus recibos y su saldo de vacaciones, y
pide permisos, vacaciones o anticipos, que quedan pendientes hasta que Recursos Humanos los aprueba.

**Multiempresa.** Cada empresa entra por su propia dirección, con su logo y sus colores, y ve solo sus datos, con perfiles
de administrador, gestor de RR. HH. y empleado, y auditoría de cada cambio.

## Buscadores (SEO)

| Campo | Valor |
|---|---|
| **Título para buscadores** (55 car.) | Software de RR. HH. y nómina para empresas en Paraguay |
| **Descripción para buscadores** (156 car.) | Sistema web de recursos humanos y sueldos en Paraguay: asistencia con QR, licencias, nómina explicada, aguinaldo, liquidación final y planillas IPS y MTESS. |
| **Palabras clave** | software de recursos humanos Paraguay, sistema de nómina, liquidación de sueldos, control de asistencia con QR, planilla IPS, MTESS, aguinaldo, liquidación final |
| **Es un producto de software** | Sí |
| **Tipo de software** | Recursos humanos / nómina, si está en la lista; si no, "Gestión empresarial (CRM, ERP, ventas, proyectos)" |

## Imágenes del proyecto

| Orden | Archivo | Principal | Tema |
|---|---|---|---|
| 1 | flyer-1.png | Sí | Recursos humanos y nómina en un solo lugar (panel) |
| 2 | flyer-2.png | | Marcación con QR dinámico (terminal y celular) |
| 3 | flyer-3.png | | Una nómina que se explica sola (recibo) |
| 4 | flyer-4.png | | Autogestión del empleado (licencias y recibos) |
| 5 | flyer-5.png | | Multiempresa y cumplimiento (dirección propia, IPS/MTESS) |

## Preguntas frecuentes

1. **¿Cómo marcan la entrada y la salida los empleados?**
   Con su celular: la terminal de la empresa muestra un QR que cambia cada pocos segundos y el empleado lo escanea desde
   su sesión. La marca queda con la hora del servidor y las dos pantallas la confirman con su nombre y su foto. También se
   puede usar un código fijo o importar los archivos de relojes de otras marcas.

2. **¿Calcula los aportes al IPS y el aguinaldo?**
   Sí. Calcula por separado el aporte del trabajador y el del empleador, el costo total para la empresa, el aguinaldo con
   las remuneraciones del año y la liquidación final según la causal y la antigüedad. Los valores legales se cargan como
   reglas con su fuente y su vigencia.

3. **¿Prepara las planillas para IPS y MTESS?**
   Sí. Arma la planilla mensual del IPS y las anuales del MTESS con los datos de las nóminas cerradas, avisa qué dato falta
   en cada legajo y permite exportarlas a Excel o CSV para presentarlas.

4. **¿Los empleados pueden ver sus recibos y pedir vacaciones?**
   Sí. Cada empleado entra con su usuario y ve solo lo suyo: asistencia, recibos, saldo de vacaciones, anticipos y
   préstamos. Puede pedir licencias, vacaciones o anticipos, que quedan pendientes hasta que Recursos Humanos los aprueba.

5. **¿Sirve para varias empresas o sucursales?**
   Sí. Es multiempresa: cada empresa tiene su propia dirección de ingreso con su logo y sus colores, y ve solo sus datos.
   Dentro de una empresa, un usuario se puede limitar a ciertas sucursales.

6. **¿Qué pasa si una nómina ya cerrada tenía un error?**
   No se modifica: se hace una rectificación enlazada, con motivo, que rehace el período con los datos corregidos y paga
   solo la diferencia. Todo queda registrado en la auditoría.
