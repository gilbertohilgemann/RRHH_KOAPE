"""Perfiles y aislamiento (§11 bis, regla técnica 8): cada cambio de acceso
tiene que tener su prueba acá."""
from django.contrib.auth.models import Group, User
from django.test import TestCase
from rest_framework.test import APIClient

from core import alcance
from core.datos_prueba import EscenarioMixin
from core.models import EventoAuditoria
from cuentas import perfiles
from plataforma.models import Empresa


class PerfilesInicialesTests(TestCase):
    def test_se_crean_los_cuatro_perfiles_con_permisos(self):
        for nombre in alcance.GRUPOS_INICIALES:
            self.assertTrue(Group.objects.filter(name=nombre).exists(), nombre)
        gestor = Group.objects.get(name=alcance.GRUPO_GESTOR)
        codigos = set(gestor.permissions.values_list('codename', flat=True))
        self.assertIn('view_empleado', codigos)
        self.assertNotIn('add_empleado', codigos)
        self.assertNotIn('dar_baja_empleado', codigos)
        self.assertNotIn('gestionar_usuarios', codigos)

    def test_todos_los_permisos_iniciales_existen(self):
        from django.contrib.auth.models import Permission
        for grupo, permisos in perfiles.PERMISOS_INICIALES.items():
            if permisos == '*':
                continue
            for codigo in permisos:
                app, codename = codigo.split('.')
                self.assertTrue(Permission.objects.filter(content_type__app_label=app, codename=codename).exists(),
                                f'{grupo}: no existe el permiso {codigo}')


class IngresoTests(EscenarioMixin, TestCase):
    def test_ingreso_devuelve_token_y_perfil(self):
        r = APIClient().post('/api/sesion/ingresar/', {'usuario': 'admin1', 'clave': 'clave-de-prueba-123'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['usuario']['nivel'], alcance.NIVEL_ADMINISTRADOR)
        self.assertEqual(r.data['usuario']['empresa']['id'], self.e1.pk)
        self.assertTrue(EventoAuditoria.objects.filter(accion=EventoAuditoria.INGRESO, nombre_usuario='admin1').exists())

    def test_ingreso_fallido_queda_en_la_auditoria(self):
        r = APIClient().post('/api/sesion/ingresar/', {'usuario': 'admin1', 'clave': 'mal'})
        self.assertEqual(r.status_code, 400)
        evento = EventoAuditoria.objects.get(accion=EventoAuditoria.INGRESO_FALLIDO)
        self.assertEqual(evento.empresa, self.e1)

    def test_sin_perfil_no_entra(self):
        r = APIClient().post('/api/sesion/ingresar/', {'usuario': 'sin_perfil', 'clave': 'clave-de-prueba-123'})
        self.assertEqual(r.status_code, 403)

    def test_empresa_inactiva_no_entra(self):
        self.e2.activa = False
        self.e2.save()
        r = APIClient().post('/api/sesion/ingresar/', {'usuario': 'admin2', 'clave': 'clave-de-prueba-123'})
        self.assertEqual(r.status_code, 403)

    def test_empleado_sin_legajo_no_entra(self):
        from core.datos_prueba import crear_usuario
        crear_usuario('suelto', self.e1, [alcance.GRUPO_EMPLEADO])
        r = APIClient().post('/api/sesion/ingresar/', {'usuario': 'suelto', 'clave': 'clave-de-prueba-123'})
        self.assertEqual(r.status_code, 403)


class AislamientoTests(EscenarioMixin, TestCase):
    def test_administrador_ve_solo_su_empresa(self):
        r = self.cliente(self.admin1).get('/api/empleados/')
        self.assertEqual(self.ids(r), {self.ana.pk, self.beto.pk})

    def test_id_de_otra_empresa_no_existe(self):
        self.assertEqual(self.cliente(self.admin1).get(f'/api/empleados/{self.ceci_e2.pk}/').status_code, 404)
        self.assertEqual(self.cliente(self.admin1).patch(f'/api/empleados/{self.ceci_e2.pk}/',
                                                         {'telefono': '1'}).status_code, 404)

    def test_gestor_limitado_a_una_sucursal(self):
        r = self.cliente(self.gestor_norte).get('/api/empleados/')
        self.assertEqual(self.ids(r), {self.beto.pk})
        r = self.cliente(self.gestor_norte).get('/api/sucursales/')
        self.assertEqual(self.ids(r), {self.norte.pk})

    def test_empleado_ve_solo_su_legajo_sin_observaciones(self):
        self.ana.observaciones = 'Nota interna'
        self.ana.save()
        r = self.cliente(self.usr_ana).get('/api/empleados/')
        self.assertEqual(self.ids(r), {self.ana.pk})
        self.assertNotIn('observaciones', r.data['results'][0])
        self.assertEqual(self.cliente(self.usr_ana).get(f'/api/empleados/{self.beto.pk}/').status_code, 404)

    def test_empleado_no_ve_datos_generales(self):
        cliente = self.cliente(self.usr_ana)
        for ruta in ('/api/departamentos/', '/api/sucursales/', '/api/usuarios/', '/api/auditoria/'):
            self.assertEqual(cliente.get(ruta).status_code, 403, ruta)
        self.assertEqual(cliente.get('/api/resumen/').data, {})

    def test_sin_perfil_no_ve_nada(self):
        self.assertEqual(self.cliente(self.sin_perfil).get('/api/empleados/').status_code, 403)

    def test_plataforma_ve_todo(self):
        r = self.cliente(self.plataforma).get('/api/empleados/')
        self.assertEqual(self.ids(r), {self.ana.pk, self.beto.pk, self.ceci_e2.pk})

    def test_relacion_de_otra_empresa_se_rechaza(self):
        r = self.cliente(self.admin1).post('/api/empleados/', {
            'codigo': 'E099', 'numero_documento': '999', 'primer_nombre': 'X', 'primer_apellido': 'Y',
            'fecha_ingreso': '2026-01-05', 'departamento': self.ventas_e2.pk,
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn('departamento', r.data)

    def test_la_empresa_la_fija_el_servidor(self):
        r = self.cliente(self.admin1).post('/api/empleados/', {
            'codigo': 'E050', 'numero_documento': '5050', 'primer_nombre': 'X', 'primer_apellido': 'Y',
            'fecha_ingreso': '2026-01-05', 'empresa': self.e2.pk,
        })
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['empresa'], self.e1.pk)

    def test_filtrar_un_modelo_sin_ruta_falla_ruidosamente(self):
        with self.assertRaises(ValueError):
            alcance.filtrar(User.objects.all(), self.admin1)


class PermisosPorPerfilTests(EscenarioMixin, TestCase):
    NUEVO = {'codigo': 'E100', 'numero_documento': '100100', 'primer_nombre': 'Nuevo', 'primer_apellido': 'Empleado',
             'fecha_ingreso': '2026-03-01'}

    def test_gestor_no_da_de_alta_ni_de_baja_empleados(self):
        cliente = self.cliente(self.gestor1)
        self.assertEqual(cliente.post('/api/empleados/', self.NUEVO).status_code, 403)
        self.assertEqual(cliente.post(f'/api/empleados/{self.ana.pk}/dar_baja/',
                                      {'fecha_egreso': '2026-05-01', 'motivo': 'x'}).status_code, 403)

    def test_gestor_no_administra_usuarios_sucursales_ni_empresa(self):
        cliente = self.cliente(self.gestor1)
        self.assertEqual(cliente.get('/api/usuarios/').status_code, 403)
        self.assertEqual(cliente.post('/api/sucursales/', {'codigo': 'X', 'nombre': 'X'}).status_code, 403)
        self.assertEqual(cliente.patch(f'/api/empresas/{self.e1.pk}/', {'telefono': '1'}).status_code, 403)

    def test_empleado_no_edita_su_legajo(self):
        self.assertEqual(self.cliente(self.usr_ana).patch(f'/api/empleados/{self.ana.pk}/',
                                                          {'telefono': '1'}).status_code, 403)

    def test_administrador_da_de_alta_un_empleado(self):
        r = self.cliente(self.admin1).post('/api/empleados/', self.NUEVO)
        self.assertEqual(r.status_code, 201, r.data)

    def test_administrador_no_crea_empresas(self):
        # 403 (sin permiso de alta) o 405 (la API no da altas de empresas): las dos lo rechazan.
        self.assertIn(self.cliente(self.admin1).post('/api/empresas/', {'nombre': 'Nueva'}).status_code, (403, 405))
        self.assertFalse(Empresa.objects.filter(nombre='Nueva').exists())

    def test_administrador_edita_su_empresa_pero_no_la_desactiva(self):
        r = self.cliente(self.admin1).patch(f'/api/empresas/{self.e1.pk}/', {'telefono': '021 555', 'activa': False})
        self.assertEqual(r.status_code, 200)
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.telefono, '021 555')
        self.assertTrue(self.e1.activa)

    def test_nadie_borra_empleados_ni_sucursales(self):
        for usuario in (self.admin1, self.plataforma):
            cliente = self.cliente(usuario)
            self.assertIn(cliente.delete(f'/api/empleados/{self.ana.pk}/').status_code, (403, 405))
            self.assertIn(cliente.delete(f'/api/sucursales/{self.centro.pk}/').status_code, (403, 405))


class LicenciasAccesoTests(EscenarioMixin, TestCase):
    """Fase 7: los tres perfiles, una sucursal limitada y otra empresa sobre los modelos de licencias."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from datetime import date
        from licencias.models import CertificadoMedico, MovimientoVacaciones, SolicitudLicencia, TipoLicencia
        vac = TipoLicencia.objects.get(empresa=None, codigo='VAC')
        cls.lic_ana = SolicitudLicencia.objects.create(empresa=cls.e1, empleado=cls.ana, tipo=vac, fecha_desde=date(2026, 10, 5),
                                                       fecha_hasta=date(2026, 10, 5), dias=1)
        cls.lic_beto = SolicitudLicencia.objects.create(empresa=cls.e1, empleado=cls.beto, tipo=vac, fecha_desde=date(2026, 10, 5),
                                                        fecha_hasta=date(2026, 10, 5), dias=1)
        cls.lic_ceci = SolicitudLicencia.objects.create(empresa=cls.e2, empleado=cls.ceci_e2, tipo=vac,
                                                        fecha_desde=date(2026, 10, 5), fecha_hasta=date(2026, 10, 5), dias=1)
        for empresa, empleado in ((cls.e1, cls.ana), (cls.e1, cls.beto), (cls.e2, cls.ceci_e2)):
            MovimientoVacaciones.objects.create(empresa=empresa, empleado=empleado, fecha=date(2026, 1, 2),
                                                tipo='ajuste', dias=5, motivo='x')
            CertificadoMedico.objects.create(empresa=empresa, empleado=empleado, fecha_desde=date(2026, 9, 1),
                                             fecha_hasta=date(2026, 9, 2), emisor='Clínica')

    RUTAS = ('/api/licencias/', '/api/movimientos-vacaciones/', '/api/certificados-medicos/')

    def empleados_vistos(self, usuario, ruta):
        r = self.cliente(usuario).get(ruta)
        self.assertEqual(r.status_code, 200, (usuario, ruta))
        return {f['empleado'] for f in r.data['results']}

    def test_cada_perfil_ve_lo_suyo(self):
        for ruta in self.RUTAS:
            self.assertEqual(self.empleados_vistos(self.admin1, ruta), {self.ana.pk, self.beto.pk}, ruta)
            self.assertEqual(self.empleados_vistos(self.gestor1, ruta), {self.ana.pk, self.beto.pk}, ruta)
            self.assertEqual(self.empleados_vistos(self.gestor_norte, ruta), {self.beto.pk}, ruta)
            self.assertEqual(self.empleados_vistos(self.usr_ana, ruta), {self.ana.pk}, ruta)
            self.assertEqual(self.empleados_vistos(self.admin2, ruta), {self.ceci_e2.pk}, ruta)
            self.assertEqual(self.cliente(self.sin_perfil).get(ruta).status_code, 403, ruta)

    def test_id_de_otra_empresa_no_existe(self):
        self.assertEqual(self.cliente(self.admin1).get(f'/api/licencias/{self.lic_ceci.pk}/').status_code, 404)
        self.assertEqual(self.cliente(self.admin1).post(f'/api/licencias/{self.lic_ceci.pk}/aprobar/').status_code, 404)
        self.assertEqual(self.cliente(self.usr_ana).get(f'/api/licencias/{self.lic_beto.pk}/').status_code, 404)

    def test_el_empleado_no_configura_ni_ajusta(self):
        cliente = self.cliente(self.usr_ana)
        self.assertEqual(cliente.post('/api/tipos-licencia/', {'codigo': 'X', 'nombre': 'X'}).status_code, 403)
        self.assertEqual(cliente.get('/api/escala-vacaciones/').status_code, 403)
        self.assertEqual(cliente.post('/api/movimientos-vacaciones/', {'empleado': self.ana.pk, 'fecha': '2026-10-01',
                                                                       'tipo': 'ajuste', 'dias': '9', 'motivo': 'x'}).status_code, 403)
        self.assertEqual(cliente.post('/api/certificados-medicos/', {}).status_code, 403)

    def test_el_gestor_no_configura_tipos_ni_escala(self):
        cliente = self.cliente(self.gestor1)
        self.assertEqual(cliente.post('/api/tipos-licencia/', {'codigo': 'X', 'nombre': 'X'}).status_code, 403)
        self.assertEqual(cliente.post('/api/escala-vacaciones/', {'desde_anios': 1, 'dias': 20}).status_code, 403)
        self.assertEqual(cliente.get('/api/escala-vacaciones/').status_code, 200)


class ReglasYConceptosAccesoTests(EscenarioMixin, TestCase):
    """Fase 8: reglas legales, conceptos, reglas de cálculo y conceptos fijos por perfil y empresa."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from datetime import date
        from legal.models import ConjuntoReglas
        from nomina.models import ConceptoNomina, ConceptoRecurrente
        cls.conjunto_e2 = ConjuntoReglas.objects.create(empresa=cls.e2, codigo='CONV', nombre='Convenio dos',
                                                        vigente_desde=date(2026, 1, 1))
        cls.concepto_e2 = ConceptoNomina.objects.create(empresa=cls.e2, codigo='PROPIO', nombre='Propio', tipo='haber')
        bono = ConceptoNomina.objects.get(empresa=None, codigo='BONO')
        for empresa, empleado in ((cls.e1, cls.ana), (cls.e1, cls.beto), (cls.e2, cls.ceci_e2)):
            ConceptoRecurrente.objects.create(empresa=empresa, empleado=empleado, concepto=bono, monto=1,
                                              vigente_desde=date(2026, 8, 1), motivo='x')

    def test_conceptos_fijos_segun_perfil(self):
        def vistos(usuario):
            return {f['empleado'] for f in self.cliente(usuario).get('/api/conceptos-fijos/').data['results']}
        self.assertEqual(vistos(self.admin1), {self.ana.pk, self.beto.pk})
        self.assertEqual(vistos(self.gestor_norte), {self.beto.pk})
        self.assertEqual(vistos(self.usr_ana), {self.ana.pk})
        self.assertEqual(vistos(self.admin2), {self.ceci_e2.pk})
        self.assertEqual(self.cliente(self.sin_perfil).get('/api/conceptos-fijos/').status_code, 403)

    def test_el_empleado_no_ve_reglas_ni_conceptos(self):
        cliente = self.cliente(self.usr_ana)
        for ruta in ('/api/reglas-legales/', '/api/conceptos-nomina/', '/api/reglas-concepto/', '/api/variables-nomina/'):
            self.assertEqual(cliente.get(ruta).status_code, 403, ruta)
        self.assertEqual(cliente.post('/api/conceptos-fijos/', {}).status_code, 403)

    def test_el_gestor_solo_consulta_la_configuracion(self):
        cliente = self.cliente(self.gestor1)
        self.assertEqual(cliente.get('/api/reglas-legales/').status_code, 200)
        self.assertEqual(cliente.post('/api/reglas-legales/', {'codigo': 'X', 'nombre': 'X', 'vigente_desde': '2026-01-01'}).status_code, 403)
        self.assertEqual(cliente.post('/api/conceptos-nomina/', {'codigo': 'X', 'nombre': 'X', 'tipo': 'haber'}).status_code, 403)
        self.assertEqual(cliente.post('/api/reglas-concepto/', {}).status_code, 403)

    def test_otra_empresa_no_existe(self):
        cliente = self.cliente(self.admin1)
        self.assertEqual(cliente.get(f'/api/reglas-legales/{self.conjunto_e2.pk}/').status_code, 404)
        self.assertEqual(cliente.get(f'/api/conceptos-nomina/{self.concepto_e2.pk}/').status_code, 404)
        r = cliente.post('/api/reglas-concepto/', {'concepto': self.concepto_e2.pk, 'vigente_desde': '2026-07-01', 'expresion': '1'})
        self.assertEqual(r.status_code, 400)


class NovedadesAccesoTests(EscenarioMixin, TestCase):
    """Fase 9: novedades, descuentos, anticipos, préstamos y cuotas por perfil, sucursal y empresa."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from datetime import date
        from nomina.models import ConceptoNomina
        from novedades.models import Anticipo, Novedad, Prestamo
        bono = ConceptoNomina.objects.get(empresa=None, codigo='BONO')
        for empresa, empleado in ((cls.e1, cls.ana), (cls.e1, cls.beto), (cls.e2, cls.ceci_e2)):
            Novedad.objects.create(empresa=empresa, empleado=empleado, concepto=bono, periodo_desde=date(2026, 9, 1),
                                   periodo_hasta=date(2026, 9, 30), monto=1, descripcion='x')
            Anticipo.objects.create(empresa=empresa, empleado=empleado, fecha=date(2026, 10, 1), monto_solicitado=1, motivo='x')
            Prestamo.objects.create(empresa=empresa, empleado=empleado, fecha=date(2026, 10, 1), capital=1, cantidad_cuotas=1,
                                    primer_mes=date(2026, 11, 1), motivo='x')
        cls.anticipo_e2 = Anticipo.objects.get(empresa=cls.e2)

    RUTAS = ('/api/novedades/', '/api/anticipos/', '/api/prestamos/')

    def test_cada_perfil_ve_lo_suyo(self):
        for ruta in self.RUTAS:
            def vistos(usuario):
                r = self.cliente(usuario).get(ruta)
                self.assertEqual(r.status_code, 200, ruta)
                return {f['empleado'] for f in r.data['results']}
            self.assertEqual(vistos(self.admin1), {self.ana.pk, self.beto.pk}, ruta)
            self.assertEqual(vistos(self.gestor_norte), {self.beto.pk}, ruta)
            self.assertEqual(vistos(self.usr_ana), {self.ana.pk}, ruta)
            self.assertEqual(vistos(self.admin2), {self.ceci_e2.pk}, ruta)
            self.assertEqual(self.cliente(self.sin_perfil).get(ruta).status_code, 403, ruta)

    def test_otra_empresa_no_existe(self):
        self.assertEqual(self.cliente(self.admin1).post(f'/api/anticipos/{self.anticipo_e2.pk}/aprobar/').status_code, 404)
        r = self.cliente(self.admin1).post('/api/anticipos/', {'empleado': self.ceci_e2.pk, 'fecha': '2026-10-14',
                                                               'monto_solicitado': '1', 'motivo': 'x'})
        self.assertEqual(r.status_code, 400)

    def test_el_gestor_no_aprueba_ni_paga(self):
        from novedades.models import Anticipo, Prestamo
        anticipo = Anticipo.objects.get(empleado=self.ana)
        prestamo = Prestamo.objects.get(empleado=self.ana)
        cliente = self.cliente(self.gestor1)
        self.assertEqual(cliente.post(f'/api/anticipos/{anticipo.pk}/aprobar/').status_code, 403)
        self.assertEqual(cliente.post(f'/api/anticipos/{anticipo.pk}/pagar/').status_code, 403)
        self.assertEqual(cliente.post(f'/api/prestamos/{prestamo.pk}/desembolsar/').status_code, 403)


class UsuariosTests(EscenarioMixin, TestCase):
    def crear(self, **datos):
        base = {'username': 'nuevo', 'first_name': 'Nuevo', 'password': 'Una-clave-larga-2026', 'roles': ['Gestor RR. HH.']}
        base.update(datos)
        return self.cliente(self.admin1).post('/api/usuarios/', base, format='json')

    def test_administrador_lista_solo_usuarios_de_su_empresa(self):
        r = self.cliente(self.admin1).get('/api/usuarios/')
        nombres = {u['username'] for u in r.data['results']}
        self.assertIn('gestor1', nombres)
        self.assertNotIn('admin2', nombres)
        self.assertNotIn('plataforma', nombres)

    def test_alta_de_usuario_con_perfil_y_auditoria(self):
        r = self.crear()
        self.assertEqual(r.status_code, 201, r.data)
        usuario = User.objects.get(username='nuevo')
        self.assertEqual(usuario.perfil.empresa, self.e1)
        self.assertTrue(usuario.check_password('Una-clave-larga-2026'))
        evento = EventoAuditoria.objects.get(accion=EventoAuditoria.ALTA, modelo='auth.User', objeto_id=str(usuario.pk))
        self.assertNotIn('password', str(evento.datos_nuevos))

    def test_no_puede_asignar_el_perfil_de_plataforma(self):
        self.assertEqual(self.crear(roles=['Koape']).status_code, 400)

    def test_empleado_necesita_legajo_de_su_empresa(self):
        self.assertEqual(self.crear(roles=['Empleado']).status_code, 400)
        self.assertEqual(self.crear(roles=['Empleado'], empleado=self.ceci_e2.pk).status_code, 400)
        self.assertEqual(self.crear(roles=['Empleado'], empleado=self.ana.pk).status_code, 400)  # ya vinculado
        self.assertEqual(self.crear(roles=['Empleado'], empleado=self.beto.pk).status_code, 201)

    def test_no_se_eleva_privilegios_a_si_mismo(self):
        cliente = self.cliente(self.admin1)
        r = cliente.patch(f'/api/usuarios/{self.admin1.pk}/', {'roles': ['Administrador', 'Gestor RR. HH.']}, format='json')
        self.assertEqual(r.status_code, 400)
        r = cliente.patch(f'/api/usuarios/{self.admin1.pk}/', {'is_active': False}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_cambio_de_perfiles_de_otro_queda_auditado(self):
        r = self.cliente(self.admin1).patch(f'/api/usuarios/{self.gestor1.pk}/', {'roles': ['Administrador']},
                                            format='json')
        self.assertEqual(r.status_code, 200, r.data)
        evento = EventoAuditoria.objects.get(accion=EventoAuditoria.PERMISOS, objeto_id=str(self.gestor1.pk))
        self.assertEqual(evento.datos_anteriores['perfiles'], ['Gestor RR. HH.'])
        self.assertEqual(evento.datos_nuevos['perfiles'], ['Administrador'])

    def test_no_toca_usuarios_de_otra_empresa(self):
        r = self.cliente(self.admin1).patch(f'/api/usuarios/{self.admin2.pk}/', {'is_active': False}, format='json')
        self.assertEqual(r.status_code, 404)

    def test_sucursal_de_otra_empresa_se_rechaza(self):
        self.assertEqual(self.crear(sucursales=[self.suc_e2.pk]).status_code, 400)

    def test_los_usuarios_no_se_borran(self):
        self.assertEqual(self.cliente(self.admin1).delete(f'/api/usuarios/{self.gestor1.pk}/').status_code, 405)
