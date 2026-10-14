"""Piezas reutilizables de la API: todas las apps del negocio arman sus
serializers y viewsets heredando de acá, así se comportan igual en lo más
importante — el aislamiento entre empresas (core/alcance.py) y la auditoría
(core/auditoria.py) — y además en filtros por fecha, textos legibles y manejo
de errores."""
from datetime import date

from django.core.exceptions import ValidationError as ValidationErrorDjango
from django.db import transaction
from django.db.models import ProtectedError
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from core import alcance, auditoria
from core.models import EventoAuditoria


def a_error_drf(error):
    """Convierte un ValidationError de Django (validaciones de los modelos)
    en uno de DRF, para que la app reciba el mensaje por campo."""
    if hasattr(error, 'message_dict'):
        return ValidationError(error.message_dict)
    return ValidationError({'non_field_errors': error.messages})


class RegistroSerializer(serializers.ModelSerializer):
    """Además de los campos del modelo, agrega a la respuesta:

    - `<campo>_texto` por cada relación y por cada campo con opciones: el texto
      legible (ej. `departamento_texto: "Ventas"`, `estado_texto: "Activo"`).
    - `texto`: el propio registro en forma legible (su __str__).
    - `creado_por` / `modificado_por`: nombres de usuario (solo lectura).

    Y restringe **todas** las relaciones editables a lo que el usuario puede
    ver: si alguien manda el id de un departamento de otra empresa, DRF
    responde "objeto no existe", sin revelar que existe en otro lado.

    La validación del modelo (`full_clean`) corre siempre antes de guardar,
    así las reglas de negocio valen igual desde la API y desde el admin."""

    creado_por = serializers.StringRelatedField(read_only=True)
    modificado_por = serializers.StringRelatedField(read_only=True)

    def get_fields(self):
        campos = super().get_fields()
        # Modelos sin auditoría de carga (intentos, filas importadas): sin esos campos.
        propios = {c.name for c in self.Meta.model._meta.concrete_fields}
        for nombre in ('creado_por', 'modificado_por'):
            if nombre not in propios:
                campos.pop(nombre, None)
        request = self.context.get('request')
        usuario = getattr(request, 'user', None)
        for campo in campos.values():
            relacion = getattr(campo, 'child_relation', campo)
            if isinstance(relacion, serializers.RelatedField) and not relacion.read_only and relacion.queryset is not None:
                if getattr(relacion.queryset.model, 'ruta_empresa', None) is not None \
                        or hasattr(relacion.queryset.model, 'filtrar_por_alcance'):
                    relacion.queryset = alcance.filtrar(relacion.queryset, usuario)
        if 'empresa' in campos:
            # La empresa la decide la API (ver RegistroViewSet.perform_create)
            # y no se cambia después de creado. Un usuario de empresa ni
            # siquiera la manda: si la mandara, se ignora.
            campos['empresa'].required = False
            if self.instance is not None or not alcance.es_plataforma(usuario):
                campos['empresa'].read_only = True
        return campos

    def to_representation(self, instancia):
        datos = super().to_representation(instancia)
        datos['texto'] = str(instancia)
        for campo in instancia._meta.concrete_fields:
            if campo.name in ('creado_por', 'modificado_por') or campo.name not in datos:
                continue
            if campo.is_relation:
                relacionado = getattr(instancia, campo.name)
                datos[f'{campo.name}_texto'] = str(relacionado) if relacionado else ''
            elif campo.choices:
                datos[f'{campo.name}_texto'] = getattr(instancia, f'get_{campo.name}_display')()
        if instancia.pk:
            for campo in instancia._meta.many_to_many:
                if campo.name in datos:
                    elegidos = list(getattr(instancia, campo.name).all())
                    datos[f'{campo.name}_texto'] = ', '.join(str(e) for e in elegidos)
                    datos[f'{campo.name}_opciones'] = [{'id': e.pk, 'texto': str(e)} for e in elegidos]
        return datos

    def validate(self, datos):
        datos = super().validate(datos)
        # full_clean del modelo con los datos nuevos (sin las relaciones
        # muchos-a-muchos, que se guardan después).
        modelo = self.Meta.model
        propios = {c.name for c in modelo._meta.concrete_fields}
        simples = {k: v for k, v in datos.items() if k in propios}
        if self.instance is not None:
            candidato = self.instance
            originales = {k: getattr(candidato, k) for k in simples}
            for k, v in simples.items():
                setattr(candidato, k, v)
        else:
            candidato = modelo(**simples)
            originales = None
        extra = self.context.get('datos_extra') or {}
        for k, v in extra.items():
            setattr(candidato, k, v)
        try:
            candidato.full_clean(exclude=self._excluir_de_validacion(candidato))
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        finally:
            if originales is not None:
                for k, v in originales.items():
                    setattr(candidato, k, v)
        return datos

    def _excluir_de_validacion(self, candidato):
        # Las únicas que no se validan acá: las que el serializer no maneja
        # (auditoría) y las relaciones que todavía no tienen valor porque las
        # completa la API (ej. la empresa de un registro nuevo).
        excluir = []
        for campo in candidato._meta.concrete_fields:
            if not campo.editable:
                excluir.append(campo.name)
            elif campo.is_relation and getattr(candidato, campo.attname) is None and campo.name not in self.fields:
                excluir.append(campo.name)
        return excluir


class ConAnidadosSerializer(RegistroSerializer):
    """Registro con filas hijas que se cargan en el mismo formulario (tramos
    de un horario, días de un calendario). Cada subclase declara
    `anidados = {'tramos': 'horario'}` (campo → nombre de la FK al padre) y
    el serializer de las filas como campo `many=True`. Al guardar, las filas
    se reemplazan todas, en la misma transacción que el padre; cada fila se
    valida con su `full_clean()` y el conjunto con `validar_anidados()`."""

    anidados = {}

    def validar_anidados(self, nombre, instancias):
        """Para validar el conjunto (ej. tramos superpuestos). Lanza ValidationError de Django."""

    def validate(self, datos):
        filas = {nombre: datos.pop(nombre) for nombre in self.anidados if nombre in datos}
        datos = super().validate(datos)
        for nombre, lista in filas.items():
            modelo_hijo = self.fields[nombre].child.Meta.model
            fk = self.anidados[nombre]
            instancias = [modelo_hijo(**fila) for fila in lista]
            errores = []
            for instancia in instancias:
                try:
                    instancia.full_clean(exclude=[fk])
                    errores.append({})
                except ValidationErrorDjango as e:
                    errores.append(e.message_dict if hasattr(e, 'message_dict') else {'non_field_errors': e.messages})
            if any(errores):
                raise ValidationError({nombre: errores})
            try:
                self.validar_anidados(nombre, instancias)
            except ValidationErrorDjango as e:
                raise ValidationError({nombre: e.messages})
        datos.update(filas)
        return datos

    def _guardar_anidados(self, padre, filas):
        usuario = getattr(self.context.get('request'), 'user', None)
        for nombre, lista in filas.items():
            modelo_hijo = self.fields[nombre].child.Meta.model
            fk = self.anidados[nombre]
            getattr(padre, nombre).all().delete()
            # Las filas precargadas (prefetch) quedaron viejas: se olvidan.
            getattr(padre, '_prefetched_objects_cache', {}).pop(nombre, None)
            extra = {}
            if any(c.name == 'creado_por' for c in modelo_hijo._meta.concrete_fields) and usuario is not None:
                extra = {'creado_por': usuario, 'modificado_por': usuario}
            modelo_hijo.objects.bulk_create([modelo_hijo(**{fk: padre}, **fila, **extra) for fila in lista])

    def create(self, datos):
        filas = {nombre: datos.pop(nombre) for nombre in self.anidados if nombre in datos}
        with transaction.atomic():
            padre = super().create(datos)
            self._guardar_anidados(padre, filas)
        return padre

    def update(self, instancia, datos):
        filas = {nombre: datos.pop(nombre) for nombre in self.anidados if nombre in datos}
        with transaction.atomic():
            padre = super().update(instancia, datos)
            self._guardar_anidados(padre, filas)
        return padre


class RegistroViewSet(viewsets.ModelViewSet):
    """ViewSet base. Cada subclase define `serializer_class` y, si aplica:

    - `campo_fecha`: habilita `?desde=AAAA-MM-DD&hasta=AAAA-MM-DD`.
    - `filtros_exactos`: campos filtrables por valor exacto (ej. `?departamento=3`).
    - `search_fields` / `ordering_fields`: búsqueda (`?buscar=`) y orden (`?orden=`).
    - `relaciones_extra`: relaciones de segundo nivel que usa el texto legible.
    - `permite_borrar`: False = la API no borra (bajas lógicas, legajos).
    - `permisos_acciones`: permiso de Django de cada acción propia.

    Toda alta, modificación y borrado queda en la auditoría con los valores
    anteriores y nuevos, en la misma transacción que el cambio."""

    campo_fecha = None
    filtros_exactos = ()
    relaciones_extra = ()
    ordering_fields = '__all__'
    permite_borrar = True

    @property
    def modelo(self):
        return self.serializer_class.Meta.model

    def get_queryset(self):
        relaciones = [c.name for c in self.modelo._meta.concrete_fields if c.is_relation]
        qs = alcance.filtrar(
            self.modelo.objects.select_related(*relaciones, *self.relaciones_extra).all(),
            self.request.user,
        )
        params = self.request.query_params

        if self.campo_fecha:
            desde = _fecha_o_nada(params.get('desde'))
            hasta = _fecha_o_nada(params.get('hasta'))
            if desde:
                qs = qs.filter(**{f'{self.campo_fecha}__gte': desde})
            if hasta:
                qs = qs.filter(**{f'{self.campo_fecha}__lte': hasta})

        # ?sucursal=<id> en cualquier listado de un modelo con sucursal.
        ruta_sucursal = getattr(self.modelo, 'ruta_sucursal', None)
        sucursal = params.get('sucursal')
        if sucursal and sucursal.isdigit() and ruta_sucursal is not None:
            qs = qs.filter(**({'pk': sucursal} if ruta_sucursal == '' else {ruta_sucursal: sucursal}))

        for campo in self.filtros_exactos:
            valor = params.get(campo)
            if valor not in (None, ''):
                # Django solo entiende 'True'/'False' para booleanos; desde
                # JavaScript llega 'true'/'false'.
                valor = {'true': True, 'false': False}.get(valor.lower(), valor)
                qs = qs.filter(**{campo: valor})
        return qs

    def datos_extra_al_crear(self, serializer):
        extra = {'creado_por': self.request.user, 'modificado_por': self.request.user}
        if any(c.name == 'empresa' for c in self.modelo._meta.concrete_fields):
            try:
                extra['empresa'] = alcance.empresa_para_crear(
                    self.request.user, serializer.validated_data.get('empresa'),
                )
            except ValidationErrorDjango as e:
                raise a_error_drf(e)
        return extra

    def get_serializer_context(self):
        contexto = super().get_serializer_context()
        # La validación del modelo (RegistroSerializer.validate) tiene que ver
        # la empresa que va a tener el registro nuevo.
        if getattr(self, 'action', None) == 'create' and self.request.user.is_authenticated \
                and not alcance.es_plataforma(self.request.user):
            empresa = alcance.empresa_de(self.request.user)
            if empresa is not None and any(c.name == 'empresa' for c in self.modelo._meta.concrete_fields):
                contexto['datos_extra'] = {'empresa': empresa}
        return contexto

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                objeto = serializer.save(**self.datos_extra_al_crear(serializer))
                auditoria.registrar(self.request.user, EventoAuditoria.ALTA, objeto,
                                    despues=auditoria.instantanea(objeto), request=self.request)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)

    def perform_update(self, serializer):
        antes = auditoria.instantanea(serializer.instance)
        try:
            with transaction.atomic():
                objeto = serializer.save(modificado_por=self.request.user)
                anteriores, nuevos = auditoria.diferencias(antes, auditoria.instantanea(objeto))
                if nuevos:
                    auditoria.registrar(self.request.user, EventoAuditoria.MODIFICACION, objeto,
                                        antes=anteriores, despues=nuevos, request=self.request)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)

    def destroy(self, request, *args, **kwargs):
        if not self.permite_borrar:
            return Response({'detail': 'Estos registros no se borran: se dan de baja o se desactivan.'},
                            status=status.HTTP_405_METHOD_NOT_ALLOWED)
        objeto = self.get_object()
        antes = auditoria.instantanea(objeto)
        # Las relaciones usan PROTECT: no se puede borrar, por ejemplo, un
        # departamento que ya tiene empleados. Sin esto sería un error 500.
        try:
            with transaction.atomic():
                auditoria.registrar(request.user, EventoAuditoria.BORRADO, objeto, antes=antes, request=request)
                objeto.delete()
        except ProtectedError:
            return Response(
                {'detail': 'No se puede borrar: hay otros registros que dependen de este. Desactivalo en su lugar.'},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CatalogoViewSet(RegistroViewSet):
    """Para modelos `CatalogoEmpresa`: la empresa ve los ítems globales y los
    suyos, pero solo crea, modifica o borra los suyos. La plataforma crea
    ítems globales dejando la empresa vacía."""

    def datos_extra_al_crear(self, serializer):
        if alcance.es_plataforma(self.request.user):
            return {'creado_por': self.request.user, 'modificado_por': self.request.user,
                    'empresa': serializer.validated_data.get('empresa')}
        return super().datos_extra_al_crear(serializer)

    def _solo_propios(self, objeto):
        if objeto.empresa_id is None and not alcance.es_plataforma(self.request.user):
            raise PermissionDenied('Es un ítem global: lo administra la plataforma. Creá uno propio si necesitás otro.')

    def perform_update(self, serializer):
        self._solo_propios(serializer.instance)
        super().perform_update(serializer)

    def destroy(self, request, *args, **kwargs):
        self._solo_propios(self.get_object())
        return super().destroy(request, *args, **kwargs)


def _fecha_o_nada(valor):
    # Una fecha mal escrita en la URL se ignora en vez de romper con un
    # error 500 (Django valida el formato recién al armar la consulta).
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None
