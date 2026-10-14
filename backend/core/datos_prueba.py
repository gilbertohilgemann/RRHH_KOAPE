"""Escenario de prueba compartido por las pruebas automáticas: dos empresas
con sucursales, estructura y empleados, y un usuario por perfil. Todo
ficticio."""
from datetime import date

from django.contrib.auth.models import Group, User
from rest_framework.test import APIClient

from core import alcance
from cuentas.models import Perfil
from empleados.models import Departamento, Empleado, Puesto
from plataforma.models import Empresa, Sucursal


def crear_usuario(nombre, empresa=None, grupos=(), empleado=None, sucursales=(), **extra):
    usuario = User.objects.create_user(nombre, password='clave-de-prueba-123', **extra)
    if grupos:
        usuario.groups.set(Group.objects.filter(name__in=grupos))
    if empresa is not None:
        perfil = Perfil.objects.create(usuario=usuario, empresa=empresa, empleado=empleado)
        perfil.sucursales.set(sucursales)
    return usuario


def crear_empleado(empresa, codigo, documento, **extra):
    datos = {'primer_nombre': 'Nombre', 'primer_apellido': f'Apellido {codigo}', 'fecha_ingreso': date(2025, 1, 2)}
    datos.update(extra)
    return Empleado.objects.create(empresa=empresa, codigo=codigo, numero_documento=documento, **datos)


class EscenarioMixin:
    """Para usar en TestCase: `self.e1`, `self.e2` (empresas), sucursales,
    empleados y un cliente por perfil (`self.cliente(usuario)`)."""

    @classmethod
    def setUpTestData(cls):
        cls.e1 = Empresa.objects.create(nombre='Empresa Uno S.A.', ruc='80000001-1')
        cls.e2 = Empresa.objects.create(nombre='Empresa Dos S.A.', ruc='80000002-2')
        cls.centro = Sucursal.objects.create(empresa=cls.e1, codigo='CEN', nombre='Casa central')
        cls.norte = Sucursal.objects.create(empresa=cls.e1, codigo='NOR', nombre='Sucursal Norte')
        cls.suc_e2 = Sucursal.objects.create(empresa=cls.e2, codigo='CEN', nombre='Central Dos')
        cls.ventas = Departamento.objects.create(empresa=cls.e1, codigo='VEN', nombre='Ventas')
        cls.ventas_e2 = Departamento.objects.create(empresa=cls.e2, codigo='VEN', nombre='Ventas Dos')
        cls.cajero = Puesto.objects.create(empresa=cls.e1, codigo='CAJ', nombre='Cajero')

        cls.ana = crear_empleado(cls.e1, 'E001', '1000001', primer_nombre='Ana', sucursal=cls.centro,
                                 departamento=cls.ventas, puesto=cls.cajero)
        cls.beto = crear_empleado(cls.e1, 'E002', '1000002', primer_nombre='Beto', sucursal=cls.norte)
        cls.ceci_e2 = crear_empleado(cls.e2, 'E001', '2000001', primer_nombre='Ceci', sucursal=cls.suc_e2)

        cls.plataforma = User.objects.create_superuser('plataforma', password='clave-de-prueba-123')
        cls.admin1 = crear_usuario('admin1', cls.e1, [alcance.GRUPO_ADMINISTRADOR])
        cls.gestor1 = crear_usuario('gestor1', cls.e1, [alcance.GRUPO_GESTOR])
        cls.gestor_norte = crear_usuario('gestor_norte', cls.e1, [alcance.GRUPO_GESTOR], sucursales=[cls.norte])
        cls.usr_ana = crear_usuario('ana', cls.e1, [alcance.GRUPO_EMPLEADO], empleado=cls.ana)
        cls.admin2 = crear_usuario('admin2', cls.e2, [alcance.GRUPO_ADMINISTRADOR])
        cls.sin_perfil = crear_usuario('sin_perfil')

    def cliente(self, usuario):
        cliente = APIClient()
        cliente.force_authenticate(usuario)
        return cliente

    @staticmethod
    def ids(respuesta):
        return {fila['id'] for fila in respuesta.data['results']}
