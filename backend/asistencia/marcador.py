"""Lógica del marcador propio (§6 bis). Un solo lugar para las modalidades,
así se comportan igual: la API (asistencia/api.py) solo traduce pedidos y
respuestas.

Modalidad A, QR dinámico (decisión del cliente, 14/10/2026): la terminal
proyecta un QR que genera el servidor; el empleado lo escanea con su
celular, con su sesión iniciada. El QR cambia cada `vigencia_qr_segundos` y,
con `qr_un_solo_uso`, apenas alguien marca con él: una foto reenviada a otro
empleado ya no sirve.

Reglas comunes:
- La hora es SIEMPRE la del servidor (nunca la del celular o la terminal).
- Solo empleados activos de la empresa de la terminal.
- Antirrebote: una segunda marca del mismo empleado antes de
  `segundos_antirrebote` se rechaza como repetida.
- Entrada o salida: en modo automático, salida si la última marca fue una
  entrada dentro de `horas_maximas_turno`; si no, entrada. En modo
  explícito lo elige el empleado (QR) o la terminal (código).
- Secuencias incoherentes (dos entradas, salida sin entrada) se registran
  igual y generan una incidencia: nunca se borra ni se corrige una marca."""
import hashlib
import secrets
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from asistencia.models import (ConfiguracionMarcacion, CredencialMarcacion, IncidenciaAsistencia, IntentoMarcacion,
                               Marcacion, QRDinamico, huella)
from empleados.models import Empleado

# Segundos de tolerancia después del vencimiento: cubre al que escaneó justo
# antes del cambio y tardó un poco en enviar.
GRACIA_QR_SEGUNDOS = 10


class Rechazo(Exception):
    """Marca no registrada, con un código y un mensaje para mostrar."""

    def __init__(self, codigo, mensaje, empleado=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.empleado = empleado


# ---------------------------------------------------------------- QR dinámico

def qr_actual(terminal, id_en_pantalla=None):
    """El QR que tiene que mostrar la terminal. Devuelve (QRDinamico, token):
    el token en claro solo cuando se genera uno nuevo (la pantalla ya tiene el
    vigente si manda su id); None, None si la terminal no muestra QR."""
    configuracion = ConfiguracionMarcacion.de(terminal.empresa)
    if not (configuracion.permite_qr and terminal.acepta_qr):
        return None, None
    ahora = timezone.now()
    vigente = QRDinamico.objects.filter(terminal=terminal, estado=QRDinamico.VIGENTE,
                                        vence_en__gt=ahora).order_by('-generado_en').first()
    if vigente is not None and vigente.pk == id_en_pantalla:
        return vigente, None
    with transaction.atomic():
        QRDinamico.objects.filter(terminal=terminal, estado=QRDinamico.VIGENTE, vence_en__lte=ahora).update(
            estado=QRDinamico.VENCIDO)
        # Otra pantalla (o una recarga) con el mismo QR: se reemplaza.
        QRDinamico.objects.filter(terminal=terminal, estado=QRDinamico.VIGENTE).update(estado=QRDinamico.REEMPLAZADO)
        token = secrets.token_urlsafe(24)
        nuevo = QRDinamico.objects.create(
            empresa_id=terminal.empresa_id, terminal=terminal, token_huella=huella(token),
            vence_en=ahora + timedelta(seconds=configuracion.vigencia_qr_segundos),
        )
    return nuevo, token


def marcar_con_qr(empleado, token, tipo=None, ip=None):
    """El empleado (con su sesión) envía el QR que escaneó en la terminal."""
    # Se relee el legajo: el estado (activo o de baja) tiene que ser el de ahora.
    empleado = Empleado.objects.select_related('empresa').get(pk=empleado.pk)
    configuracion = ConfiguracionMarcacion.de(empleado.empresa)
    if not configuracion.permite_qr:
        return _rechazar(empleado.empresa_id, None, 'qr_deshabilitado',
                         'Tu empresa no tiene habilitada la marcación con QR.', empleado, ip)
    registro = QRDinamico.objects.select_related('terminal__empresa').filter(
        token_huella=huella((token or '').strip())).first()
    if registro is None:
        return _rechazar(empleado.empresa_id, None, 'qr_desconocido', 'Ese QR no es de una terminal de Koape.', empleado, ip)
    terminal = registro.terminal
    ahora = timezone.now()
    motivo = None
    if registro.empresa_id != empleado.empresa_id:
        motivo = ('qr_otra_empresa', 'Ese QR es de una terminal de otra empresa.')
    elif not terminal.activa or not terminal.acepta_qr:
        motivo = ('terminal_inactiva', 'La terminal no está habilitada para QR.')
    elif registro.estado == QRDinamico.USADO:
        motivo = ('qr_usado', 'Ese QR ya se usó: escaneá el que muestra ahora la pantalla.')
    elif registro.estado == QRDinamico.REEMPLAZADO or ahora > registro.vence_en + timedelta(seconds=GRACIA_QR_SEGUNDOS):
        motivo = ('qr_vencido', 'Ese QR ya cambió: escaneá el que muestra ahora la pantalla.')
    if motivo:
        return _rechazar(empleado.empresa_id, terminal if registro.empresa_id == empleado.empresa_id else None,
                         *motivo, empleado=empleado, ip=ip)
    try:
        with transaction.atomic():
            # Consumo atómico: de dos envíos simultáneos con un QR de un uso, uno solo lo logra.
            pendientes = QRDinamico.objects.filter(pk=registro.pk, estado__in=(QRDinamico.VIGENTE, QRDinamico.VENCIDO))
            cambios = {'usos': F('usos') + 1}
            if configuracion.qr_un_solo_uso:
                cambios['estado'] = QRDinamico.USADO
            if pendientes.update(**cambios) != 1:
                raise Rechazo('qr_usado', 'Ese QR ya se usó: escaneá el que muestra ahora la pantalla.', empleado)
            return registrar(empleado, terminal, Marcacion.QR, 'qr_autenticado', tipo,
                             qr_id=registro.pk, referencia=f'QR {registro.pk}')
    except Rechazo as rechazo:
        return _rechazar(empleado.empresa_id, terminal, rechazo.codigo, rechazo.mensaje, empleado=empleado, ip=ip)


def eventos_de_terminal(terminal, desde_id=0, minutos=2):
    """Marcas recientes hechas en la terminal (para mostrarlas en su pantalla)."""
    desde = timezone.now() - timedelta(minutes=minutos)
    return Marcacion.objects.select_related('empleado').filter(
        terminal=terminal, pk__gt=desde_id or 0, creado__gte=desde).order_by('pk')[:10]


# ---------------------------------------------------------------- código fijo

def marcar_con_codigo(terminal, codigo, tipo=None, ip=None):
    if not terminal.acepta_codigo:
        return _rechazar(terminal.empresa_id, terminal, 'terminal_sin_codigo', 'Esta terminal no acepta códigos.', ip=ip,
                         metodo=Marcacion.CODIGO_FIJO)
    if not ConfiguracionMarcacion.de(terminal.empresa).permite_codigo_fijo:
        return _rechazar(terminal.empresa_id, terminal, 'codigo_deshabilitado',
                         'La empresa no tiene habilitado el código fijo.', ip=ip, metodo=Marcacion.CODIGO_FIJO)
    codigo = (codigo or '').strip()
    credencial = CredencialMarcacion.buscar(terminal.empresa_id, codigo) if codigo.isdigit() else None
    if credencial is None:
        return _rechazar(terminal.empresa_id, terminal, 'codigo_desconocido', 'Código no válido.', ip=ip,
                         metodo=Marcacion.CODIGO_FIJO)
    try:
        with transaction.atomic():
            return registrar(credencial.empleado, terminal, Marcacion.CODIGO_FIJO, 'solo_codigo', tipo,
                             credencial_id=credencial.pk, referencia=f'Código v{credencial.version}')
    except Rechazo as rechazo:
        return _rechazar(terminal.empresa_id, terminal, rechazo.codigo, rechazo.mensaje, empleado=credencial.empleado,
                         ip=ip, metodo=Marcacion.CODIGO_FIJO)


# ---------------------------------------------------------------- registro común

def registrar(empleado, terminal, metodo, nivel, tipo=None, **extra):
    """Registra la marca (dentro de una transacción). Lanza Rechazo si no corresponde."""
    configuracion = ConfiguracionMarcacion.de(empleado.empresa)
    # Bloquea el legajo: dos marcas simultáneas del mismo empleado se ordenan.
    empleado = Empleado.objects.select_for_update().get(pk=empleado.pk)
    if empleado.empresa_id != terminal.empresa_id:
        raise Rechazo('otra_empresa', 'El empleado no es de esta empresa.')
    if empleado.estado != Empleado.ACTIVO:
        raise Rechazo('empleado_inactivo', 'El legajo no está activo.', empleado)
    ahora = timezone.now()
    ultima = Marcacion.objects.filter(empleado=empleado, anulada=False).order_by('-fecha_hora', '-id').first()
    if ultima and (ahora - ultima.fecha_hora).total_seconds() < configuracion.segundos_antirrebote:
        segundos = int((ahora - ultima.fecha_hora).total_seconds())
        raise Rechazo('repetida', f'Ya marcaste hace {segundos} segundos ({ultima.get_tipo_display().lower()}).', empleado)

    abierta = bool(ultima and ultima.tipo == Marcacion.ENTRADA
                   and ahora - ultima.fecha_hora < timedelta(hours=configuracion.horas_maximas_turno))
    if tipo not in (None, ''):
        if tipo not in (Marcacion.ENTRADA, Marcacion.SALIDA):
            raise Rechazo('tipo_invalido', 'Indicá entrada o salida.', empleado)
    elif configuracion.modo_accion == ConfiguracionMarcacion.EXPLICITA:
        raise Rechazo('falta_tipo', 'Elegí Entrada o Salida.', empleado)
    else:
        tipo = Marcacion.SALIDA if abierta else Marcacion.ENTRADA

    marcacion = Marcacion.objects.create(
        empresa_id=empleado.empresa_id, empleado=empleado, fecha_hora=ahora, tipo=tipo, metodo=metodo,
        nivel_verificacion=nivel, terminal=terminal,
        huella_deduplicacion=hashlib.sha256(f'{empleado.empresa_id}|{empleado.pk}|{ahora.isoformat()}|{tipo}|{metodo}'.encode()).hexdigest(),
        **extra,
    )
    # Secuencias incoherentes: la marca queda y se avisa a RR. HH.
    incidencia = None
    if tipo == Marcacion.ENTRADA and abierta:
        incidencia = (IncidenciaAsistencia.ENTRADA_SIN_SALIDA,
                      f'Entrada sin salida de la entrada anterior ({timezone.localtime(ultima.fecha_hora):%d/%m %H:%M}).')
    elif tipo == Marcacion.SALIDA and not abierta:
        incidencia = (IncidenciaAsistencia.SALIDA_SIN_ENTRADA, 'Salida sin una entrada previa en el turno.')
    if incidencia:
        IncidenciaAsistencia.objects.create(empresa_id=empleado.empresa_id, empleado=empleado,
                                            fecha=timezone.localdate(ahora), tipo=incidencia[0],
                                            descripcion=incidencia[1], marcacion=marcacion)
    # El día de asistencia se recalcula cuando la marca queda guardada.
    from asistencia.motor import recalcular_despues
    recalcular_despues(empleado, [ahora])
    return {'resultado': 'ok', 'marcacion': marcacion, 'incidencia': incidencia[1] if incidencia else None}


def _rechazar(empresa_id, terminal, codigo, mensaje, empleado=None, ip=None, metodo=Marcacion.QR):
    IntentoMarcacion.objects.create(empresa_id=empresa_id, terminal=terminal, metodo=metodo,
                                    empleado=empleado, codigo_rechazo=codigo, mensaje=mensaje[:250], ip=ip)
    return {'resultado': 'rechazado', 'codigo': codigo, 'mensaje': mensaje}


def terminal_bloqueada(terminal, minutos=5, maximo=10):
    """Demasiados códigos desconocidos recientes en la terminal (ej. probar al azar)."""
    desde = timezone.now() - timedelta(minutes=minutos)
    return IntentoMarcacion.objects.filter(terminal=terminal, fecha_hora__gte=desde,
                                           codigo_rechazo='codigo_desconocido').count() >= maximo
