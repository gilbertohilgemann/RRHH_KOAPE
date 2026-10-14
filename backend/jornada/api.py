"""Jornada: regímenes, horarios (con sus tramos), asignaciones de horario y
calendarios de feriados (con sus días).

- Regímenes y calendarios son catálogos: globales (plataforma) + propios de
  cada empresa, que solo modifica los suyos.
- Los horarios se guardan con todos sus tramos en una sola operación; la
  respuesta trae los minutos por semana, si cruza la medianoche, un resumen
  legible y las advertencias contra los máximos del régimen.
- Las asignaciones nunca se superponen: la anterior abierta se cierra sola."""
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from core import alcance
from core.api.base import CatalogoViewSet, ConAnidadosSerializer, RegistroSerializer, RegistroViewSet
from jornada.models import (AsignacionHorario, CalendarioFeriados, DiaFeriado, Horario, RegimenJornada, TramoHorario,
                            feriado_en, horario_vigente, validar_tramos)


class RegimenJornadaSerializer(RegistroSerializer):
    es_global = serializers.BooleanField(read_only=True)

    class Meta:
        model = RegimenJornada
        fields = '__all__'


class RegimenJornadaViewSet(CatalogoViewSet):
    serializer_class = RegimenJornadaSerializer
    search_fields = ['codigo', 'nombre']
    filtros_exactos = ('activo', 'tipo_jornada')


class TramoSerializer(serializers.ModelSerializer):
    minutos = serializers.SerializerMethodField()

    class Meta:
        model = TramoHorario
        exclude = ['horario']

    def get_minutos(self, tramo):
        return tramo.minutos_brutos


class HorarioSerializer(ConAnidadosSerializer):
    tramos = TramoSerializer(many=True, required=False)
    anidados = {'tramos': 'horario'}

    class Meta:
        model = Horario
        fields = '__all__'

    def validar_anidados(self, nombre, instancias):
        validar_tramos(instancias)

    def to_representation(self, horario):
        datos = super().to_representation(horario)
        datos.update({
            'minutos_semana': horario.minutos_semana,
            'horas_semana': f'{horario.minutos_semana // 60}:{horario.minutos_semana % 60:02d}',
            'cruza_medianoche': horario.cruza_medianoche,
            'resumen': horario.resumen(),
            'advertencias': horario.advertencias(),
        })
        return datos


class HorarioViewSet(RegistroViewSet):
    serializer_class = HorarioSerializer
    search_fields = ['codigo', 'nombre']
    filtros_exactos = ('activo', 'regimen')
    relaciones_extra = ('regimen',)

    def get_queryset(self):
        return super().get_queryset().prefetch_related('tramos')


class AsignacionHorarioSerializer(RegistroSerializer):
    class Meta:
        model = AsignacionHorario
        fields = '__all__'

    def to_representation(self, asignacion):
        datos = super().to_representation(asignacion)
        # El empleado ve su horario por acá (no tiene acceso a la lista de horarios).
        datos['resumen_horario'] = asignacion.horario.resumen()
        return datos


class AsignacionHorarioViewSet(RegistroViewSet):
    serializer_class = AsignacionHorarioSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'empleado__primer_nombre', 'horario__nombre']
    filtros_exactos = ('empleado', 'horario')
    campo_fecha = 'vigente_desde'
    relaciones_extra = ('empleado__sucursal',)

    def get_queryset(self):
        return super().get_queryset().prefetch_related('horario__tramos')

    @action(detail=False, methods=['get'])
    def vigente(self, request):
        """`GET .../vigente/?empleado=<id>&fecha=AAAA-MM-DD`: el horario de ese día y si es feriado."""
        from empleados.models import Empleado
        empleado = alcance.filtrar(Empleado.objects.all(), request.user).filter(pk=request.query_params.get('empleado') or 0).first()
        if empleado is None:
            return Response({'detail': 'Empleado no encontrado.'}, status=404)
        fecha = serializers.DateField().to_internal_value(request.query_params.get('fecha')) \
            if request.query_params.get('fecha') else None
        from django.utils import timezone
        fecha = fecha or timezone.localdate()
        horario = horario_vigente(empleado, fecha)
        feriado = feriado_en(empleado.empresa, fecha)
        return Response({
            'fecha': fecha,
            'horario': {'id': horario.pk, 'nombre': horario.nombre, 'resumen': horario.resumen(),
                        'minutos_del_dia': horario.minutos_dia(fecha.weekday())} if horario else None,
            'feriado': {'nombre': feriado.nombre, 'tipo': feriado.get_tipo_display()} if feriado else None,
        })


class DiaFeriadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiaFeriado
        fields = ['id', 'fecha', 'nombre', 'tipo']


class CalendarioFeriadosSerializer(ConAnidadosSerializer):
    dias = DiaFeriadoSerializer(many=True, required=False)
    anidados = {'dias': 'calendario'}
    es_global = serializers.BooleanField(read_only=True)

    class Meta:
        model = CalendarioFeriados
        fields = '__all__'

    def validar_anidados(self, nombre, instancias):
        from django.core.exceptions import ValidationError
        anio = self.initial_data.get('anio') or (self.instance.anio if self.instance else None)
        fechas = set()
        for dia in instancias:
            if anio and dia.fecha.year != int(anio):
                raise ValidationError(f'{dia.fecha:%d/%m/%Y}: tiene que ser del año {anio}.')
            if dia.fecha in fechas:
                raise ValidationError(f'{dia.fecha:%d/%m/%Y} está repetida.')
            fechas.add(dia.fecha)

    def to_representation(self, calendario):
        datos = super().to_representation(calendario)
        datos['cantidad_dias'] = len(datos.get('dias') or [])
        return datos


class CalendarioFeriadosViewSet(CatalogoViewSet):
    serializer_class = CalendarioFeriadosSerializer
    search_fields = ['codigo', 'nombre']
    filtros_exactos = ('anio', 'activo')

    def get_queryset(self):
        return super().get_queryset().prefetch_related('dias')
