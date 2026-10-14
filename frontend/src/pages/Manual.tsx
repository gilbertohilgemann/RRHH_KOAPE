import type { ReactNode } from 'react'
import { tieneAlcanceGeneral, tienePermiso } from '../permisos'
import { useSesion } from '../services/sesionContexto'

/** Manual de usuario de la aplicación (solo con sesión iniciada). Cada
 * pantalla nueva suma su sección acá en el mismo trabajo, no después
 * (Convenciones-de-Proyecto.txt). Cada uno ve las secciones de lo que puede usar. */

function Seccion({ numero, titulo, children, abierta }: { numero: number; titulo: string; children: ReactNode; abierta?: boolean }) {
  return (
    <details open={abierta} className="rounded-xl bg-white shadow-sm ring-1 ring-stone-200">
      <summary className="cursor-pointer px-4 py-3 font-semibold text-stone-900">{numero}. {titulo}</summary>
      <div className="space-y-2 border-t border-stone-100 px-4 py-3 text-sm leading-relaxed text-stone-700">{children}</div>
    </details>
  )
}

const Tip = ({ children }: { children: ReactNode }) => (
  <p className="rounded-lg border-l-4 border-marca-600 bg-marca-50 px-3 py-2">💡 {children}</p>
)
const Aviso = ({ children }: { children: ReactNode }) => (
  <p className="rounded-lg border-l-4 border-orange-600 bg-orange-50 px-3 py-2">⚠ {children}</p>
)

export default function Manual() {
  const { usuario } = useSesion()
  const general = tieneAlcanceGeneral(usuario)
  const administra = tienePermiso(usuario, 'cuentas.gestionar_usuarios')
  let n = 0

  return (
    <div className="mx-auto max-w-3xl space-y-3">
      <h1 className="text-2xl font-bold text-stone-900">Manual de uso</h1>
      <p className="text-sm text-stone-600">Tocá cada tema para abrirlo. Ves solo lo que corresponde a tu perfil.</p>

      <Seccion numero={++n} titulo="Entrar y salir" abierta>
        <p>Entrá con el usuario y la contraseña que te dio el administrador de tu empresa. Para cerrar la sesión usá
          <strong> Salir</strong>, arriba a la derecha: se cierra en todos los dispositivos donde la tenías abierta.</p>
        <p>Tu empresa puede tener su <strong>dirección de ingreso propia</strong>, con su logo y sus colores (por ejemplo
          <code> rrhh.koapesystem.com/delacosta</code>): guardala en favoritos. Por esa dirección solo entran los usuarios de tu empresa;
          al salir, volvés a ella.{usuario?.empresa?.direccion_acceso ? ` La de tu empresa es /${usuario.empresa.direccion_acceso}.` : ''}</p>
        <p>El menú de la izquierda agrupa las pantallas por tema (Personal, Jornada, Asistencia, Licencias, Nómina, Reportes,
          Estructura, Administración): tocá el nombre del grupo para desplegar o cerrar
          sus opciones. El grupo de la pantalla que estás viendo se abre solo, y el sistema recuerda cuáles dejaste abiertos.</p>
        <p>En el celular, el menú se abre con el botón ☰ de arriba a la izquierda.</p>
        <Aviso>Después de 10 intentos fallidos en un minuto, el sistema te pide esperar. Cada intento queda registrado.</Aviso>
      </Seccion>

      {usuario?.empleado && (
        <Seccion numero={++n} titulo="Mi ficha">
          <p>En <strong>Mi ficha</strong> ves tus datos personales y laborales, en qué sucursal, departamento y puesto
            estuviste asignado, tu horario, tus contratos, tus sueldos, tus documentos (los podés descargar) y tus cuentas bancarias. No podés modificarlos: si algo está mal, pedíselo a Recursos Humanos.</p>
        </Seccion>
      )}

      {general && (
        <Seccion numero={++n} titulo="Empleados (legajos)">
          <p>En <strong>Personal → Empleados</strong> está la lista de legajos. Podés buscar por nombre, código o
            documento, y filtrar por estado, sucursal y fecha de ingreso. Tocá una fila para ver el legajo.</p>
          {tienePermiso(usuario, 'empleados.add_empleado') && (
            <p>Para cargar uno nuevo, <strong>Nuevo</strong>. El código de empleado y el documento no se pueden repetir
              dentro de la empresa.</p>
          )}
          <p>Cada vez que cambia la sucursal, el departamento, el puesto, el centro de costo o el supervisor, el
            sistema lo guarda solo en el <strong>historial de asignaciones</strong>, que se ve debajo del legajo.</p>
          {tienePermiso(usuario, 'empleados.dar_baja_empleado') && (
            <>
              <p><strong>Dar de baja</strong>: debajo del legajo, con la fecha de egreso y el motivo. El legajo no se
                borra nunca: queda en gris en la lista y se puede <strong>reactivar</strong> (también con motivo).</p>
              <Tip>Las observaciones internas solo las ven Administración y RR. HH.; el empleado no.</Tip>
            </>
          )}
        </Seccion>
      )}

      {general && (
        <Seccion numero={++n} titulo="Legajo: contratos, sueldos, documentos y cuentas">
          <p>Debajo de la ficha de cada empleado están sus <strong>contratos</strong>, su <strong>historial salarial</strong>,
            sus <strong>documentos</strong> y sus <strong>cuentas bancarias</strong>. El botón <em>Nuevo</em> de cada sección ya
            trae elegido al empleado.</p>
          <ul className="list-disc pl-5">
            <li><strong>Contratos</strong>: se cargan en <em>borrador</em> (se pueden corregir) y se <em>activan</em>. Al activarlo
              pasa a vigente y su salario queda como el primer sueldo del historial. Un contrato vigente ya no se edita: se
              <em> finaliza</em> con fecha y motivo. Un borrador que no corresponde se <em>anula</em>. No puede haber dos contratos
              vigentes superpuestos para el mismo empleado.</li>
            <li><strong>Historial salarial</strong>: un aumento o cambio se carga como <em>pendiente</em> con su fecha de vigencia y
              motivo, y rige recién cuando alguien con permiso lo <em>aprueba</em>: el sueldo anterior se cierra solo el día antes.
              Un sueldo aprobado no se modifica; se corrige cargando otro.</li>
            <li><strong>Documentos</strong>: PDF o fotos (JPG, PNG, WEBP) de hasta 10 MB. Se guardan privados y cada descarga queda
              registrada. Los de tipo <em>confidencial</em> (certificados médicos) solo los ven quienes tienen ese permiso y el propio
              empleado. No se borran: se <em>anulan</em> con motivo.</li>
            <li><strong>Cuentas bancarias</strong>: el número se guarda cifrado y en pantalla se ven solo los últimos 4 dígitos.
              <em> Ver número completo</em> (con permiso) lo muestra y queda en la auditoría.</li>
          </ul>
          <Tip>En <strong>Estructura</strong> están los esquemas salariales y los tipos de documento. Los marcados
            "De Koape" son comunes a todas las empresas y no se modifican; podés crear los tuyos.</Tip>
        </Seccion>
      )}

      {tienePermiso(usuario, 'asistencia.marcar_con_qr') && usuario?.empleado && (
        <Seccion numero={++n} titulo="Ingreso / egreso por QR">
          <ol className="list-decimal space-y-1 pl-5">
            <li>En la entrada hay una pantalla con un <strong>QR que cambia</strong> cada pocos segundos.</li>
            <li>En tu celular, con tu sesión iniciada, entrá a <strong>Ingreso / egreso por QR</strong>, tocá <em>Escanear QR</em> y
              apuntá a la pantalla. (Si tu empresa lo pide, antes elegí <em>Entrada</em> o <em>Salida</em>.)</li>
            <li>Listo: tu celular y la pantalla muestran tu legajo, tu nombre, la hora con segundos y tu foto.</li>
          </ol>
          <Tip>Si la cámara no abre dentro de la aplicación, escaneá el QR con la cámara normal de tu teléfono: abre la aplicación y la
            marca se registra sola.</Tip>
          <Aviso>Escaneá el QR que ves en el momento: una foto del QR no sirve, porque cambia apenas alguien lo usa. Cada marca queda
            registrada a tu nombre.</Aviso>
        </Seccion>
      )}

      {general && (
        <Seccion numero={++n} titulo="Asistencia: marcador, terminales y códigos">
          <ul className="list-disc pl-5">
            <li><strong>Marcaciones</strong>: todas las entradas y salidas, con el método (QR, código fijo…), la terminal y cómo se
              verificó. No se editan ni se borran.</li>
            <li><strong>Incidencias</strong>: cuando la secuencia no cierra (dos entradas seguidas, una salida sin entrada) la marca queda
              igual y se genera una incidencia para revisar. Al resolverla, anotá qué se hizo.</li>
            <li><strong>Intentos rechazados</strong>: QR vencidos o ya usados, códigos desconocidos, marcas repetidas. Muchos códigos
              desconocidos seguidos bloquean la terminal unos minutos.</li>
          </ul>
          {tienePermiso(usuario, 'asistencia.change_terminalmarcacion') && (
            <>
              <p><strong>Instalar una terminal</strong> (TV, monitor o tablet en la entrada, conectada a la red):</p>
              <ol className="list-decimal space-y-1 pl-5">
                <li>En <strong>Asistencia → Terminales</strong> creá la terminal y tocá <em>Generar clave de la terminal</em>. La clave se
                  muestra una sola vez: copiala.</li>
                <li>En el dispositivo abrí la aplicación en <code>/terminal</code> (ej. <code>http://servidor:5204/terminal</code>),
                  pegá la clave y tocá <em>Vincular</em>. Queda funcionando sin usuario y proyecta el QR.</li>
                <li>Los empleados lo escanean con su celular; la pantalla muestra a cada uno con su foto unos segundos.</li>
              </ol>
              <p>Para que la foto salga, cargala en el legajo de cada empleado (sección <em>Foto</em>).</p>
              <p>Si se pierde o roban el dispositivo, desactivá la terminal o generá una clave nueva: la anterior deja de valer.</p>
              <p><strong>Códigos fijos</strong>: en <strong>Asistencia → Códigos fijos</strong> (o desde el legajo) se genera el código de
                cada empleado. Se muestra al generarlo; después solo con <em>Ver código</em>. Si se pierde, <em>Revocar</em> y generar
                otro.</p>
              <Aviso>El código fijo es práctico pero puede compartirse: identifica el código, no prueba quién lo presenta. El QR
                dinámico, escaneado desde la sesión del empleado, es más seguro.</Aviso>
              <p>En <strong>Configuración del marcador</strong> se habilitan las modalidades, cada cuántos segundos cambia el QR, si
                cambia apenas alguien lo usa (recomendado), si se pide elegir entrada o salida, y los segundos mínimos entre dos marcas.</p>
            </>
          )}
        </Seccion>
      )}

      {usuario?.empleado && tienePermiso(usuario, 'asistencia.view_diaasistencia') && !general && (
        <Seccion numero={++n} titulo="Mi asistencia y correcciones">
          <p>En <strong>Mi asistencia</strong> ves tus últimos 31 días: entrada, salida, horas trabajadas, tardanzas y horas extra. Tocá un
            día para ver tus marcas y cómo se calculó.</p>
          <p>Si te olvidaste de marcar o marcaste mal, tocá <em>Pedir corrección de marca</em>: indicá la hora real y el motivo. Queda pendiente
            hasta que Recursos Humanos la apruebe; tu marca original nunca se modifica.</p>
        </Seccion>
      )}

      {general && tienePermiso(usuario, 'asistencia.view_diaasistencia') && (
        <Seccion numero={++n} titulo="Asistencia diaria, ajustes y horas extra">
          <p>En <strong>Asistencia → Asistencia diaria</strong> está cada día de cada empleado: horas programadas y trabajadas, tardanza,
            salida anticipada, horas extra candidatas y autorizadas, nocturnas y el estado (presente, incompleto, ausente, franco, feriado, licencia).
            Tocá un día para ver <em>cómo se calculó</em>, sus marcas e incidencias.</p>
          <ul className="list-disc pl-5">
            <li>Se recalcula sola al marcar, al importar y al aprobar ajustes u horas extra. Después de cambiar horarios o feriados, o para
              ver las ausencias de días sin marcas, usá <em>Calcular período</em>.</li>
            <li>El almuerzo entre dos tramos (ej. 12 a 13) se descuenta si no se marcó; las marcas faltantes nunca se inventan: ese tramo no suma
              horas y queda una incidencia.</li>
            <li><strong>Horas extra</strong>: lo trabajado de más es solo <em>candidato</em>. Se paga lo que se autoriza en <em>Asistencia → Horas
              extra</em> (desde el día, botón <em>Autorizar horas extra</em>).</li>
            <li><strong>Ajustes de marcación</strong>: para agregar una marca que faltó o anular una errónea. Al aprobarse se crea la marca
              nueva (o se anula la errónea, sin borrarla) y el día se recalcula. Los empleados también pueden pedirlos.</li>
          </ul>
          <Tip>Marcá los días como <em>revisados</em> a medida que los controlás: si después cambian (una marca nueva, un ajuste), vuelven a
            quedar sin revisar.</Tip>
          <Aviso>El horario nocturno (20:00 a 06:00) y los demás valores legales están marcados "a verificar" hasta cargar las reglas legales
            de la fase 8.</Aviso>
        </Seccion>
      )}

      {usuario?.empleado && tienePermiso(usuario, 'licencias.view_solicitudlicencia') && !general && (
        <Seccion numero={++n} titulo="Mis licencias y vacaciones">
          <p>En <strong>Mis licencias</strong> ves tus días de vacaciones disponibles, los devengados y los tomados, y todas tus licencias.</p>
          <p>Para pedir vacaciones, un permiso de unas horas u otra licencia tocá <em>Pedir licencia o vacaciones</em>: elegí el tipo y las
            fechas (para un permiso por horas, el mismo día con la hora de inicio y de fin). Los días los calcula el sistema según tu horario
            y los feriados. Queda <em>pendiente</em> hasta que Recursos Humanos la apruebe; mientras tanto la podés corregir o cancelar.</p>
          <Tip>Si es un reposo médico, entregá el certificado a Recursos Humanos: lo cargan en tu legajo.</Tip>
        </Seccion>
      )}

      {general && tienePermiso(usuario, 'licencias.view_solicitudlicencia') && (
        <Seccion numero={++n} titulo="Licencias, permisos y vacaciones">
          <ul className="list-disc pl-5">
            <li><strong>Licencias → Licencias y permisos</strong>: cargá la licencia (o revisá la que pidió el empleado) y tocá
              <em> Aprobar</em> o <em>Rechazar</em> (con motivo). Los días se calculan solos: hábiles según el horario del empleado y sin
              feriados, o corridos, según el tipo. Dos licencias del mismo empleado no se pueden superponer.</li>
            <li>Al aprobar <strong>vacaciones</strong> se descuentan del saldo (si no alcanza, no se aprueba). Los días de una licencia aprobada
              quedan como <em>Licencia</em> en la asistencia: no son ausencias. Un <strong>permiso por horas</strong> aprobado justifica la llegada
              tarde o la salida anticipada en esa franja.</li>
            <li>Los tipos que exigen documento (reposo, maternidad, duelo…) piden elegir el comprobante ya cargado en el legajo antes de
              aprobar. Los <strong>certificados médicos</strong> se registran con fechas, emisor y número, nunca el diagnóstico.</li>
            <li><strong>Saldo de vacaciones</strong>: muestra el saldo de cada empleado. <em>Generar devengo anual</em> suma los días de cada
              aniversario del último año según la <em>Escala de vacaciones</em> (no duplica si se toca dos veces). Los saldos anteriores al sistema
              se cargan con un <em>Ajuste</em>.</li>
            <li>Cancelar una licencia aprobada devuelve los días con una corrección: los movimientos nunca se borran.</li>
          </ul>
          <Aviso>Los tipos de licencia (días de duelo, matrimonio, maternidad, paternidad) y la escala de vacaciones (12, 18 y 30 días) vienen
            como <em>referencia sin verificar</em>: revisalos contra la norma vigente. Cada empresa puede crear sus propios tipos y su propia escala.</Aviso>
        </Seccion>
      )}

      {usuario?.empleado && tienePermiso(usuario, 'nomina.view_recibosueldo') && !general && (
        <Seccion numero={++n} titulo="Mis recibos de sueldo">
          <p>En <strong>Mis recibos</strong> están tus recibos publicados. Tocá uno para ver cada concepto (sueldo, horas extra, IPS, descuentos)
            con su explicación, e imprimirlo o guardarlo en PDF con <em>Imprimir o guardar en PDF</em>.</p>
        </Seccion>
      )}

      {general && tienePermiso(usuario, 'nomina.view_corridanomina') && (
        <Seccion numero={++n} titulo="Liquidar la nómina">
          <ol className="list-decimal space-y-1 pl-5">
            <li>Creá el <strong>período</strong> en <em>Nómina → Períodos de nómina</em> (ej. 2026-10, del 01/10 al 31/10).</li>
            <li>Antes de calcular: asistencia del período calculada, novedades y horas extra aprobadas, contratos y sueldos al día.</li>
            <li><em>Nómina → Liquidaciones → Nuevo</em>: elegí el período y tocá <em>Calcular</em>. Se puede recalcular las veces que haga falta.</li>
            <li>Revisá los totales, las advertencias y cada empleado (tocalo para ver cada línea con <em>cómo se calculó</em>). En rojo, los que
              tienen errores (sin contrato, sin sueldo, sin regla): bloquean la aprobación.</li>
            <li><em>Marcar como revisada</em> → <em>Aprobar</em> → <em>Cerrar</em>. Al cerrar se aplican las novedades y las cuotas, se guarda
              el costo del empleador y se cierra el período: ya no se modifica.</li>
            <li><em>Emitir recibos</em> (numerados), <em>Publicar recibos</em> (cada empleado ve el suyo) y <em>Registrar pagos</em> (a la cuenta
              principal de cada uno); después confirmá cada pago en <em>Pagos de nómina</em>.</li>
          </ol>
          <ul className="list-disc pl-5">
            <li>Si después de cerrar aparece un error, <em>Rectificar</em> (con motivo) crea otra liquidación enlazada que rehace el período con
              los datos corregidos; se paga solo la diferencia y la original queda como estaba.</li>
            <li><strong>Costo del empleador</strong>: por centro de costo, departamento, sucursal o empleado. La provisión de aguinaldo se
              muestra aparte y no suma al costo.</li>
            <li><strong>Empleados sin IPS</strong>: en el legajo, desmarcá <em>Aporta al IPS</em>. Se liquida igual, pero sin el aporte del
              trabajador ni el del empleador (su liquidación lo avisa) y no figura en la planilla del IPS.</li>
          </ul>
          <Aviso>Si las reglas legales o las fórmulas que usa la liquidación no están aprobadas, la liquidación es una <em>simulación</em>:
            sirve para revisar los números, pero no se puede aprobar.</Aviso>
        </Seccion>
      )}

      {general && tienePermiso(usuario, 'nomina.view_corridanomina') && (
        <Seccion numero={++n} titulo="Aguinaldo y liquidación final">
          <ul className="list-disc pl-5">
            <li><strong>Aguinaldo</strong>: en <em>Liquidaciones → Nuevo</em>, sección <em>Aguinaldo</em>, elegí el año. Toma lo que cuenta para el
              aguinaldo en las nóminas cerradas del año y descuenta lo ya pagado (por ejemplo, en una liquidación final). Conviene cerrar antes
              la nómina de diciembre. Después sigue el mismo camino: revisar, aprobar, cerrar, recibos y pagos.</li>
            <li><strong>Liquidación final</strong>: dá de baja el legajo, cargá las novedades pendientes y, en <em>Nómina → Liquidaciones
              finales</em>, cargá la fecha de egreso, la causal y si se otorgó el preaviso. <em>Calcular y revisar la liquidación</em> arma
              el salario pendiente, las vacaciones no gozadas, el aguinaldo proporcional y, si la causal lo dice, el preaviso y la
              indemnización; descuenta lo que falte de anticipos y préstamos. Cada línea explica su cálculo.</li>
            <li>Mientras el empleado tenga liquidación final, la nómina regular no lo incluye (cobra en la final).</li>
          </ul>
          <Aviso>Qué causales llevan preaviso o indemnización, los días por antigüedad y la fracción de año vienen como referencia sin
            verificar (Nómina → Reglas legales → PY-EGRESO). Revisalos con un profesional antes de aprobarlos.</Aviso>
        </Seccion>
      )}

      {general && tienePermiso(usuario, 'cumplimiento.view_presentacionoficial') && (
        <Seccion numero={++n} titulo="Planillas MTESS / IPS">
          <p>En <strong>Nómina → Planillas MTESS / IPS → Nuevo</strong> elegí la planilla (IPS mensual; MTESS anual de sueldos y jornales o de
            empleados y obreros) y el período. Se arma con las nóminas cerradas y valida a cada empleado: en rojo, lo que falta en su legajo
            (número de asegurado IPS, cédula, sexo, fecha de nacimiento…). Corregí los legajos y tocá <em>Preparar de nuevo</em>.</p>
          <p>Bajala en CSV o Excel, presentala en el sistema del organismo y registrá el número de comprobante con <em>Registrar la
            presentación</em>. Si la rechazan, quedá constancia del motivo.</p>
          <Aviso>El formato del archivo es una propuesta: verificalo contra el sistema oficial (REI del IPS, planillas del MTESS) antes de usarlo.</Aviso>
        </Seccion>
      )}

      {general && (
        <Seccion numero={++n} titulo="Reportes">
          <p>En <strong>Reportes</strong> elegí el reporte (nómina por concepto o por empleado, horas y asistencia, contratos por vencer,
            cambios salariales, anticipos y préstamos, vacaciones, base del aguinaldo, legajos, importaciones de marcas), ajustá los filtros y
            exportalo a CSV o Excel. Cada uno muestra solo lo que tu perfil puede ver; las exportaciones quedan en la auditoría.</p>
        </Seccion>
      )}

      {usuario?.empleado && tienePermiso(usuario, 'novedades.view_anticipo') && !general && (
        <Seccion numero={++n} titulo="Mis anticipos y descuentos">
          <p>En <strong>Mis anticipos y descuentos</strong> ves tus anticipos y préstamos (con lo que falta descontar), tus descuentos autorizados
            y tus conceptos fijos.</p>
          <p>Para pedir un adelanto de sueldo tocá <em>Pedir un anticipo</em>: indicá el monto, el motivo y en cuántas cuotas se descuenta.
            Queda <em>solicitado</em> hasta que Recursos Humanos lo apruebe y te lo pague.</p>
        </Seccion>
      )}

      {general && tienePermiso(usuario, 'novedades.view_novedad') && (
        <Seccion numero={++n} titulo="Novedades, anticipos, préstamos y descuentos">
          <ul className="list-disc pl-5">
            <li><strong>Nómina → Novedades</strong>: comisiones (concepto COMISION, con la base de ventas y el %: el importe se calcula solo),
              bonos (BONO) y otros movimientos del período. Quedan <em>pendientes</em> hasta aprobarlas; aprobadas, las toma la liquidación.
              Una novedad ya aplicada en una nómina no se anula: se corrige con una rectificación.</li>
            <li><strong>Anticipos</strong>: se aprueban (por lo solicitado), se registra el pago con la referencia de la transferencia y se generan
              solas las cuotas de recuperación. Los empleados también pueden pedirlos.</li>
            <li><strong>Préstamos</strong>: con la autorización firmada del empleado (documento del legajo) se aprueban; <em>Ver plan de cuotas</em>
              muestra cada cuota; al desembolsar se generan. Con interés mensual, la cuota es fija (sistema francés).</li>
            <li>Si el empleado paga aparte lo que falta, <em>El saldo se pagó aparte</em> cierra las cuotas pendientes sin borrarlas.</li>
            <li><strong>Descuentos autorizados</strong>: cuota sindical, embargo, compras… Siempre con el documento de autorización (o la orden
              judicial) y la autorización escrita del empleado (salvo embargos).</li>
            <li><strong>Cuotas a descontar</strong>: qué se descuenta cada mes. La nómina marca cada cuota una sola vez.</li>
          </ul>
        </Seccion>
      )}

      {general && tienePermiso(usuario, 'legal.view_conjuntoreglas') && (
        <Seccion numero={++n} titulo="Reglas legales, conceptos y fórmulas">
          <ul className="list-disc pl-5">
            <li><strong>Nómina → Reglas legales</strong>: salario mínimo, recargos, divisores y tasas de IPS, cada uno con su fuente oficial y
              su vigencia. Pasan por <em>Borrador → Revisado → Aprobado</em>: quien aprueba tiene que ser otra persona que quien revisó. Una vez
              aprobado no se edita: para un cambio (ej. un salario mínimo nuevo) usá <em>Crear versión nueva</em> con la fecha desde la que vale;
              al aprobarla, la anterior se cierra sola el día antes.</li>
            <li>Las reglas de Koape las mantiene Koape. La empresa puede cargar las suyas (ej. un convenio colectivo): tienen prioridad.</li>
            <li><strong>Parámetros vigentes</strong>: qué valor rige en una fecha y de dónde sale. Solo los aprobados valen para liquidar;
              <em> Simular</em> muestra también los borradores.</li>
            <li><strong>Conceptos de nómina</strong>: haberes, descuentos y aportes, y a qué afectan (neto, aguinaldo, vacaciones, IPS, costo
              del empleador). El aporte del empleador nunca se descuenta del neto del trabajador.</li>
            <li><strong>Reglas de cálculo</strong>: la fórmula de cada concepto, con su vigencia. Se escribe con variables en MAYÚSCULAS (ej.
              <code> VALOR_HORA * HORAS_EXTRA_DIURNAS * (1 + RECARGO_EXTRA_DIURNA / 100)</code>), operaciones, comparaciones,
              <code> A if CONDICIÓN else B</code> y <code>min</code>, <code>max</code>, <code>abs</code>, <code>redondear</code>.
              <em> Probar con valores de ejemplo</em> muestra el resultado sin guardar nada. Aprobada no se edita.</li>
            <li><strong>Conceptos fijos</strong>: un bono, viático o descuento que se repite para un empleado (también desde su legajo). Si el
              concepto exige aprobación, no se aplica hasta aprobarlo; para terminarlo, <em>Finalizar</em> con fecha y motivo.</li>
          </ul>
          <Aviso>Los parámetros, tasas, conceptos y fórmulas que trae el sistema son una <em>referencia en borrador, sin verificar</em>.
            Hasta que alguien los revise contra las fuentes oficiales (MTESS, IPS, Código del Trabajo) y otra persona los apruebe, la
            nómina real queda bloqueada; solo se puede simular.</Aviso>
        </Seccion>
      )}

      {tienePermiso(usuario, 'asistencia.add_loteimportacion') && (
        <Seccion numero={++n} titulo="Importar marcaciones desde un archivo CSV">
          <p>Para relojes de otras marcas o sistemas que entregan las marcas en un archivo.</p>
          <ol className="list-decimal space-y-1 pl-5">
            <li><strong>Una sola vez</strong>: en <em>Asistencia → Relojes externos</em> cargá el reloj, y en <em>Códigos de reloj</em> qué
              empleado es cada código del reloj (también desde el legajo). En <em>Perfiles de importación</em> se indica cómo leer el
              archivo: separador, codificación, qué columna es cada dato y el formato de la fecha (ej. <code>%d/%m/%Y %H:%M:%S</code>).</li>
            <li>En <em>Asistencia → Importar marcaciones → Nuevo</em> elegí el reloj, el perfil y el archivo. <em>Vista previa</em> muestra las
              primeras filas tal como se leen, con el número de cada columna.</li>
            <li><em>Validar archivo</em> revisa todas las filas <strong>sin crear marcas todavía</strong>: cada una queda válida, rechazada (con el
              motivo: código desconocido, fecha con otro formato, empleado que no trabajaba ese día…) o duplicada.</li>
            <li>Revisá el resultado y tocá <em>Confirmar e importar</em>: se crean solo las marcas de las filas válidas.</li>
          </ol>
          <Tip>Las filas no importadas se descargan en CSV o Excel (botones <em>Errores</em>) para corregirlas y volver a importar. Volver a
            importar el mismo archivo no duplica marcas.</Tip>
          <Aviso>Las marcas de un archivo no se verifican en persona: el archivo es la fuente que entrega quien lo sube, y queda registrado
            quién fue. Si se importó un archivo equivocado, <em>Revertir importación</em> (con motivo) anula sus marcas sin borrarlas.</Aviso>
        </Seccion>
      )}

      {general && (
        <Seccion numero={++n} titulo="Jornada: horarios, asignaciones y feriados">
          <ul className="list-disc pl-5">
            <li><strong>Horarios</strong>: cada uno tiene uno o varios <em>tramos</em> por día (ej. 08:00–12:00 y 13:00–17:00).
              <em> Copiar el lunes a martes–viernes</em> ahorra cargar la semana entera. Si la hora "hasta" es menor que
              "desde" (22:00–06:00), el tramo termina al día siguiente: es un turno noche. Dos tramos no se pueden superponer.
              El sistema muestra el resumen, las horas por semana y avisa si se pasan del máximo del régimen.</li>
            <li><strong>Asignación de horarios</strong>: qué horario tiene cada empleado desde una fecha. Si ya tenía uno sin fecha
              de fin, se cierra solo el día anterior. También se ve y se carga desde el legajo de cada empleado.</li>
            <li><strong>Feriados</strong>: el calendario nacional lo carga Koape y es común a todas las empresas. Cada empresa
              puede crear el suyo con feriados locales o días propios.</li>
            <li><strong>Regímenes de jornada</strong>: diurna, nocturna y mixta, con sus máximos de horas por día y por semana.</li>
          </ul>
          <Aviso>Los máximos de los regímenes y el calendario nacional vienen como <em>referencia sin verificar</em>: revisalos
            contra la norma y el decreto del año (algunos feriados se trasladan) antes de usarlos para liquidar.</Aviso>
        </Seccion>
      )}

      {general && (
        <Seccion numero={++n} titulo="Estructura: sucursales, departamentos, puestos y centros de costo">
          <p>En <strong>Estructura</strong> se cargan las sucursales, los departamentos (con de quién dependen y su
            responsable), los puestos y los centros de costo, que después se eligen en cada legajo.</p>
          <p>Las sucursales no se borran: se desmarcan como <em>activas</em>. Un departamento, puesto o centro de costo
            que ya tiene empleados tampoco se puede borrar; desactivalo.</p>
        </Seccion>
      )}

      {administra && (
        <Seccion numero={++n} titulo="Usuarios y perfiles">
          <p>En <strong>Administración → Usuarios</strong> se crean los usuarios de tu empresa y se les asignan
            perfiles:</p>
          <ul className="list-disc pl-5">
            <li><strong>Administrador</strong>: todo dentro de la empresa (usuarios, sucursales, altas y bajas de empleados, auditoría).</li>
            <li><strong>Gestor RR. HH.</strong>: consulta legajos y carga y revisa movimientos; no da de alta ni de baja empleados ni usuarios.</li>
            <li><strong>Empleado</strong>: solo ve lo suyo. Hay que elegir su <em>legajo</em>.</li>
          </ul>
          <p><strong>Limitado a las sucursales</strong>: si marcás alguna, ese usuario solo ve los empleados de esas
            sucursales. Sin marcar = todas.</p>
          <Aviso>No podés cambiarte tus propios perfiles ni desactivarte: lo tiene que hacer otro administrador.
            Los usuarios no se borran: se desmarca <em>Activo</em>.</Aviso>
        </Seccion>
      )}

      {tienePermiso(usuario, 'plataforma.change_empresa') && (
        <Seccion numero={++n} titulo="Datos de la empresa">
          <p>En <strong>Administración → Datos de la empresa</strong> se corrigen la razón social, el RUC y los
            números patronales de IPS y MTESS, que después salen en los recibos y en las planillas oficiales.</p>
          <p><strong>Personalización</strong>: la empresa puede usar su propia identidad en vez de la de Koape.</p>
          <ul className="list-disc pl-5">
            <li><strong>Logo</strong>: abajo de la ficha, <em>Subir logo</em> (PNG, JPG o WEBP de hasta 2 MB, mejor con fondo
              transparente). Se ve en el encabezado de todos los usuarios de la empresa, con el nombre de la empresa.</li>
            <li><strong>Color principal y secundario</strong>: en la sección <em>Personalización</em>. El principal se usa en
              botones y menú, el secundario en la franja de arriba. <em>Volver al de Koape</em> los deja como estaban.</li>
          </ul>
          <Tip>Los demás usuarios ven los cambios la próxima vez que entran o al volver a la pestaña (en unos minutos).</Tip>
          <Aviso>Si el color principal es muy claro, el sistema no lo acepta: el texto blanco de los botones no se leería.</Aviso>
        </Seccion>
      )}

      {tienePermiso(usuario, 'core.view_eventoauditoria') && (
        <Seccion numero={++n} titulo="Auditoría">
          <p>En <strong>Administración → Auditoría</strong> queda todo lo que se hizo: altas, cambios (con el valor
            anterior y el nuevo), bajas, ingresos y cambios de perfiles, con quién y cuándo. No se puede modificar
            ni borrar.</p>
        </Seccion>
      )}
    </div>
  )
}
