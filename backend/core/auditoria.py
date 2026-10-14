"""Escritura de la bitácora de auditoría (core.EventoAuditoria).

La API genérica (core/api/base.py) y el admin (core/admin_base.py) registran
solos cada alta, modificación y borrado con los valores anteriores y nuevos;
las acciones propias (baja de un empleado, cambio de perfiles, ingreso al
sistema...) llaman a `registrar()` explícitamente."""
import json
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import FileField, ForeignKey, ManyToManyField

# Campos que nunca se copian a la bitácora (secretos o datos que se protegen).
CAMPOS_EXCLUIDOS = {'password', 'creado', 'modificado', 'creado_por', 'modificado_por'}


def instantanea(objeto):
    """Los valores actuales de un registro como diccionario apto para JSON
    (relaciones por id, fechas en ISO). Los modelos con datos sensibles
    pueden declarar `campos_sin_auditar` para dejarlos afuera."""
    if objeto is None:
        return None
    excluidos = CAMPOS_EXCLUIDOS | set(getattr(objeto, 'campos_sin_auditar', ()))
    datos = {}
    for campo in objeto._meta.concrete_fields:
        if campo.name in excluidos:
            continue
        if isinstance(campo, ForeignKey):
            datos[campo.name] = getattr(objeto, campo.attname)
        elif isinstance(campo, FileField):
            archivo = getattr(objeto, campo.name)
            datos[campo.name] = archivo.name if archivo else ''
        else:
            datos[campo.name] = getattr(objeto, campo.name)
    if objeto.pk:
        for campo in objeto._meta.many_to_many:
            if campo.name not in excluidos and isinstance(campo, ManyToManyField):
                datos[campo.name] = sorted(getattr(objeto, campo.name).values_list('pk', flat=True))
        # Filas hijas que se editan con el registro (ej. los tramos de un horario).
        extra = getattr(objeto, 'datos_auditoria_extra', None)
        if callable(extra):
            datos.update(extra())
    return json.loads(json.dumps(datos, cls=DjangoJSONEncoder, default=_a_texto))


def _a_texto(valor):
    return str(valor) if isinstance(valor, Decimal) else repr(valor)


def diferencias(antes, despues):
    """Solo los campos que cambiaron: ({campo: anterior}, {campo: nuevo})."""
    antes, despues = antes or {}, despues or {}
    cambiados = [c for c in sorted(set(antes) | set(despues)) if antes.get(c) != despues.get(c)]
    return {c: antes.get(c) for c in cambiados}, {c: despues.get(c) for c in cambiados}


def _empresa_de(objeto):
    """La empresa de un registro siguiendo su `ruta_empresa`."""
    ruta = getattr(objeto, 'ruta_empresa', None)
    if objeto is None or ruta is None:
        return None
    if ruta == '':
        return objeto
    actual = objeto
    for parte in ruta.split('__'):
        actual = getattr(actual, parte, None)
        if actual is None:
            return None
    return actual


def ip_de(request):
    if request is None:
        return None
    reenviada = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (reenviada.split(',')[0].strip() if reenviada else request.META.get('REMOTE_ADDR')) or None


def registrar(usuario, accion, objeto=None, *, empresa=None, descripcion='', antes=None, despues=None, request=None,
              modelo=None):
    """Escribe un evento. `antes`/`despues`: diccionarios (ver `instantanea`)."""
    from core.models import EventoAuditoria
    usuario_valido = usuario if usuario is not None and getattr(usuario, 'is_authenticated', False) else None
    return EventoAuditoria.objects.create(
        usuario=usuario_valido,
        nombre_usuario=usuario_valido.get_username() if usuario_valido else '',
        empresa=empresa if empresa is not None else _empresa_de(objeto),
        accion=accion,
        modelo=modelo or (objeto._meta.label if objeto is not None else ''),
        objeto_id=str(objeto.pk) if objeto is not None and objeto.pk is not None else '',
        objeto_texto=str(objeto)[:250] if objeto is not None else '',
        descripcion=descripcion,
        datos_anteriores=antes,
        datos_nuevos=despues,
        ip=ip_de(request),
    )
