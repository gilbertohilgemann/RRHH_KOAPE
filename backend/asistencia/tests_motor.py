"""Motor de asistencia, ajustes y horas extra (fase 6; §7 y pruebas de §13)."""
import hashlib
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.test import TestCase

from asistencia import motor
from asistencia.models import (AjusteMarcacion, AutorizacionHorasExtra, ConfiguracionMarcacion, DiaAsistencia,
                               IncidenciaAsistencia, Marcacion)
from core.datos_prueba import EscenarioMixin
from jornada.models import AsignacionHorario, Horario, RegimenJornada, TramoHorario

ZONA = ZoneInfo('America/Asuncion')
LUNES = date(2026, 10, 5)
SABADO = date(2026, 10, 10)
FERIADO = date(2026, 5, 14)  # jueves, feriado nacional precargado


class MotorMixin(EscenarioMixin):
    def setUp(self):
        diurna = RegimenJornada.objects.get(empresa=None, codigo='DIURNA')
        nocturna = RegimenJornada.objects.get(empresa=None, codigo='NOCTURNA')
        self.oficina = Horario.objects.create(empresa=self.e1, codigo='OF', nombre='Oficina', regimen=diurna, tolerancia_minutos=10)
        for dia in range(5):
            TramoHorario.objects.create(horario=self.oficina, dia_semana=dia, hora_inicio=time(8), hora_fin=time(12), orden=1)
            TramoHorario.objects.create(horario=self.oficina, dia_semana=dia, hora_inicio=time(13), hora_fin=time(17), orden=2)
        self.noche = Horario.objects.create(empresa=self.e1, codigo='NO', nombre='Noche', regimen=nocturna)
        for dia in range(7):
            TramoHorario.objects.create(horario=self.noche, dia_semana=dia, hora_inicio=time(22), hora_fin=time(6))
        AsignacionHorario.objects.create(empresa=self.e1, empleado=self.ana, horario=self.oficina, vigente_desde=date(2025, 1, 2))
        AsignacionHorario.objects.create(empresa=self.e1, empleado=self.beto, horario=self.noche, vigente_desde=date(2025, 1, 2))
        self.contador = 0

    def marca(self, empleado, momento, tipo=Marcacion.ENTRADA):
        self.contador += 1
        fecha_hora = datetime.fromisoformat(momento).replace(tzinfo=ZONA)
        return Marcacion.objects.create(empresa=self.e1, empleado=empleado, fecha_hora=fecha_hora, tipo=tipo,
                                        metodo=Marcacion.MANUAL, nivel_verificacion='manual_aprobado',
                                        huella_deduplicacion=hashlib.sha256(f'prueba{self.contador}'.encode()).hexdigest())

    def dia(self, empleado, fecha):
        motor.calcular(empleado, fecha)
        return DiaAsistencia.objects.get(empleado=empleado, fecha=fecha)

    def incidencias(self, empleado, fecha):
        return set(IncidenciaAsistencia.objects.filter(empleado=empleado, fecha=fecha).values_list('tipo', flat=True))


class MotorTests(MotorMixin, TestCase):
    def test_jornada_completa_con_almuerzo_sin_marcar(self):
        self.marca(self.ana, '2026-10-05 08:00')
        self.marca(self.ana, '2026-10-05 17:00', Marcacion.SALIDA)
        d = self.dia(self.ana, LUNES)
        self.assertEqual((d.estado, d.minutos_programados, d.minutos_trabajados, d.minutos_descanso), ('presente', 480, 480, 60))
        self.assertEqual((d.minutos_tardanza, d.minutos_extra_candidatos), (0, 0))
        self.assertTrue(any('descanso programado no marcado' in e for e in d.explicacion))

    def test_medio_dia_no_descuenta_un_almuerzo_que_no_trabajo(self):
        self.marca(self.ana, '2026-10-05 08:00')
        self.marca(self.ana, '2026-10-05 12:00', 'salida')
        d = self.dia(self.ana, LUNES)
        self.assertEqual((d.minutos_trabajados, d.minutos_salida_anticipada), (240, 0))  # 12:00 es el fin del tramo 1

    def test_descanso_dentro_del_tramo(self):
        deposito = Horario.objects.create(empresa=self.e1, codigo='DEP', nombre='Depósito',
                                          regimen=RegimenJornada.objects.get(empresa=None, codigo='DIURNA'))
        TramoHorario.objects.create(horario=deposito, dia_semana=0, hora_inicio=time(7), hora_fin=time(15), descanso_minutos=30)
        AsignacionHorario.objects.create(empresa=self.e1, empleado=self.ana, horario=deposito, vigente_desde=LUNES)
        self.marca(self.ana, '2026-10-05 07:00')
        self.marca(self.ana, '2026-10-05 15:00', 'salida')
        self.assertEqual(self.dia(self.ana, LUNES).minutos_trabajados, 450)  # 8 h menos 30 min de descanso no pago
        Marcacion.objects.all().delete()
        for hora, tipo in (('07:00', 'entrada'), ('11:00', 'salida'), ('11:40', 'entrada'), ('15:00', 'salida')):
            self.marca(self.ana, f'2026-10-05 {hora}', tipo)
        self.assertEqual(self.dia(self.ana, LUNES).minutos_trabajados, 440)  # tomó 40 min de pausa: no se descuenta más

    def test_varios_tramos_marcados(self):
        for hora, tipo in (('08:00', 'entrada'), ('12:00', 'salida'), ('13:00', 'entrada'), ('17:00', 'salida')):
            self.marca(self.ana, f'2026-10-05 {hora}', tipo)
        d = self.dia(self.ana, LUNES)
        self.assertEqual((d.minutos_trabajados, d.minutos_descanso), (480, 60))

    def test_tardanza_con_tolerancia_y_salida_anticipada(self):
        self.marca(self.ana, '2026-10-05 08:05')
        self.marca(self.ana, '2026-10-05 17:00', 'salida')
        self.assertEqual(self.dia(self.ana, LUNES).minutos_tardanza, 0)  # dentro de la tolerancia
        Marcacion.objects.all().delete()
        self.marca(self.ana, '2026-10-05 08:20')
        self.marca(self.ana, '2026-10-05 16:30', 'salida')
        d = self.dia(self.ana, LUNES)
        self.assertEqual((d.minutos_tardanza, d.minutos_salida_anticipada), (20, 30))
        self.assertTrue({'tardanza', 'salida_anticipada'} <= self.incidencias(self.ana, LUNES))

    def test_falta_la_salida_no_se_inventa(self):
        self.marca(self.ana, '2026-10-05 08:00')
        d = self.dia(self.ana, LUNES)
        self.assertEqual((d.estado, d.marcas_faltantes, d.minutos_trabajados), ('incompleto', 1, 0))
        self.assertIn('marca_faltante', self.incidencias(self.ana, LUNES))

    def test_ausencia_y_franco(self):
        d = self.dia(self.ana, LUNES)
        self.assertEqual(d.estado, 'ausente')
        self.assertIn('ausencia', self.incidencias(self.ana, LUNES))
        self.assertEqual(self.dia(self.ana, SABADO).estado, 'franco')

    def test_trabajo_en_franco_y_en_feriado(self):
        self.marca(self.ana, '2026-10-10 09:00')
        self.marca(self.ana, '2026-10-10 12:00', 'salida')
        d = self.dia(self.ana, SABADO)
        self.assertEqual((d.minutos_ordinarios, d.minutos_extra_candidatos), (0, 180))
        self.assertIn('trabajo_en_descanso', self.incidencias(self.ana, SABADO))
        self.assertEqual(self.dia(self.ana, FERIADO).estado, 'feriado')
        self.marca(self.ana, '2026-05-14 08:00')
        self.marca(self.ana, '2026-05-14 12:00', 'salida')
        d = self.dia(self.ana, FERIADO)
        self.assertEqual((d.feriado, d.minutos_feriado, d.minutos_programados), ('Independencia Nacional', 240, 0))

    def test_turno_noche_cruza_la_medianoche_y_suma_nocturnas(self):
        self.marca(self.beto, '2026-10-05 21:55')
        self.marca(self.beto, '2026-10-06 06:02', 'salida')
        d = self.dia(self.beto, LUNES)
        self.assertEqual(d.estado, 'presente')
        self.assertEqual(d.minutos_trabajados, 8 * 60 + 7)
        self.assertEqual(d.minutos_nocturnos, 8 * 60 + 5)  # 21:55–06:00 dentro de 20–06
        # La salida de la madrugada no aparece en el martes.
        self.assertEqual(self.dia(self.beto, date(2026, 10, 6)).estado, 'ausente')

    def test_marcas_fuera_de_orden_y_sin_tipo(self):
        # Importadas sin entrada/salida y cargadas en cualquier orden: se ordenan y se emparejan.
        self.marca(self.ana, '2026-10-05 17:00', Marcacion.DESCONOCIDO)
        self.marca(self.ana, '2026-10-05 08:00', Marcacion.DESCONOCIDO)
        self.assertEqual(self.dia(self.ana, LUNES).minutos_trabajados, 480)

    def test_horas_extra_solo_autorizadas(self):
        self.marca(self.ana, '2026-10-05 08:00')
        self.marca(self.ana, '2026-10-05 18:00', 'salida')
        d = self.dia(self.ana, LUNES)
        self.assertEqual((d.minutos_extra_candidatos, d.minutos_extra_autorizados), (60, 0))
        AutorizacionHorasExtra.objects.create(empresa=self.e1, empleado=self.ana, fecha=LUNES, minutos_solicitados=60,
                                              minutos_aprobados=30, motivo='Cierre', estado='aprobada')
        d = self.dia(self.ana, LUNES)
        self.assertEqual(d.minutos_extra_autorizados, 30)
        self.assertEqual(IncidenciaAsistencia.objects.get(empleado=self.ana, fecha=LUNES, tipo='extra_sin_autorizar').minutos, 30)

    def test_menos_del_minimo_no_es_extra(self):
        self.marca(self.ana, '2026-10-05 08:00')
        self.marca(self.ana, '2026-10-05 17:10', 'salida')
        self.assertEqual(self.dia(self.ana, LUNES).minutos_extra_candidatos, 0)

    def test_recalcular_respeta_incidencias_resueltas_y_resetea_la_revision(self):
        d = self.dia(self.ana, LUNES)
        IncidenciaAsistencia.objects.filter(empleado=self.ana, fecha=LUNES, tipo='ausencia').update(estado='justificada')
        DiaAsistencia.objects.filter(pk=d.pk).update(revisado_en=d.calculado_en)
        self.marca(self.ana, '2026-10-05 08:00')
        self.marca(self.ana, '2026-10-05 17:00', 'salida')
        d = self.dia(self.ana, LUNES)
        self.assertEqual(d.version_calculo, 2)
        self.assertIsNone(d.revisado_en)  # cambió: hay que volver a revisarlo
        self.assertEqual(IncidenciaAsistencia.objects.filter(empleado=self.ana, fecha=LUNES, tipo='ausencia').count(), 1)

    def test_las_marcas_anuladas_no_cuentan(self):
        self.marca(self.ana, '2026-10-05 08:00')
        salida = self.marca(self.ana, '2026-10-05 17:00', 'salida')
        Marcacion.objects.filter(pk=salida.pk).update(anulada=True)
        self.assertEqual(self.dia(self.ana, LUNES).estado, 'incompleto')

    def test_usa_el_horario_vigente_en_la_fecha(self):
        AsignacionHorario.objects.create(empresa=self.e1, empleado=self.ana, horario=self.noche, vigente_desde=date(2026, 10, 6))
        self.assertEqual(self.dia(self.ana, LUNES).horario, self.oficina)
        self.assertEqual(self.dia(self.ana, date(2026, 10, 6)).horario, self.noche)

    def test_no_calcula_fuera_del_periodo_laboral(self):
        self.assertEqual(motor.calcular(self.ana, date(2024, 1, 1), date(2024, 1, 5)), [])


class AjustesYAutorizacionesTests(MotorMixin, TestCase):
    def test_ajuste_agrega_la_marca_faltante_y_recalcula(self):
        self.marca(self.ana, '2026-10-05 08:00')
        self.assertEqual(self.dia(self.ana, LUNES).estado, 'incompleto')
        r = self.cliente(self.gestor1).post('/api/ajustes-marcacion/', {
            'empleado': self.ana.pk, 'accion': 'agregar', 'fecha_hora': '2026-10-05T17:00:00-03:00', 'tipo': 'salida',
            'motivo': 'Olvidó marcar la salida'})
        self.assertEqual(r.status_code, 201, r.data)
        with self.captureOnCommitCallbacks(execute=True):
            a = self.cliente(self.admin1).post(f'/api/ajustes-marcacion/{r.data["id"]}/aprobar/')
        self.assertEqual(a.status_code, 200, a.data)
        nueva = Marcacion.objects.get(pk=a.data['marcacion_creada'])
        self.assertEqual((nueva.metodo, nueva.nivel_verificacion), ('manual', 'manual_aprobado'))
        self.assertEqual(DiaAsistencia.objects.get(empleado=self.ana, fecha=LUNES).estado, 'presente')

    def test_ajuste_anula_sin_editar_la_original(self):
        self.marca(self.ana, '2026-10-05 08:00')
        erronea = self.marca(self.ana, '2026-10-05 08:01')
        self.marca(self.ana, '2026-10-05 17:00', 'salida')
        r = self.cliente(self.admin1).post('/api/ajustes-marcacion/', {
            'empleado': self.ana.pk, 'accion': 'anular', 'marcacion': erronea.pk, 'motivo': 'Marcó dos veces'})
        with self.captureOnCommitCallbacks(execute=True):
            self.cliente(self.gestor1).post(f'/api/ajustes-marcacion/{r.data["id"]}/aprobar/')
        erronea.refresh_from_db()
        self.assertTrue(erronea.anulada)
        self.assertEqual(erronea.fecha_hora.astimezone(ZONA).strftime('%H:%M'), '08:01')  # la original no se toca
        self.assertEqual(DiaAsistencia.objects.get(empleado=self.ana, fecha=LUNES).estado, 'presente')

    def test_el_empleado_pide_correccion_solo_para_si(self):
        datos = {'accion': 'agregar', 'fecha_hora': '2026-10-05T17:00:00-03:00', 'tipo': 'salida', 'motivo': 'Me olvidé'}
        cliente = self.cliente(self.usr_ana)
        r = cliente.post('/api/ajustes-marcacion/', {**datos, 'empleado': self.ana.pk})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['estado'], 'pendiente')
        self.assertEqual(cliente.post('/api/ajustes-marcacion/', {**datos, 'empleado': self.beto.pk}).status_code, 400)
        self.assertEqual(cliente.post(f'/api/ajustes-marcacion/{r.data["id"]}/aprobar/').status_code, 403)
        self.assertEqual(cliente.post('/api/autorizaciones-extra/', {'empleado': self.ana.pk, 'fecha': '2026-10-05',
                                                                     'minutos_solicitados': 60, 'motivo': 'x'}).status_code, 403)

    def test_separacion_de_quien_pide_y_quien_aprueba(self):
        config = ConfiguracionMarcacion.de(self.e1)
        config.exigir_aprobador_distinto = True
        config.save()
        r = self.cliente(self.admin1).post('/api/autorizaciones-extra/', {
            'empleado': self.ana.pk, 'fecha': '2026-10-05', 'minutos_solicitados': 60, 'motivo': 'Cierre'})
        self.assertEqual(self.cliente(self.admin1).post(f'/api/autorizaciones-extra/{r.data["id"]}/aprobar/').status_code, 403)

    def test_horas_extra_las_aprueba_el_administrador_no_el_gestor(self):
        r = self.cliente(self.gestor1).post('/api/autorizaciones-extra/', {
            'empleado': self.ana.pk, 'fecha': '2026-10-05', 'minutos_solicitados': 60, 'motivo': 'Cierre'})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.cliente(self.gestor1).post(f'/api/autorizaciones-extra/{r.data["id"]}/aprobar/').status_code, 403)
        self.assertEqual(self.cliente(self.admin1).post(f'/api/autorizaciones-extra/{r.data["id"]}/aprobar/',
                                                        {'minutos_aprobados': 90}).status_code, 400)
        a = self.cliente(self.admin1).post(f'/api/autorizaciones-extra/{r.data["id"]}/aprobar/', {'minutos_aprobados': 45})
        self.assertEqual(a.data['minutos_aprobados'], 45)

    def test_calcular_periodo_y_permisos(self):
        self.assertEqual(self.cliente(self.usr_ana).post('/api/dias-asistencia/calcular/', {'desde': '2026-10-05'}).status_code, 403)
        r = self.cliente(self.gestor1).post('/api/dias-asistencia/calcular/', {'desde': '2026-10-05', 'hasta': '2026-10-09'})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertGreaterEqual(r.data['dias'], 10)
        self.assertEqual(self.cliente(self.admin1).post('/api/dias-asistencia/calcular/',
                                                        {'desde': '2026-01-01', 'hasta': '2026-10-01'}).status_code, 400)
        # El empleado ve sus días (con su explicación), no los de otros.
        dias = self.cliente(self.usr_ana).get('/api/dias-asistencia/').data
        self.assertEqual({d['empleado'] for d in dias['results']}, {self.ana.pk})
        detalle = self.cliente(self.usr_ana).get(f'/api/dias-asistencia/{dias["results"][0]["id"]}/').data
        self.assertIn('explicacion', detalle)
        self.assertIn('marcas', detalle)
        self.assertEqual(self.cliente(self.admin2).get(f'/api/dias-asistencia/{dias["results"][0]["id"]}/').status_code, 404)

    def test_una_marca_nueva_recalcula_el_dia(self):
        from asistencia.marcador import registrar
        from asistencia.models import TerminalMarcacion
        terminal = TerminalMarcacion.objects.create(empresa=self.e1, codigo='T', nombre='T')
        with self.captureOnCommitCallbacks(execute=True):
            registrar(self.ana, terminal, Marcacion.MANUAL, 'manual_aprobado')
        from django.utils import timezone
        self.assertTrue(DiaAsistencia.objects.filter(empleado=self.ana, fecha=timezone.localdate()).exists())
