"""Crea una empresa de demostración con datos ficticios: sucursales,
estructura, empleados y un usuario por perfil. Solo para probar o mostrar el
sistema; no usar con datos reales.

    manage.py cargar_datos_demo --clave '<contraseña de los usuarios demo>'

Es idempotente: si la empresa demo ya existe, no la duplica (solo
restablece la contraseña de sus usuarios)."""
from datetime import date

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core import alcance
from cuentas.models import Perfil
from empleados.models import CentroCosto, Departamento, Empleado, Puesto
from plataforma.models import Empresa, Sucursal

NOMBRE_EMPRESA = 'Empresa Demo S.A.'

EMPLEADOS = [
    # código, documento, nombre, apellido, sexo, ingreso, sucursal, departamento, puesto, centro
    ('E001', '1234567', 'María', 'González', 'F', date(2019, 3, 1), 'CEN', 'ADM', 'GER', 'CC-ADM'),
    ('E002', '2345678', 'Juan', 'Benítez', 'M', date(2020, 7, 15), 'CEN', 'RRHH', 'ANA', 'CC-ADM'),
    ('E003', '3456789', 'Lucía', 'Martínez', 'F', date(2021, 2, 1), 'CEN', 'VEN', 'VEN', 'CC-VEN'),
    ('E004', '4567890', 'Carlos', 'Ramírez', 'M', date(2022, 5, 10), 'ENC', 'VEN', 'VEN', 'CC-VEN'),
    ('E005', '5678901', 'Ana', 'Duarte', 'F', date(2023, 1, 9), 'ENC', 'VEN', 'CAJ', 'CC-VEN'),
    ('E006', '6789012', 'Pedro', 'Villalba', 'M', date(2023, 8, 21), 'ENC', 'DEP', 'OPE', 'CC-OPE'),
    ('E007', '7890123', 'Rosa', 'Ortiz', 'F', date(2024, 4, 2), 'CEN', 'DEP', 'OPE', 'CC-OPE'),
    ('E008', '8901234', 'Diego', 'Acosta', 'M', date(2025, 11, 3), 'ENC', 'VEN', 'CAJ', 'CC-VEN'),
]


class Command(BaseCommand):
    help = 'Crea una empresa de demostración con empleados y usuarios de cada perfil (datos ficticios).'

    def add_arguments(self, parser):
        parser.add_argument('--clave', required=True, help='Contraseña de los usuarios demo (admin_demo, gestor_demo, empleado_demo).')

    @transaction.atomic
    def handle(self, *args, **opciones):
        clave = opciones['clave']
        if len(clave) < 8:
            raise CommandError('La clave tiene que tener al menos 8 caracteres.')

        empresa, creada = Empresa.objects.get_or_create(nombre=NOMBRE_EMPRESA, defaults={
            'razon_social': 'Empresa Demo Sociedad Anónima', 'ruc': '80099999-0',
            'numero_patronal_ips': '0000-00000', 'actividad': 'Comercio minorista', 'direccion': 'Encarnación, Paraguay',
        })
        if creada:
            sucursales = {
                'CEN': Sucursal.objects.create(empresa=empresa, codigo='CEN', nombre='Casa central', ciudad='Asunción'),
                'ENC': Sucursal.objects.create(empresa=empresa, codigo='ENC', nombre='Sucursal Encarnación', ciudad='Encarnación'),
            }
            departamentos = {c: Departamento.objects.create(empresa=empresa, codigo=c, nombre=n) for c, n in [
                ('ADM', 'Administración'), ('RRHH', 'Recursos Humanos'), ('VEN', 'Ventas'), ('DEP', 'Depósito'),
            ]}
            puestos = {c: Puesto.objects.create(empresa=empresa, codigo=c, nombre=n) for c, n in [
                ('GER', 'Gerente'), ('ANA', 'Analista de RR. HH.'), ('VEN', 'Vendedor'), ('CAJ', 'Cajero'), ('OPE', 'Operario de depósito'),
            ]}
            centros = {c: CentroCosto.objects.create(empresa=empresa, codigo=c, nombre=n) for c, n in [
                ('CC-ADM', 'Administración'), ('CC-VEN', 'Ventas'), ('CC-OPE', 'Operaciones'),
            ]}
            for codigo, doc, nombre, apellido, sexo, ingreso, suc, dep, pue, cc in EMPLEADOS:
                Empleado.objects.create(
                    empresa=empresa, codigo=codigo, numero_documento=doc, primer_nombre=nombre, primer_apellido=apellido,
                    sexo=sexo, fecha_ingreso=ingreso, fecha_nacimiento=date(1985 + int(codigo[-1]), 6, 15),
                    sucursal=sucursales[suc], departamento=departamentos[dep], puesto=puestos[pue], centro_costo=centros[cc],
                )
            jefa = Empleado.objects.get(empresa=empresa, codigo='E001')
            Empleado.objects.filter(empresa=empresa).exclude(pk=jefa.pk).update(supervisor=jefa)
            self.stdout.write(self.style.SUCCESS(f'Empresa "{empresa}" creada con {len(EMPLEADOS)} empleados.'))
        else:
            self.stdout.write(f'La empresa "{empresa}" ya existía: solo se restablecen sus usuarios.')

        self._contratos_demo(empresa)
        self._jornada_demo(empresa)
        self._marcador_demo(empresa)
        self._licencias_demo(empresa)

        usuarios = [
            ('admin_demo', 'Administración', 'Demo', alcance.GRUPO_ADMINISTRADOR, None),
            ('gestor_demo', 'Gestión', 'Demo', alcance.GRUPO_GESTOR, None),
            ('empleado_demo', 'Lucía', 'Martínez', alcance.GRUPO_EMPLEADO, Empleado.objects.get(empresa=empresa, codigo='E003')),
        ]
        for nombre, primer, apellido, grupo, empleado in usuarios:
            usuario, _ = User.objects.get_or_create(username=nombre, defaults={'first_name': primer, 'last_name': apellido})
            usuario.set_password(clave)
            usuario.is_active = True
            usuario.save()
            usuario.groups.set([Group.objects.get(name=grupo)])
            Perfil.objects.update_or_create(usuario=usuario, defaults={'empresa': empresa, 'empleado': empleado})
            self.stdout.write(f'  Usuario {nombre} ({grupo})')
        self.stdout.write(self.style.WARNING('Datos ficticios: no usar esta empresa para datos reales.'))

    def _contratos_demo(self, empresa):
        """Fase 2: un contrato vigente por empleado (con su sueldo inicial) y
        una cuenta bancaria de ejemplo. Solo a los que todavía no tienen."""
        from contratos.models import ContratoEmpleado, EsquemaSalarial
        from empleados.models import CuentaBancaria
        mensual = EsquemaSalarial.objects.get(empresa=None, codigo='MENSUAL')
        jornal = EsquemaSalarial.objects.get(empresa=None, codigo='JORNAL')
        sistema = User.objects.filter(username='admin').first()
        sueldos = {'GER': 9000000, 'ANA': 5500000, 'VEN': 3800000, 'CAJ': 3400000, 'OPE': 130000}
        nuevos = 0
        for empleado in Empleado.objects.filter(empresa=empresa).select_related('puesto'):
            if empleado.contratos.exists():
                continue
            por_jornal = empleado.puesto and empleado.puesto.codigo == 'OPE'
            contrato = ContratoEmpleado.objects.create(
                empresa=empresa, empleado=empleado, numero=f'C-{empleado.codigo}', fecha_inicio=empleado.fecha_ingreso,
                esquema_salarial=jornal if por_jornal else mensual, frecuencia_pago='quincenal' if por_jornal else 'mensual',
                salario=sueldos.get(empleado.puesto.codigo if empleado.puesto else '', 3500000),
                creado_por=sistema, modificado_por=sistema,
            )
            contrato.activar(sistema)
            nuevos += 1
        lucia = Empleado.objects.get(empresa=empresa, codigo='E003')
        if not lucia.cuentas_bancarias.exists():
            cuenta = CuentaBancaria(empresa=empresa, empleado=lucia, banco='Banco Demo', titular='Lucía Martínez',
                                    documento_titular=lucia.numero_documento, creado_por=sistema, modificado_por=sistema)
            cuenta.fijar_numero('1020304050')
            cuenta.save()
        if nuevos:
            self.stdout.write(f'  {nuevos} contratos vigentes con su sueldo inicial.')

    def _jornada_demo(self, empresa):
        """Fase 3: horario de oficina (lun–vie 08–12 y 13–17) y de depósito
        (lun–sáb 07–15), asignados desde la fecha de ingreso de cada empleado."""
        from datetime import time
        from jornada.models import AsignacionHorario, Horario, RegimenJornada, TramoHorario
        diurna = RegimenJornada.objects.get(empresa=None, codigo='DIURNA')
        oficina, creado = Horario.objects.get_or_create(empresa=empresa, codigo='OFICINA', defaults={
            'nombre': 'Oficina', 'regimen': diurna, 'tolerancia_minutos': 10})
        if creado:
            TramoHorario.objects.bulk_create(
                [TramoHorario(horario=oficina, dia_semana=d, hora_inicio=time(8), hora_fin=time(12), orden=1) for d in range(5)]
                + [TramoHorario(horario=oficina, dia_semana=d, hora_inicio=time(13), hora_fin=time(17), orden=2) for d in range(5)])
        deposito, creado = Horario.objects.get_or_create(empresa=empresa, codigo='DEPOSITO', defaults={
            'nombre': 'Depósito', 'regimen': diurna, 'tolerancia_minutos': 5})
        if creado:
            TramoHorario.objects.bulk_create([TramoHorario(horario=deposito, dia_semana=d, hora_inicio=time(7),
                                                           hora_fin=time(15), descanso_minutos=30) for d in range(6)])
        asignadas = 0
        for empleado in Empleado.objects.filter(empresa=empresa).select_related('departamento'):
            if empleado.asignaciones_horario.exists():
                continue
            horario = deposito if empleado.departamento and empleado.departamento.codigo == 'DEP' else oficina
            AsignacionHorario.objects.create(empresa=empresa, empleado=empleado, horario=horario,
                                             vigente_desde=empleado.fecha_ingreso, motivo='Horario inicial (demo)')
            asignadas += 1
        if asignadas:
            self.stdout.write(f'  {asignadas} empleados con horario asignado.')

    def _marcador_demo(self, empresa):
        """Fase 4: QR y código fijo habilitados, una terminal (con clave nueva en
        cada corrida, que se imprime para vincularla) y el código de Lucía."""
        from asistencia.models import ConfiguracionMarcacion, CredencialMarcacion, TerminalMarcacion
        sistema = User.objects.filter(username='admin').first()
        configuracion = ConfiguracionMarcacion.de(empresa)
        configuracion.permite_codigo_fijo = True
        configuracion.save()
        terminal, _ = TerminalMarcacion.objects.get_or_create(empresa=empresa, codigo='ENTRADA', defaults={
            'nombre': 'Entrada principal', 'ubicacion': 'Recepción', 'sucursal': empresa.plataforma_sucursal_set.first()})
        clave = terminal.generar_clave()
        lucia = Empleado.objects.get(empresa=empresa, codigo='E003')
        credencial = CredencialMarcacion.objects.filter(empleado=lucia, estado='activa').first()
        codigo = credencial.codigo() if credencial else CredencialMarcacion.generar(lucia, sistema)[1]
        self.stdout.write(f'  Terminal "{terminal}": abrí /terminal y pegá la clave {clave}')
        self.stdout.write(f'  Código fijo de Lucía Martínez (empleado_demo): {codigo}')
        self._importacion_demo(empresa, configuracion)

    def _importacion_demo(self, empresa, configuracion):
        """Fase 5: importación CSV habilitada, un reloj externo con su perfil y
        los códigos 101–108 de los empleados E001–E008 (para probar con
        docs/ejemplos/marcaciones_reloj_demo.csv)."""
        from asistencia.models import MapeoEmpleadoReloj, PerfilImportacion, RelojExterno
        configuracion.permite_csv = True
        configuracion.save()
        perfil, _ = PerfilImportacion.objects.get_or_create(empresa=empresa, codigo='RELOJ-DEMO', defaults={
            'nombre': 'Reloj del depósito (demo)', 'separador': ';', 'identificador': 'codigo_reloj',
            'columna_empleado': 'Codigo', 'columna_fecha_hora': 'FechaHora', 'formato_fecha_hora': '%d/%m/%Y %H:%M:%S',
            'columna_tipo': 'Tipo', 'valores_entrada': 'E,IN', 'valores_salida': 'S,OUT', 'columna_evento': 'Evento'})
        reloj, _ = RelojExterno.objects.get_or_create(empresa=empresa, codigo='RELOJ-DEP', defaults={
            'nombre': 'Reloj del depósito', 'fabricante': 'Genérico', 'perfil_importacion': perfil})
        for empleado in Empleado.objects.filter(empresa=empresa):
            codigo = str(100 + int(empleado.codigo[1:]))
            MapeoEmpleadoReloj.objects.get_or_create(empresa=empresa, reloj=reloj, codigo_en_reloj=codigo,
                                                     defaults={'empleado': empleado})
        self.stdout.write(f'  Reloj externo "{reloj}" con perfil "{perfil}" y códigos 101–108.')

    def _licencias_demo(self, empresa):
        """Fase 7: devengo de vacaciones del último aniversario de cada empleado
        y unas vacaciones aprobadas de Lucía (la primera semana de diciembre)."""
        from django.utils import timezone
        from licencias import servicios
        from licencias.models import SolicitudLicencia, TipoLicencia
        sistema = User.objects.filter(username='admin').first()
        hoy = timezone.localdate()
        empleados = Empleado.objects.filter(empresa=empresa).exclude(estado=Empleado.BAJA).select_related('empresa')
        creados = servicios.devengar(empleados, date(hoy.year - 1, hoy.month, min(hoy.day, 28)), hoy, sistema)
        lucia = Empleado.objects.get(empresa=empresa, codigo='E003')
        if not lucia.solicitudes_licencia.exists():
            solicitud = SolicitudLicencia(empresa=empresa, empleado=lucia, tipo=TipoLicencia.objects.get(empresa=None, codigo='VAC'),
                                          fecha_desde=date(hoy.year, 12, 1), fecha_hasta=date(hoy.year, 12, 5),
                                          motivo='Vacaciones (demo)', creado_por=sistema, modificado_por=sistema)
            solicitud.full_clean()
            solicitud.calcular()
            solicitud.save()
            servicios.aprobar(solicitud, sistema)
        if creados:
            self.stdout.write(f'  {len(creados)} devengos de vacaciones por antigüedad; vacaciones aprobadas de Lucía en diciembre.')
