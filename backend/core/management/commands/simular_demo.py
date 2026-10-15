"""Simula 3 años de historia en la empresa demo (datos ficticios) usando los
mismos servicios que la aplicación, para mostrar el sistema funcionando:

- 20 empleados: 10 con más de 2 años, 5 que ingresaron en el último año y 5
  que ya egresaron, cada uno con su liquidación final.
- Marcaciones de cada día hábil (QR en la oficina, reloj en el depósito), con
  tardanzas, ausencias (algunas justificadas), olvidos de marca corregidos con
  ajustes y horas extra autorizadas; asistencia calculada.
- Aumentos de sueldo cada julio, vacaciones, reposos con certificado, permisos
  por horas, duelo y matrimonio.
- Comisiones de los vendedores, bonos de fin de año y por presentismo,
  viático fijo, bonificación familiar, cuota sindical, anticipos y préstamos.
- Nómina de cada mes desde octubre de 2023 hasta el mes pasado: calculada,
  revisada, aprobada, cerrada, con recibos publicados y pagos confirmados;
  aguinaldos de cada año y planillas IPS / MTESS presentadas.

Como la demo es ficticia, la empresa demo tiene su propio conjunto de reglas
legales y sus reglas de cálculo APROBADOS (copias de las de referencia,
marcadas como ficticias): así sus nóminas no son simulaciones. Las reglas
globales de Koape no se tocan (siguen en borrador hasta verificarlas).

    manage.py cargar_datos_demo --clave '<contraseña>'   (primero)
    manage.py simular_demo

Se corre una sola vez (si ya está simulada, avisa y no hace nada)."""
import hashlib
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from empleados.models import CentroCosto, Departamento, DocumentoEmpleado, Empleado, HistorialAsignacion, Puesto, TipoDocumento
from plataforma.models import Empresa, Sucursal

NOMBRE_EMPRESA = 'Empresa Demo S.A.'
INICIO = date(2023, 10, 1)
ZONA = ZoneInfo('America/Asuncion')
PDF = b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n'

# código, documento, nombre, apellido, sexo, ingreso, sucursal, departamento, puesto, centro, salario, egreso, causal
NUEVOS = [
    ('E009', '9012345', 'Fernando', 'Giménez', 'M', date(2022, 9, 5), 'CEN', 'VEN', 'VEN', 'CC-VEN', 3900000, None, None),
    ('E010', '1122334', 'Patricia', 'Benítez', 'F', date(2023, 3, 13), 'CEN', 'ADM', 'ANA', 'CC-ADM', 5200000, None, None),
    ('E011', '2233445', 'Ramón', 'Cáceres', 'M', date(2023, 6, 1), 'ENC', 'DEP', 'OPE', 'CC-OPE', 125000, None, None),
    ('E012', '3344556', 'Sofía', 'Ayala', 'F', date(2025, 11, 17), 'CEN', 'VEN', 'VEN', 'CC-VEN', 3800000, None, None),
    ('E013', '4455667', 'Marcos', 'Vera', 'M', date(2026, 1, 12), 'ENC', 'VEN', 'CAJ', 'CC-VEN', 3300000, None, None),
    ('E014', '5566778', 'Elena', 'Núñez', 'F', date(2026, 3, 2), 'ENC', 'DEP', 'OPE', 'CC-OPE', 135000, None, None),
    ('E015', '6677889', 'Javier', 'Insfrán', 'M', date(2026, 6, 1), 'CEN', 'RRHH', 'ANA', 'CC-ADM', 5000000, None, None),
    ('E016', '7788990', 'Gabriela', 'Romero', 'F', date(2023, 2, 1), 'CEN', 'VEN', 'VEN', 'CC-VEN', 3700000, date(2024, 6, 15), 'renuncia'),
    ('E017', '8899001', 'Hugo', 'Ledesma', 'M', date(2022, 8, 1), 'ENC', 'VEN', 'CAJ', 'CC-VEN', 3400000, date(2024, 11, 30), 'despido_injustificado'),
    ('E018', '9900112', 'Liliana', 'Ortega', 'F', date(2023, 5, 2), 'ENC', 'DEP', 'OPE', 'CC-OPE', 120000, date(2025, 3, 31), 'mutuo_acuerdo'),
    ('E019', '1029384', 'Óscar', 'Brítez', 'M', date(2024, 9, 2), 'CEN', 'ADM', 'ANA', 'CC-ADM', 4800000, date(2025, 9, 1), 'fin_contrato'),
    ('E020', '5647382', 'Natalia', 'Galeano', 'F', date(2023, 10, 2), 'CEN', 'VEN', 'VEN', 'CC-VEN', 3750000, date(2026, 5, 20), 'despido_justificado'),
]
# Feriados de los años previos al calendario precargado (datos de la demo).
FERIADOS = {
    2023: ['01-01', '03-01', '04-06', '04-07', '05-01', '05-14', '05-15', '06-12', '08-15', '09-29', '12-08', '12-25'],
    2024: ['01-01', '03-01', '03-28', '03-29', '05-01', '05-14', '05-15', '06-12', '08-15', '09-29', '12-08', '12-25'],
    2025: ['01-01', '03-01', '04-17', '04-18', '05-01', '05-14', '05-15', '06-12', '08-15', '09-29', '12-08', '12-25'],
}


def _meses(desde, hasta):
    actual = desde.replace(day=1)
    while actual <= hasta:
        yield actual
        actual = (actual + timedelta(days=32)).replace(day=1)


def _fin_de_mes(primero):
    return (primero + timedelta(days=32)).replace(day=1) - timedelta(days=1)


class Command(BaseCommand):
    help = 'Simula 3 años de historia (20 empleados, nóminas, licencias, novedades, egresos) en la empresa demo.'

    def handle(self, *args, **opciones):
        self.r = random.Random(2026)
        self.hoy = timezone.localdate()
        self.ayer = self.hoy - timedelta(days=1)
        self.empresa = Empresa.objects.filter(nombre=NOMBRE_EMPRESA).first()
        if self.empresa is None:
            raise CommandError('No existe la empresa demo: corré primero manage.py cargar_datos_demo --clave ...')
        if Empleado.objects.filter(empresa=self.empresa, codigo='E020').exists():
            self.stdout.write(self.style.WARNING('La empresa demo ya tiene la historia simulada: no se hace nada.'))
            return
        try:
            self.admin = User.objects.get(username='admin_demo')
            self.gestor = User.objects.get(username='gestor_demo')
        except User.DoesNotExist:
            raise CommandError('Faltan los usuarios demo: corré primero manage.py cargar_datos_demo --clave ...')
        self.plataforma = User.objects.filter(is_superuser=True).order_by('pk').first()
        if self.plataforma is None:
            raise CommandError('Falta el superusuario (manage.py crear_admin).')

        pasos = [
            ('Reglas legales y de cálculo de la demo', self._reglas),
            ('Feriados 2023–2025', self._feriados),
            ('Empleados, contratos y horarios', self._empleados),
            ('Aumentos de sueldo de cada julio', self._aumentos),
            ('Egresos (bajas)', self._bajas),
            ('Vacaciones devengadas', self._devengos),
            ('Licencias y permisos', self._licencias),
            ('Marcaciones, horas extra y ajustes', self._marcaciones),
            ('Asistencia calculada', self._asistencia),
            ('Novedades, conceptos fijos, descuentos, anticipos y préstamos', self._novedades),
            ('Nóminas, aguinaldos y liquidaciones finales', self._nominas),
            ('Planillas IPS / MTESS', self._planillas),
            ('Pendientes del mes en curso', self._pendientes),
        ]
        for titulo, funcion in pasos:
            self.stdout.write(f'==> {titulo}...')
            funcion()
        self.stdout.write(self.style.SUCCESS('Historia de la demo simulada (datos ficticios).'))

    # ------------------------------------------------------------------ apoyo
    def _documento(self, empleado, codigo_tipo, descripcion, emision):
        tipo = TipoDocumento.objects.filter(empresa=None, codigo=codigo_tipo).first() or TipoDocumento.objects.filter(empresa=None).first()
        doc = DocumentoEmpleado(empresa=self.empresa, empleado=empleado, tipo_documento=tipo, descripcion=descripcion,
                                nombre_original=f'{descripcion}.pdf'[:250], tipo_mime='application/pdf', tamano=len(PDF),
                                sha256=hashlib.sha256(PDF + descripcion.encode()).hexdigest(), fecha_emision=emision,
                                confidencial=tipo.confidencial, creado_por=self.gestor, modificado_por=self.gestor)
        doc.archivo.save('demo.pdf', ContentFile(PDF), save=False)
        doc.save()
        return doc

    def _activos(self, fecha):
        return [e for e in self.empleados if e.fecha_ingreso <= fecha and (e.fecha_egreso is None or e.fecha_egreso >= fecha)]

    # --------------------------------------------------------- reglas legales
    def _reglas(self):
        from legal import servicios as legal
        from legal.models import ConjuntoReglas, ParametroLegal, RegimenSeguridadSocial
        from nomina import servicios as nomina
        from nomina.models import ReglaConcepto
        conjunto = ConjuntoReglas.objects.create(
            empresa=self.empresa, codigo='DEMO', nombre='Parámetros de la demostración (ficticios)', vigente_desde=date(2023, 1, 1),
            fuente_nombre='Copia de las referencias de Koape — DATOS FICTICIOS, solo para la demo',
            notas='Aprobado únicamente para que la empresa demo muestre nóminas reales. No usar como fuente legal.',
            creado_por=self.gestor, modificado_por=self.gestor)
        vistos = set()
        for codigo in ('PY-LABORAL', 'PY-EGRESO'):
            origen = ConjuntoReglas.objects.filter(empresa=None, codigo=codigo).order_by('-version').first()
            if origen is None:
                continue
            for p in origen.parametros.all():
                if p.codigo not in vistos:
                    ParametroLegal.objects.create(conjunto=conjunto, codigo=p.codigo, nombre=p.nombre, valor_numerico=p.valor_numerico,
                                                  valor_texto=p.valor_texto, valor_json=p.valor_json, unidad=p.unidad,
                                                  referencia_fuente='Copia ficticia para la demo')
                    vistos.add(p.codigo)
            for r in origen.regimenes.all():
                RegimenSeguridadSocial.objects.get_or_create(conjunto=conjunto, codigo=r.codigo, defaults={
                    'nombre': r.nombre, 'tasa_trabajador': r.tasa_trabajador, 'tasa_patronal': r.tasa_patronal, 'base': r.base})
        legal.revisar(conjunto, self.plataforma)
        legal.aprobar(conjunto, self.admin)
        for regla in ReglaConcepto.objects.filter(empresa=None).exclude(estado=ReglaConcepto.RETIRADA):
            copia = ReglaConcepto.objects.create(
                empresa=self.empresa, concepto=regla.concepto, vigente_desde=date(2023, 1, 1), condicion=regla.condicion,
                expresion=regla.expresion, redondeo=regla.redondeo, prioridad=regla.prioridad,
                notas='Copia aprobada solo para la demo (datos ficticios).', creado_por=self.gestor, modificado_por=self.gestor)
            nomina.aprobar_regla(copia, self.admin)

    def _feriados(self):
        from jornada.models import CalendarioFeriados, DiaFeriado
        for anio, dias in FERIADOS.items():
            calendario, _ = CalendarioFeriados.objects.get_or_create(
                empresa=self.empresa, codigo='DEMO', anio=anio, defaults={'nombre': f'Feriados {anio} (demo)', 'creado_por': self.gestor})
            for dia in dias:
                DiaFeriado.objects.get_or_create(calendario=calendario, fecha=date.fromisoformat(f'{anio}-{dia}'),
                                                 defaults={'nombre': 'Feriado nacional', 'tipo': 'nacional'})
        self.feriados = set(DiaFeriado.objects.filter(calendario__activo=True, calendario__empresa__in=[None, self.empresa])
                            .values_list('fecha', flat=True)) | set(
            DiaFeriado.objects.filter(calendario__activo=True, calendario__empresa__isnull=True).values_list('fecha', flat=True))

    # -------------------------------------------------------------- empleados
    def _empleados(self):
        from contratos.models import ContratoEmpleado, EsquemaSalarial
        from jornada.models import AsignacionHorario, Horario
        mensual = EsquemaSalarial.objects.get(empresa=None, codigo='MENSUAL')
        jornal = EsquemaSalarial.objects.get(empresa=None, codigo='JORNAL')
        oficina = Horario.objects.get(empresa=self.empresa, codigo='OFICINA')
        deposito = Horario.objects.get(empresa=self.empresa, codigo='DEPOSITO')
        sucursales = {s.codigo: s for s in Sucursal.objects.filter(empresa=self.empresa)}
        departamentos = {d.codigo: d for d in Departamento.objects.filter(empresa=self.empresa)}
        puestos = {p.codigo: p for p in Puesto.objects.filter(empresa=self.empresa)}
        centros = {c.codigo: c for c in CentroCosto.objects.filter(empresa=self.empresa)}
        jefa = Empleado.objects.get(empresa=self.empresa, codigo='E001')
        self.egresos = {}
        for codigo, doc, nombre, apellido, sexo, ingreso, suc, dep, pue, cc, salario, egreso, causal in NUEVOS:
            e = Empleado.objects.create(
                empresa=self.empresa, codigo=codigo, numero_documento=doc, primer_nombre=nombre, primer_apellido=apellido, sexo=sexo,
                fecha_ingreso=ingreso, fecha_nacimiento=date(1980 + self.r.randint(0, 22), self.r.randint(1, 12), self.r.randint(1, 28)),
                sucursal=sucursales[suc], departamento=departamentos[dep], puesto=puestos[pue], centro_costo=centros[cc], supervisor=jefa,
                creado_por=self.admin, modificado_por=self.admin)
            plazo_fijo = causal == 'fin_contrato'
            contrato = ContratoEmpleado.objects.create(
                empresa=self.empresa, empleado=e, numero=f'C-{codigo}', fecha_inicio=ingreso, esquema_salarial=jornal if pue == 'OPE' else mensual,
                tipo_contrato='plazo_fijo' if plazo_fijo else 'indefinido', fecha_fin=egreso if plazo_fijo else None,
                frecuencia_pago='quincenal' if pue == 'OPE' else 'mensual', salario=salario, creado_por=self.admin, modificado_por=self.admin)
            contrato.activar(self.admin)
            AsignacionHorario.objects.create(empresa=self.empresa, empleado=e, horario=deposito if dep == 'DEP' else oficina,
                                             vigente_desde=ingreso, motivo='Horario inicial (demo)')
            if egreso:
                self.egresos[codigo] = (egreso, causal)
        # Datos completos para las planillas oficiales.
        civiles = ['soltero', 'casado', 'soltero', 'casado', 'divorciado']
        calles = ['Mcal. López', 'España', 'Eusebio Ayala', 'Artigas', 'Mcal. Estigarribia', 'Avda. Irrazábal']
        for e in Empleado.objects.filter(empresa=self.empresa):
            e.numero_asegurado_ips = e.numero_asegurado_ips or f'IPS-{e.numero_documento}'
            e.estado_civil = e.estado_civil or self.r.choice(civiles)
            e.direccion = e.direccion or f'{self.r.choice(calles)} {self.r.randint(100, 3999)}, {e.sucursal.ciudad or "Asunción"}'
            e.telefono = e.telefono or f'098{self.r.randint(1000000, 9999999)}'
            e.save(update_fields=['numero_asegurado_ips', 'estado_civil', 'direccion', 'telefono'])
        self.empleados = list(Empleado.objects.filter(empresa=self.empresa).select_related('puesto', 'departamento').order_by('codigo'))
        self.horario = {a.empleado_id: a.horario for a in AsignacionHorario.objects.filter(empresa=self.empresa).select_related('horario')}

    def _aumentos(self):
        from contratos.models import ContratoEmpleado, HistorialSalarial, sueldo_vigente
        for anio, porcentaje in ((2024, Decimal('6')), (2025, Decimal('5.5')), (2026, Decimal('7'))):
            fecha = date(anio, 7, 1)
            for e in self._activos(fecha):
                egreso = self.egresos.get(e.codigo, (None,))[0]
                if (egreso and fecha >= egreso) or e.fecha_ingreso > fecha - timedelta(days=60):
                    continue
                actual = sueldo_vigente(e, fecha - timedelta(days=1))
                contrato = ContratoEmpleado.objects.filter(empleado=e, estado=ContratoEmpleado.VIGENTE).first()
                if actual is None or contrato is None:
                    continue
                nuevo = (actual.salario_base * (1 + porcentaje / 100) / 1000).quantize(Decimal('1')) * 1000
                cambio = HistorialSalarial.objects.create(
                    empresa=self.empresa, empleado=e, contrato=contrato, vigente_desde=fecha, esquema_salarial=actual.esquema_salarial,
                    salario_base=nuevo, frecuencia_pago=actual.frecuencia_pago, motivo=f'Ajuste anual {anio} ({porcentaje} %)',
                    creado_por=self.gestor, modificado_por=self.gestor)
                cambio.aprobar(self.admin)

    def _bajas(self):
        from contratos.models import ContratoEmpleado
        motivos = {'renuncia': 'Renuncia voluntaria', 'despido_injustificado': 'Despido sin causa',
                   'mutuo_acuerdo': 'Mutuo acuerdo', 'fin_contrato': 'Fin del contrato a plazo fijo',
                   'despido_justificado': 'Despido con causa justificada (faltas reiteradas)'}
        for e in self.empleados:
            if e.codigo not in self.egresos:
                continue
            egreso, causal = self.egresos[e.codigo]
            with transaction.atomic():
                e.estado, e.fecha_egreso, e.motivo_egreso = Empleado.BAJA, egreso, motivos[causal]
                e.save(update_fields=['estado', 'fecha_egreso', 'motivo_egreso'])
                HistorialAsignacion.objects.filter(empleado=e, vigente_hasta__isnull=True).update(vigente_hasta=egreso)
                contrato = ContratoEmpleado.objects.filter(empleado=e, estado=ContratoEmpleado.VIGENTE).first()
                if contrato:
                    contrato.finalizar(self.admin, egreso, motivos[causal])

    def _devengos(self):
        from licencias import servicios
        servicios.devengar(Empleado.objects.filter(empresa=self.empresa).select_related('empresa'), date(2000, 1, 1), self.hoy, self.admin)

    # -------------------------------------------------------------- licencias
    def _solicitud(self, empleado, codigo_tipo, desde, hasta, aprobar=True, **extra):
        from licencias import servicios
        from licencias.models import SolicitudLicencia, TipoLicencia, saldo_vacaciones
        tipo = TipoLicencia.objects.get(empresa=None, codigo=codigo_tipo)
        s = SolicitudLicencia(empresa=self.empresa, empleado=empleado, tipo=tipo, fecha_desde=desde, fecha_hasta=hasta,
                              creado_por=self.gestor, modificado_por=self.gestor, **extra)
        s.calcular()
        if tipo.consume_vacaciones and s.dias > saldo_vacaciones(empleado):
            return None
        try:
            s.full_clean()
        except Exception:  # noqa: BLE001 — se superpone con otra: se omite
            return None
        s.save()
        if aprobar:
            servicios.aprobar(s, self.admin)
        return s

    def _licencias(self):
        from licencias.models import CertificadoMedico
        self.licencia_dias = {}   # empleado_id -> fechas sin trabajo
        self.permisos = {}        # (empleado_id, fecha) -> hora de llegada
        for e in self.empleados:
            dias = set()
            for anio in (2024, 2025, 2026):
                inicio = date(anio, self.r.choice([1, 2]), self.r.randint(5, 20))
                while inicio.weekday() != 0:
                    inicio += timedelta(days=1)
                fin = inicio + timedelta(days=4 if anio < 2026 else 9)
                if inicio - e.fecha_ingreso < timedelta(days=365) or (e.fecha_egreso and fin >= e.fecha_egreso) or fin >= self.ayer:
                    continue
                if self._solicitud(e, 'VAC', inicio, fin, motivo='Vacaciones de verano'):
                    dias |= {inicio + timedelta(days=i) for i in range((fin - inicio).days + 1)}
            self.licencia_dias[e.pk] = dias
        # Reposos médicos con certificado.
        for codigo, desde, dias_reposo in (('E004', date(2024, 5, 6), 3), ('E009', date(2025, 7, 14), 2), ('E011', date(2024, 9, 9), 5),
                                           ('E003', date(2026, 4, 20), 2), ('E018', date(2024, 8, 19), 3)):
            e = next(x for x in self.empleados if x.codigo == codigo)
            hasta = desde + timedelta(days=dias_reposo - 1)
            doc = self._documento(e, 'MEDICO', f'Certificado de reposo {desde:%d-%m-%Y}', desde)
            s = self._solicitud(e, 'REPOSO', desde, hasta, motivo='Reposo médico', documento=doc)
            if s:
                CertificadoMedico.objects.create(empresa=self.empresa, empleado=e, fecha_desde=desde, fecha_hasta=hasta, emisor='Hospital Central (demo)',
                                                 numero=f'CM-{self.r.randint(10000, 99999)}', documento=doc, solicitud=s, estado='validado',
                                                 creado_por=self.gestor, modificado_por=self.gestor)
                self.licencia_dias[e.pk] |= {desde + timedelta(days=i) for i in range(dias_reposo)}
        # Duelo y matrimonio (con su comprobante).
        for codigo, tipo, desde, descripcion in (('E002', 'DUELO', date(2025, 2, 10), 'Acta de defunción'),
                                                 ('E010', 'MATRIMONIO', date(2024, 11, 18), 'Acta de matrimonio')):
            e = next(x for x in self.empleados if x.codigo == codigo)
            doc = self._documento(e, 'OTRO', descripcion, desde)
            if self._solicitud(e, tipo, desde, desde + timedelta(days=2), motivo=descripcion, documento=doc):
                self.licencia_dias[e.pk] |= {desde + timedelta(days=i) for i in range(3)}
        # Permisos particulares por horas (llegan a las 10:00).
        oficinistas = [e for e in self.empleados if self.horario[e.pk].codigo == 'OFICINA']
        for _ in range(14):
            e = self.r.choice(oficinistas)
            dia = INICIO + timedelta(days=self.r.randint(0, (self.ayer - INICIO).days))
            if dia.weekday() > 4 or dia in self.feriados or dia < e.fecha_ingreso or (e.fecha_egreso and dia > e.fecha_egreso) \
                    or dia in self.licencia_dias[e.pk]:
                continue
            if self._solicitud(e, 'PARTICULAR', dia, dia, motivo='Trámite personal', hora_desde=time(8), hora_hasta=time(10)):
                self.permisos[(e.pk, dia)] = time(10, 0)
        # Una rechazada, para mostrar el circuito.
        from licencias import servicios
        s = self._solicitud(next(x for x in self.empleados if x.codigo == 'E004'), 'VAC', date(2025, 12, 22), date(2025, 12, 26), aprobar=False,
                            motivo='Vacaciones de fin de año')
        if s:
            servicios.rechazar(s, self.admin, 'Temporada alta de ventas: reprogramar para enero.')

    # ----------------------------------------------------------- marcaciones
    def _marcaciones(self):
        from asistencia.models import AjusteMarcacion, AutorizacionHorasExtra, Marcacion, RelojExterno, TerminalMarcacion
        terminal = TerminalMarcacion.objects.filter(empresa=self.empresa).first()
        reloj = RelojExterno.objects.filter(empresa=self.empresa).first()
        existentes = set(Marcacion.objects.filter(empresa=self.empresa).values_list('empleado_id', 'fecha_hora__date'))
        marcas, autorizaciones, olvidos = [], [], []
        self.ausencias = []
        for e in self.empleados:
            horario = self.horario[e.pk]
            tramos = {}
            for t in horario.tramos.all():
                tramos.setdefault(t.dia_semana, []).append(t)
            deposito = horario.codigo == 'DEPOSITO'
            desde = max(INICIO, e.fecha_ingreso)
            hasta = min(self.ayer, e.fecha_egreso or self.ayer)
            dia = desde
            while dia <= hasta:
                del_dia = sorted(tramos.get(dia.weekday(), []), key=lambda t: t.hora_inicio)
                if not del_dia or dia in self.feriados or dia in self.licencia_dias[e.pk] or (e.pk, dia) in existentes:
                    dia += timedelta(days=1)
                    continue
                if self.r.random() < 0.015:
                    self.ausencias.append((e.pk, dia))
                    dia += timedelta(days=1)
                    continue
                inicio = datetime.combine(dia, del_dia[0].hora_inicio, tzinfo=ZONA)
                fin = datetime.combine(dia, del_dia[-1].hora_fin, tzinfo=ZONA)
                if (e.pk, dia) in self.permisos:
                    entrada = datetime.combine(dia, self.permisos[(e.pk, dia)], tzinfo=ZONA) - timedelta(minutes=self.r.randint(0, 8))
                elif self.r.random() < 0.06:
                    entrada = inicio + timedelta(minutes=self.r.randint(12, 40))
                else:
                    entrada = inicio - timedelta(minutes=self.r.randint(0, 12))
                salida = fin + timedelta(minutes=self.r.randint(0, 9))
                if self.r.random() < 0.035:
                    extra = self.r.randint(60, 150)
                    salida = fin + timedelta(minutes=extra)
                    if self.r.random() < 0.8:
                        autorizaciones.append(AutorizacionHorasExtra(
                            empresa=self.empresa, empleado=e, fecha=dia, minutos_solicitados=extra, minutos_aprobados=extra,
                            motivo=self.r.choice(['Inventario', 'Cierre de mes', 'Entrega urgente', 'Cobertura de turno']),
                            estado='aprobada', aprobado_por=self.admin, aprobado_en=timezone.now(), creado_por=self.gestor, modificado_por=self.gestor))
                datos = dict(empresa=self.empresa, empleado=e,
                             metodo=Marcacion.CSV if deposito else Marcacion.QR,
                             nivel_verificacion='archivo_importado' if deposito else 'qr_autenticado',
                             terminal=None if deposito else terminal, reloj=reloj if deposito else None)
                marcas.append(Marcacion(fecha_hora=entrada, tipo=Marcacion.ENTRADA,
                                        huella_deduplicacion=hashlib.sha256(f'demo|{e.pk}|{entrada}|E'.encode()).hexdigest(), **datos))
                if self.r.random() < 0.01:
                    olvidos.append((e, salida))  # se olvidó de marcar la salida
                else:
                    marcas.append(Marcacion(fecha_hora=salida, tipo=Marcacion.SALIDA,
                                            huella_deduplicacion=hashlib.sha256(f'demo|{e.pk}|{salida}|S'.encode()).hexdigest(), **datos))
                dia += timedelta(days=1)
        Marcacion.objects.bulk_create(marcas, batch_size=1000)
        AutorizacionHorasExtra.objects.bulk_create(autorizaciones, batch_size=500)
        # Olvidos: la mayoría se corrigen con un ajuste aprobado; algunos quedan como marca faltante.
        for e, salida in olvidos:
            if self.r.random() < 0.7:
                ajuste = AjusteMarcacion.objects.create(
                    empresa=self.empresa, empleado=e, accion=AjusteMarcacion.AGREGAR, fecha_hora=salida, tipo=Marcacion.SALIDA,
                    motivo='Se olvidó de marcar la salida (lo confirmó el supervisor)', creado_por=self.gestor, modificado_por=self.gestor)
                marca = Marcacion.objects.create(
                    empresa=self.empresa, empleado=e, fecha_hora=salida, tipo=Marcacion.SALIDA, metodo=Marcacion.MANUAL,
                    nivel_verificacion='manual_aprobado', referencia=f'Ajuste {ajuste.pk}',
                    huella_deduplicacion=hashlib.sha256(f'ajuste|{ajuste.pk}'.encode()).hexdigest(), creado_por=self.admin, modificado_por=self.admin)
                AjusteMarcacion.objects.filter(pk=ajuste.pk).update(estado=AjusteMarcacion.APROBADO, aprobado_por=self.admin,
                                                                    aprobado_en=timezone.now(), marcacion_creada=marca)
        self.stdout.write(f'    {len(marcas)} marcas, {len(autorizaciones)} autorizaciones de horas extra, {len(olvidos)} olvidos de marca.')

    def _asistencia(self):
        from asistencia import motor
        from asistencia.models import IncidenciaAsistencia
        for e in self.empleados:
            motor.calcular(e, max(INICIO, e.fecha_ingreso), self.ayer)
        # La mitad de las ausencias, justificadas (avisó y presentó constancia).
        for empleado_id, dia in self.ausencias:
            if self.r.random() < 0.5:
                IncidenciaAsistencia.objects.filter(empleado_id=empleado_id, fecha=dia, tipo=IncidenciaAsistencia.AUSENCIA).update(
                    estado='justificada', resolucion='Avisó por enfermedad de un familiar; presentó constancia.')

    # ------------------------------------------------------------- novedades
    def _novedades(self):
        from nomina import servicios as nomina
        from nomina.models import ConceptoNomina, ConceptoRecurrente
        from novedades import servicios
        from novedades.models import Anticipo, DescuentoAutorizado, Novedad, Prestamo
        ahora = timezone.now()
        comision = ConceptoNomina.objects.get(empresa=None, codigo='COMISION')
        bono = ConceptoNomina.objects.get(empresa=None, codigo='BONO')
        novedades = []
        for mes in _meses(INICIO, self.ayer.replace(day=1) - timedelta(days=1)):
            fin = _fin_de_mes(mes)
            for e in self._activos(fin):
                if e.puesto and e.puesto.codigo == 'VEN' and e.fecha_ingreso <= mes:
                    ventas = Decimal(self.r.randint(18, 65)) * 1000000
                    novedades.append(Novedad(empresa=self.empresa, empleado=e, concepto=comision, periodo_desde=mes, periodo_hasta=fin,
                                             cantidad=ventas, tasa=Decimal('2'), origen='comision', descripcion=f'Comisión por ventas de {mes:%m/%Y}',
                                             referencia=f'VTA-{mes:%Y%m}-{e.codigo}', estado='aprobada', aprobado_por=self.admin, aprobado_en=ahora,
                                             creado_por=self.gestor, modificado_por=self.gestor))
            if mes.month == 12:
                for e in self.r.sample(self._activos(fin), k=min(7, len(self._activos(fin)))):
                    novedades.append(Novedad(empresa=self.empresa, empleado=e, concepto=bono, periodo_desde=mes, periodo_hasta=fin,
                                             monto=Decimal(self.r.choice([300, 400, 500, 750])) * 1000, origen='bono',
                                             descripcion='Premio de fin de año', estado='aprobada', aprobado_por=self.admin, aprobado_en=ahora,
                                             creado_por=self.gestor, modificado_por=self.gestor))
            if mes.month in (3, 6, 9):
                for e in self.r.sample(self._activos(fin), k=min(3, len(self._activos(fin)))):
                    novedades.append(Novedad(empresa=self.empresa, empleado=e, concepto=bono, periodo_desde=mes, periodo_hasta=fin,
                                             monto=Decimal('150000'), origen='bono', descripcion='Premio por presentismo del trimestre',
                                             estado='aprobada', aprobado_por=self.admin, aprobado_en=ahora,
                                             creado_por=self.gestor, modificado_por=self.gestor))
        Novedad.objects.bulk_create(novedades, batch_size=500)

        por_codigo = {e.codigo: e for e in self.empleados}
        # Viático fijo del gerente y bonificación familiar (con su comprobante).
        viatico, _ = ConceptoNomina.objects.get_or_create(empresa=self.empresa, codigo='VIATICO', defaults={
            'nombre': 'Viático mensual', 'tipo': 'haber', 'tipo_calculo': 'fijo', 'recurrente': True, 'afecta_costo_patronal': True,
            'orden': 45, 'creado_por': self.admin})
        fijo = ConceptoRecurrente.objects.create(empresa=self.empresa, empleado=por_codigo['E001'], concepto=viatico, monto=500000,
                                                 vigente_desde=date(2024, 1, 1), frecuencia='mensual', motivo='Viático por visitas a sucursales',
                                                 creado_por=self.gestor, modificado_por=self.gestor)
        nomina.recurrente_al_crear(fijo, self.gestor)
        familiar = ConceptoNomina.objects.get(empresa=None, codigo='BONIFICACION_FAMILIAR')
        for codigo, hijos in (('E006', 2), ('E011', 1), ('E005', 1)):
            e = por_codigo[codigo]
            doc = self._documento(e, 'OTRO', f'Certificado de nacimiento ({hijos} hijo/s)', date(2023, 9, 1))
            fijo = ConceptoRecurrente.objects.create(empresa=self.empresa, empleado=e, concepto=familiar, monto=152200 * hijos,
                                                     vigente_desde=max(INICIO, e.fecha_ingreso), documento=doc,
                                                     motivo=f'Bonificación familiar por {hijos} hijo/s', creado_por=self.gestor, modificado_por=self.gestor)
            nomina.recurrente_al_crear(fijo, self.gestor)
        # Cuota sindical autorizada.
        sindical = ConceptoNomina.objects.get(empresa=None, codigo='CUOTA_SINDICAL')
        for codigo in ('E006', 'E007', 'E011', 'E005'):
            e = por_codigo[codigo]
            doc = self._documento(e, 'OTRO', 'Autorización de descuento de cuota sindical', date(2024, 2, 20))
            DescuentoAutorizado.objects.create(empresa=self.empresa, empleado=e, concepto=sindical, tipo='sindical', monto_cuota=50000,
                                               fecha_desde=max(date(2024, 3, 1), e.fecha_ingreso), autorizado_por_empleado=True, documento=doc,
                                               creado_por=self.gestor, modificado_por=self.gestor)
        # Anticipos pagados y recuperados en cuotas.
        for codigo, fecha, monto, cuotas in (('E003', date(2024, 2, 12), 800000, 2), ('E006', date(2024, 7, 8), 400000, 1),
                                             ('E009', date(2024, 12, 9), 1200000, 3), ('E005', date(2025, 4, 14), 600000, 2),
                                             ('E007', date(2025, 8, 11), 300000, 1), ('E002', date(2026, 3, 9), 1000000, 2),
                                             ('E020', date(2026, 2, 16), 900000, 6), ('E013', date(2026, 8, 10), 500000, 1)):
            e = por_codigo[codigo]
            anticipo = Anticipo.objects.create(empresa=self.empresa, empleado=e, fecha=fecha, monto_solicitado=monto, motivo='Gastos imprevistos',
                                               cuotas=cuotas, primer_mes=(fecha + timedelta(days=32)).replace(day=1),
                                               creado_por=self.gestor, modificado_por=self.gestor)
            servicios.aprobar_anticipo(anticipo, self.admin)
            servicios.pagar_anticipo(anticipo, self.admin, 'transferencia', f'TRF-ANT-{anticipo.pk}', fecha=fecha + timedelta(days=1))
        # Préstamos con autorización firmada.
        for codigo, fecha, capital, cuotas, interes in (('E004', date(2024, 4, 3), 3000000, 6, 0), ('E001', date(2025, 1, 15), 8000000, 12, 1),
                                                        ('E010', date(2025, 10, 6), 4500000, 9, 0)):
            e = por_codigo[codigo]
            doc = self._documento(e, 'OTRO', 'Autorización firmada de préstamo y descuento', fecha)
            prestamo = Prestamo.objects.create(empresa=self.empresa, empleado=e, fecha=fecha, capital=capital, cantidad_cuotas=cuotas,
                                               tasa_interes_mensual=interes, primer_mes=(fecha + timedelta(days=32)).replace(day=1),
                                               motivo='Préstamo personal', documento=doc, creado_por=self.gestor, modificado_por=self.gestor)
            servicios.aprobar_prestamo(prestamo, self.admin)
            servicios.desembolsar_prestamo(prestamo, self.admin, f'TRF-PRE-{prestamo.pk}')

    # --------------------------------------------------------------- nóminas
    def _flujo(self, corrida, fecha_pago):
        from nomina import liquidar
        from nomina.models import LiquidacionEmpleado, PagoNomina
        errores = list(corrida.liquidaciones.filter(estado_calculo=LiquidacionEmpleado.ERROR).values_list('empleado__codigo', 'advertencias'))
        if corrida.es_simulacion or errores:
            raise CommandError(f'La liquidación {corrida} no se puede aprobar: {corrida.advertencias} {errores}')
        liquidar.revisar(corrida, self.gestor)
        liquidar.aprobar(corrida, self.admin)
        corrida = liquidar.cerrar(corrida, self.admin)
        liquidar.emitir_recibos(corrida, self.admin)
        liquidar.publicar_recibos(corrida, self.admin)
        liquidar.registrar_pagos(corrida, self.admin, fecha_pago, 'transferencia', f'LOTE-{corrida.periodo.codigo}')
        for pago in PagoNomina.objects.filter(corrida=corrida, estado=PagoNomina.REGISTRADO):
            liquidar.confirmar_pago(pago, self.admin)
        self.corridas += 1

    def _nominas(self):
        from nomina import liquidar
        from nomina.models import CorridaNomina, LiquidacionFinal, PeriodoNomina
        self.corridas = 0
        ultimo_mes = self.hoy.replace(day=1) - timedelta(days=1)
        for mes in _meses(INICIO, ultimo_mes):
            fin = _fin_de_mes(mes)
            # Egresos del mes: su liquidación final va antes que la nómina del mes.
            for e in self.empleados:
                if e.codigo in self.egresos and mes <= self.egresos[e.codigo][0] <= fin:
                    egreso, causal = self.egresos[e.codigo]
                    final = LiquidacionFinal.objects.create(
                        empresa=self.empresa, empleado=e, fecha_egreso=egreso, causal=causal, preaviso_otorgado=causal == 'mutuo_acuerdo',
                        motivo=e.motivo_egreso, creado_por=self.gestor, modificado_por=self.gestor)
                    self._flujo(liquidar.calcular_final(final, self.gestor), egreso + timedelta(days=5))
            periodo, _ = PeriodoNomina.objects.get_or_create(
                empresa=self.empresa, codigo=f'{mes:%Y-%m}',
                defaults={'tipo': 'mensual', 'fecha_desde': mes, 'fecha_hasta': fin, 'fecha_pago': fin, 'creado_por': self.gestor})
            for vieja in periodo.corridas.exclude(estado__in=(CorridaNomina.CERRADA, CorridaNomina.ANULADA)):
                liquidar.anular(vieja, self.admin, 'Se reemplaza por la nómina de la historia simulada.')
            self._flujo(liquidar.crear(periodo, self.gestor), fin)
            if mes.month == 12:
                self._flujo(liquidar.crear_aguinaldo(self.empresa, mes.year, self.gestor), date(mes.year, 12, 20))
            self.stdout.write(f'    {mes:%m/%Y} cerrado.')
        PeriodoNomina.objects.get_or_create(
            empresa=self.empresa, codigo=f'{self.hoy:%Y-%m}',
            defaults={'tipo': 'mensual', 'fecha_desde': self.hoy.replace(day=1), 'fecha_hasta': _fin_de_mes(self.hoy.replace(day=1)),
                      'fecha_pago': _fin_de_mes(self.hoy.replace(day=1)), 'creado_por': self.gestor})
        self.stdout.write(f'    {self.corridas} liquidaciones cerradas (mensuales, aguinaldos y finales).')

    def _planillas(self):
        from cumplimiento import servicios as planillas
        from cumplimiento.models import PresentacionOficial
        ahora = timezone.now()
        pedidos = [(PresentacionOficial.IPS_MENSUAL, mes, _fin_de_mes(mes)) for mes in _meses(date(2026, 1, 1), self.hoy.replace(day=1) - timedelta(days=1))]
        pedidos += [(PresentacionOficial.MTESS_SUELDOS, date(a, 1, 1), date(a, 12, 31)) for a in (2024, 2025)]
        pedidos += [(PresentacionOficial.MTESS_EMPLEADOS, date(a, 1, 1), date(a, 12, 31)) for a in (2024, 2025)]
        for tipo, desde, hasta in pedidos:
            p = planillas.preparar(PresentacionOficial.objects.create(empresa=self.empresa, tipo=tipo, periodo_desde=desde, periodo_hasta=hasta,
                                                                      creado_por=self.gestor, modificado_por=self.gestor))
            if p.lineas_con_errores:
                self.stdout.write(self.style.WARNING(f'    {p}: {p.lineas_con_errores} línea(s) con errores, queda preparada.'))
                continue
            p.estado, p.presentado_por, p.presentado_en = PresentacionOficial.PRESENTADA, self.admin, ahora
            p.numero_comprobante = f'{p.autoridad}-{desde:%Y%m}-{self.r.randint(100000, 999999)}'
            p.save(update_fields=['estado', 'presentado_por', 'presentado_en', 'numero_comprobante'])

    def _pendientes(self):
        """Lo que queda para hacer este mes: muestra los circuitos de aprobación."""
        from asistencia.models import AjusteMarcacion, Marcacion
        from nomina.models import ConceptoNomina
        from novedades.models import Anticipo, Novedad
        por_codigo = {e.codigo: e for e in self.empleados}
        inicio = self.hoy.replace(day=1)
        Novedad.objects.create(empresa=self.empresa, empleado=por_codigo['E003'], concepto=ConceptoNomina.objects.get(empresa=None, codigo='COMISION'),
                               periodo_desde=inicio, periodo_hasta=_fin_de_mes(inicio), cantidad=Decimal('42000000'), tasa=Decimal('2'),
                               origen='comision', descripcion=f'Comisión por ventas de {inicio:%m/%Y}', creado_por=self.gestor, modificado_por=self.gestor)
        Anticipo.objects.create(empresa=self.empresa, empleado=por_codigo['E012'], fecha=self.hoy, monto_solicitado=700000,
                                motivo='Reparación del vehículo', cuotas=2, creado_por=self.gestor, modificado_por=self.gestor)
        siguiente = (inicio + timedelta(days=40)).replace(day=1)
        while siguiente.weekday() != 0:
            siguiente += timedelta(days=1)
        self._solicitud(por_codigo['E009'], 'VAC', siguiente, siguiente + timedelta(days=4), aprobar=False, motivo='Vacaciones')
        dia = self.ayer - timedelta(days=2)
        while dia.weekday() > 4:
            dia -= timedelta(days=1)
        AjusteMarcacion.objects.create(empresa=self.empresa, empleado=por_codigo['E004'], accion=AjusteMarcacion.AGREGAR,
                                       fecha_hora=datetime.combine(dia, time(17, 5), tzinfo=ZONA), tipo=Marcacion.SALIDA,
                                       motivo='Se quedó sin batería el celular al salir', creado_por=self.gestor, modificado_por=self.gestor)
