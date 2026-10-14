"""Regímenes, horarios con tramos, asignaciones y feriados."""
from datetime import date, time

from django.test import TestCase

from core.datos_prueba import EscenarioMixin
from core.models import EventoAuditoria
from jornada.models import (AsignacionHorario, CalendarioFeriados, DiaFeriado, Horario, RegimenJornada, TramoHorario,
                            feriado_en, horario_vigente)

OFICINA = [  # lunes a viernes 08–12 y 13–17
    {'dia_semana': d, 'hora_inicio': i, 'hora_fin': f} for d in range(5) for i, f in (('08:00', '12:00'), ('13:00', '17:00'))
]


class JornadaMixin(EscenarioMixin):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.diurna = RegimenJornada.objects.get(empresa=None, codigo='DIURNA')
        cls.nocturna = RegimenJornada.objects.get(empresa=None, codigo='NOCTURNA')

    def crear_horario(self, tramos=OFICINA, usuario=None, **extra):
        datos = {'codigo': 'OF', 'nombre': 'Oficina', 'regimen': self.diurna.pk, 'tramos': tramos}
        datos.update(extra)
        return self.cliente(usuario or self.admin1).post('/api/horarios/', datos, format='json')


class HorarioTests(JornadaMixin, TestCase):
    def test_crear_con_tramos_y_resumen(self):
        r = self.crear_horario()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['minutos_semana'], 40 * 60)
        self.assertEqual(r.data['resumen'], 'Lun–Vie 08:00–12:00, 13:00–17:00')
        self.assertEqual(len(r.data['tramos']), 10)
        self.assertFalse(r.data['cruza_medianoche'])

    def test_tramos_superpuestos_se_rechazan(self):
        r = self.crear_horario([{'dia_semana': 0, 'hora_inicio': '08:00', 'hora_fin': '12:00'},
                                {'dia_semana': 0, 'hora_inicio': '11:00', 'hora_fin': '15:00'}])
        self.assertEqual(r.status_code, 400)
        self.assertIn('superponen', str(r.data))

    def test_turno_noche_cruza_la_medianoche(self):
        r = self.crear_horario([{'dia_semana': d, 'hora_inicio': '22:00', 'hora_fin': '05:00'} for d in range(7)],
                               regimen=self.nocturna.pk, codigo='NOCHE', nombre='Noche')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data['cruza_medianoche'])
        self.assertEqual(r.data['minutos_semana'], 7 * 7 * 60)

    def test_noche_del_domingo_no_puede_pisar_el_lunes(self):
        r = self.crear_horario([{'dia_semana': 6, 'hora_inicio': '22:00', 'hora_fin': '06:00'},
                                {'dia_semana': 0, 'hora_inicio': '05:00', 'hora_fin': '09:00'}])
        self.assertEqual(r.status_code, 400)

    def test_descanso_y_advertencias_contra_el_regimen(self):
        largo = [{'dia_semana': d, 'hora_inicio': '07:00', 'hora_fin': '18:00', 'descanso_minutos': 60} for d in range(6)]
        r = self.crear_horario(largo)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['minutos_semana'], 6 * 10 * 60)  # 11 h menos 1 de descanso
        avisos = ' '.join(r.data['advertencias'])
        self.assertIn('máximo diario', avisos)
        self.assertIn('máximo semanal', avisos)
        self.assertIn('no fueron verificados', avisos)

    def test_descanso_mayor_que_el_tramo(self):
        r = self.crear_horario([{'dia_semana': 0, 'hora_inicio': '08:00', 'hora_fin': '09:00', 'descanso_minutos': 60}])
        self.assertEqual(r.status_code, 400)

    def test_editar_reemplaza_los_tramos_y_queda_auditado(self):
        r = self.crear_horario()
        cliente = self.cliente(self.admin1)
        r = cliente.patch(f'/api/horarios/{r.data["id"]}/', {'tramos': [
            {'dia_semana': 5, 'hora_inicio': '08:00', 'hora_fin': '12:00'}]}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['resumen'], 'Sáb 08:00–12:00')
        self.assertEqual(TramoHorario.objects.filter(horario_id=r.data['id']).count(), 1)
        evento = EventoAuditoria.objects.get(accion=EventoAuditoria.MODIFICACION, modelo='jornada.Horario')
        self.assertEqual(evento.datos_anteriores['tramos'], 'Lun–Vie 08:00–12:00, 13:00–17:00')

    def test_gestor_no_define_horarios(self):
        self.assertEqual(self.crear_horario(usuario=self.gestor1).status_code, 403)

    def test_otra_empresa_no_ve_el_horario(self):
        r = self.crear_horario()
        self.assertEqual(self.cliente(self.admin2).get(f'/api/horarios/{r.data["id"]}/').status_code, 404)

    def test_regimen_global_no_se_modifica_desde_la_empresa(self):
        r = self.cliente(self.admin1).patch(f'/api/regimenes-jornada/{self.diurna.pk}/', {'verificado': True})
        self.assertEqual(r.status_code, 403)


class AsignacionTests(JornadaMixin, TestCase):
    def setUp(self):
        self.oficina = Horario.objects.create(empresa=self.e1, codigo='OF', nombre='Oficina', regimen=self.diurna)
        TramoHorario.objects.create(horario=self.oficina, dia_semana=0, hora_inicio=time(8), hora_fin=time(12))
        self.tarde = Horario.objects.create(empresa=self.e1, codigo='TA', nombre='Tarde', regimen=self.diurna)

    def asignar(self, horario, desde, usuario=None, empleado=None, **extra):
        return self.cliente(usuario or self.gestor1).post('/api/asignaciones-horario/', {
            'empleado': (empleado or self.ana).pk, 'horario': horario.pk, 'vigente_desde': desde, **extra})

    def test_gestor_asigna_y_la_anterior_se_cierra(self):
        self.assertEqual(self.asignar(self.oficina, '2026-01-01').status_code, 201)
        r = self.asignar(self.tarde, '2026-07-01')
        self.assertEqual(r.status_code, 201, r.data)
        primera = AsignacionHorario.objects.get(horario=self.oficina)
        self.assertEqual(primera.vigente_hasta, date(2026, 6, 30))
        self.assertEqual(horario_vigente(self.ana, date(2026, 6, 30)), self.oficina)
        self.assertEqual(horario_vigente(self.ana, date(2026, 7, 1)), self.tarde)

    def test_no_se_superponen(self):
        self.asignar(self.oficina, '2026-03-01', vigente_hasta='2026-03-31')
        self.assertEqual(self.asignar(self.tarde, '2026-03-15', vigente_hasta='2026-04-15').status_code, 400)
        # Antes de una abierta que empieza después, tampoco.
        self.asignar(self.oficina, '2026-05-01')
        self.assertEqual(self.asignar(self.tarde, '2026-04-20').status_code, 400)

    def test_no_antes_del_ingreso(self):
        self.assertEqual(self.asignar(self.oficina, '2024-01-01').status_code, 400)

    def test_horario_de_otra_empresa_se_rechaza(self):
        ajeno = Horario.objects.create(empresa=self.e2, codigo='X', nombre='Ajeno', regimen=self.diurna)
        self.assertEqual(self.asignar(ajeno, '2026-01-01').status_code, 400)

    def test_empleado_ve_su_horario_y_no_el_de_otros(self):
        self.asignar(self.oficina, '2026-01-01')
        self.asignar(self.tarde, '2026-01-01', empleado=self.beto)
        r = self.cliente(self.usr_ana).get('/api/asignaciones-horario/')
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['resumen_horario'], 'Lun 08:00–12:00')
        self.assertEqual(self.cliente(self.usr_ana).get('/api/horarios/').status_code, 403)
        self.assertEqual(self.asignar(self.oficina, '2026-02-01', usuario=self.usr_ana).status_code, 403)

    def test_consulta_del_dia(self):
        self.asignar(self.oficina, '2026-01-01')
        r = self.cliente(self.admin1).get('/api/asignaciones-horario/vigente/', {'empleado': self.ana.pk, 'fecha': '2026-05-14'})
        self.assertEqual(r.data['horario']['nombre'], 'Oficina')
        self.assertEqual(r.data['feriado']['nombre'], 'Independencia Nacional')
        r = self.cliente(self.admin1).get('/api/asignaciones-horario/vigente/', {'empleado': self.ceci_e2.pk})
        self.assertEqual(r.status_code, 404)


class FeriadosTests(JornadaMixin, TestCase):
    def test_calendario_nacional_y_propio(self):
        self.assertEqual(feriado_en(self.e1, date(2026, 12, 25)).nombre, 'Navidad')
        r = self.cliente(self.admin1).post('/api/calendarios-feriados/', {
            'codigo': 'LOCAL', 'nombre': 'Feriados de Encarnación', 'anio': 2026,
            'dias': [{'fecha': '2026-03-25', 'nombre': 'Fundación de la ciudad', 'tipo': 'local'}]}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(feriado_en(self.e1, date(2026, 3, 25)).nombre, 'Fundación de la ciudad')
        self.assertIsNone(feriado_en(self.e2, date(2026, 3, 25)))  # la otra empresa no lo tiene
        self.assertNotIn(r.data['id'], self.ids(self.cliente(self.admin2).get('/api/calendarios-feriados/')))

    def test_fechas_del_año_y_sin_repetir(self):
        cliente = self.cliente(self.admin1)
        base = {'codigo': 'X', 'nombre': 'X', 'anio': 2026}
        r = cliente.post('/api/calendarios-feriados/', {**base, 'dias': [{'fecha': '2027-01-01', 'nombre': 'X'}]}, format='json')
        self.assertEqual(r.status_code, 400)
        r = cliente.post('/api/calendarios-feriados/', {**base, 'dias': [
            {'fecha': '2026-02-02', 'nombre': 'A'}, {'fecha': '2026-02-02', 'nombre': 'B'}]}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_el_nacional_no_lo_cambia_una_empresa(self):
        nacional = CalendarioFeriados.objects.get(empresa=None, codigo='PY-NACIONAL', anio=2026)
        r = self.cliente(self.admin1).patch(f'/api/calendarios-feriados/{nacional.pk}/', {'dias': []}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(DiaFeriado.objects.filter(calendario=nacional).count(), 12)

    def test_empleado_ve_los_feriados(self):
        r = self.cliente(self.usr_ana).get('/api/calendarios-feriados/')
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.data['count'], 1)
