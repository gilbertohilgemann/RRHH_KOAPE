"""Importación de marcaciones desde CSV (fase 5; §6 y §6 bis C).

1. `vista_previa()`: lee el archivo con el separador y la codificación
   elegidos y devuelve las primeras filas tal cual, para armar el perfil.
2. `crear_lote()`: guarda el archivo y valida cada fila contra el perfil, en
   revisión (nunca directo a marcas). Cada fila queda válida, rechazada (con
   el motivo) o duplicada (dentro del archivo o contra lo ya importado).
3. `confirmar()`: crea las marcas de las filas válidas en una sola
   transacción. Reimportar el mismo archivo no duplica nada.
4. `revertir()`: anula las marcas del lote (no las borra), con motivo.
5. `exportar_errores()`: las filas no importadas en CSV o Excel, protegidas
   contra inyección de fórmulas (=, +, -, @).

Nunca se adivina: un código desconocido, una fecha que no respeta el formato
o un empleado fuera de su período laboral se rechazan con el motivo."""
import csv
import hashlib
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from asistencia.models import ConfiguracionMarcacion, FilaImportacion, LoteImportacion, MapeoEmpleadoReloj, Marcacion
from empleados.models import Empleado

MAX_BYTES = getattr(settings, 'IMPORTACION_MAX_BYTES', 5 * 1024 * 1024)
MAX_FILAS = getattr(settings, 'IMPORTACION_MAX_FILAS', 50_000)
TOLERANCIA_FUTURO = timedelta(minutes=5)


# ------------------------------------------------------------------ lectura

def _contenido(archivo):
    if archivo.size > MAX_BYTES:
        raise ValidationError(f'El archivo pasa de {MAX_BYTES // (1024 * 1024)} MB.')
    archivo.seek(0)
    datos = archivo.read()
    archivo.seek(0)
    return datos


def leer_csv(datos, separador, codificacion, tiene_encabezado):
    """(encabezado o None, [(número de fila del archivo, [columnas])]). Las filas vacías se saltean."""
    if b'\x00' in datos[:4096]:
        raise ValidationError('No parece un archivo de texto CSV (¿es un Excel u otro archivo?).')
    try:
        texto = datos.decode(codificacion)
    except (UnicodeDecodeError, LookupError):
        otra = 'Latin-1 o Windows-1252' if codificacion == 'utf-8' else 'UTF-8'
        raise ValidationError(f'No se pudo leer el archivo como {codificacion.upper()}. Probá con {otra}.')
    texto = texto.lstrip('﻿')
    lector = csv.reader(io.StringIO(texto, newline=''), delimiter=separador)
    encabezado, filas = None, []
    try:
        for numero, columnas in enumerate(lector, start=1):
            if not any(c.strip() for c in columnas):
                continue
            columnas = [c.strip() for c in columnas]
            if tiene_encabezado and encabezado is None:
                encabezado = columnas
                continue
            filas.append((numero, columnas))
            if len(filas) > MAX_FILAS:
                raise ValidationError(f'El archivo tiene más de {MAX_FILAS} filas: dividilo en partes.')
    except csv.Error as error:
        raise ValidationError(f'El archivo no es un CSV válido: {error}.')
    return encabezado, filas


def vista_previa(archivo, separador, codificacion, tiene_encabezado, cantidad=20):
    encabezado, filas = leer_csv(_contenido(archivo), separador, codificacion, tiene_encabezado)
    ancho = max([len(encabezado or [])] + [len(c) for _, c in filas[:cantidad]] + [0])
    return {
        'encabezado': encabezado or [f'Columna {i}' for i in range(1, ancho + 1)],
        'tiene_encabezado': bool(encabezado),
        'filas': [{'fila': n, 'columnas': c} for n, c in filas[:cantidad]],
        'total_filas': len(filas),
    }


def _indice(referencia, encabezado, nombre_campo):
    """Columna por su nombre en el encabezado o por su número (1, 2…)."""
    referencia = (referencia or '').strip()
    if not referencia:
        return None
    if referencia.isdigit():
        return int(referencia) - 1
    if encabezado:
        normalizado = [c.strip().lower() for c in encabezado]
        if referencia.lower() in normalizado:
            return normalizado.index(referencia.lower())
    raise ValidationError(f'El archivo no tiene la columna "{referencia}" ({nombre_campo}). '
                          f'Revisá el perfil o usá el número de columna.')


# ------------------------------------------------------------------ lote

def _huella(empresa_id, empleado_id, fecha_hora, tipo):
    return hashlib.sha256(f'csv|{empresa_id}|{empleado_id}|{fecha_hora.astimezone(ZoneInfo("UTC")).isoformat(timespec="seconds")}|{tipo}'.encode()).hexdigest()


class _Buscador:
    """Encuentra el empleado de una fila según cómo lo identifica el perfil."""

    def __init__(self, perfil, reloj, empresa):
        self.perfil = perfil
        if perfil.identificador == 'codigo_reloj':
            self.mapeos = {}
            for mapeo in MapeoEmpleadoReloj.objects.select_related('empleado').filter(reloj=reloj):
                self.mapeos.setdefault(mapeo.codigo_en_reloj.lower(), []).append(mapeo)
        else:
            campo = 'codigo' if perfil.identificador == 'codigo_empleado' else 'numero_documento'
            self.empleados = {getattr(e, campo).strip().lower(): e for e in Empleado.objects.filter(empresa=empresa)}

    def buscar(self, codigo, fecha):
        codigo = codigo.strip().lower()
        if self.perfil.identificador != 'codigo_reloj':
            return self.empleados.get(codigo)
        for mapeo in self.mapeos.get(codigo, []):
            if (mapeo.vigente_desde is None or mapeo.vigente_desde <= fecha) and \
                    (mapeo.vigente_hasta is None or fecha <= mapeo.vigente_hasta):
                return mapeo.empleado
        return None


def crear_lote(usuario, empresa, archivo, perfil, reloj=None, desde=None, hasta=None, notas=''):
    """Guarda el archivo y valida todas sus filas (en revisión). Lanza ValidationError si el archivo entero no sirve."""
    if not ConfiguracionMarcacion.de(empresa).permite_csv:
        raise ValidationError('Tu empresa no tiene habilitada la importación de archivos CSV (Configuración del marcador).')
    if perfil.empresa_id != empresa.pk or not perfil.activo:
        raise ValidationError('Elegí un perfil de importación activo de tu empresa.')
    if reloj is not None and reloj.empresa_id != empresa.pk:
        raise ValidationError('El reloj no es de tu empresa.')
    if perfil.identificador == 'codigo_reloj' and reloj is None:
        raise ValidationError('Este perfil usa los códigos del reloj: elegí de qué reloj es el archivo.')
    if desde and hasta and hasta < desde:
        raise ValidationError('El período "hasta" no puede ser anterior a "desde".')

    datos = _contenido(archivo)
    encabezado, filas = leer_csv(datos, perfil.separador, perfil.codificacion, perfil.tiene_encabezado)
    if not filas:
        raise ValidationError('El archivo no tiene filas para importar.')
    col = {
        'empleado': _indice(perfil.columna_empleado, encabezado, 'empleado'),
        'fecha_hora': _indice(perfil.columna_fecha_hora, encabezado, 'fecha y hora'),
        'fecha': _indice(perfil.columna_fecha, encabezado, 'fecha'),
        'hora': _indice(perfil.columna_hora, encabezado, 'hora'),
        'tipo': _indice(perfil.columna_tipo, encabezado, 'entrada/salida'),
        'evento': _indice(perfil.columna_evento, encabezado, 'id de evento'),
    }
    zona = ZoneInfo(perfil.zona_horaria)
    buscador = _Buscador(perfil, reloj, empresa)
    entrada, salida = perfil.conjunto_entrada, perfil.conjunto_salida
    ahora = timezone.now()
    sha256 = hashlib.sha256(datos).hexdigest()

    resultados = []  # (numero, columnas, datos de la fila)
    for numero, columnas in filas:
        fila = {'codigo_en_archivo': '', 'empleado': None, 'fecha_hora': None, 'tipo': '', 'id_evento': '',
                'huella': '', 'estado': FilaImportacion.VALIDA, 'mensaje': ''}
        resultados.append((numero, columnas, fila))

        def valor(clave):
            indice = col[clave]
            return columnas[indice].strip() if indice is not None and indice < len(columnas) else None

        necesarias = [i for i in col.values() if i is not None]
        if necesarias and max(necesarias) >= len(columnas):
            fila.update(estado=FilaImportacion.RECHAZADA, mensaje=f'Faltan columnas (tiene {len(columnas)}).')
            continue
        fila['codigo_en_archivo'] = (valor('empleado') or '')[:80]
        fila['id_evento'] = (valor('evento') or '')[:120]
        try:
            if col['fecha_hora'] is not None:
                momento = datetime.strptime(valor('fecha_hora'), perfil.formato_fecha_hora)
            else:
                dia = datetime.strptime(valor('fecha'), perfil.formato_fecha).date()
                hora = datetime.strptime(valor('hora'), perfil.formato_hora).time()
                momento = datetime.combine(dia, hora)
        except (ValueError, TypeError):
            texto = valor('fecha_hora') if col['fecha_hora'] is not None else f'{valor("fecha")} {valor("hora")}'
            fila.update(estado=FilaImportacion.RECHAZADA, mensaje=f'Fecha u hora "{texto}" no respeta el formato del perfil.')
            continue
        momento = momento.replace(tzinfo=zona)
        fila['fecha_hora'] = momento
        fecha = momento.date()
        if not fila['codigo_en_archivo']:
            fila.update(estado=FilaImportacion.RECHAZADA, mensaje='Sin código de empleado.')
            continue
        if momento > ahora + TOLERANCIA_FUTURO:
            fila.update(estado=FilaImportacion.RECHAZADA, mensaje='La fecha y hora es futura.')
            continue
        if (desde and fecha < desde) or (hasta and fecha > hasta):
            fila.update(estado=FilaImportacion.RECHAZADA, mensaje='Fuera del período elegido para la importación.')
            continue
        empleado = buscador.buscar(fila['codigo_en_archivo'], fecha)
        if empleado is None:
            donde = 'en los códigos del reloj' if perfil.identificador == 'codigo_reloj' else 'entre los empleados'
            fila.update(estado=FilaImportacion.RECHAZADA, mensaje=f'Código "{fila["codigo_en_archivo"]}" desconocido {donde}.')
            continue
        fila['empleado'] = empleado
        if fecha < empleado.fecha_ingreso or (empleado.fecha_egreso and fecha > empleado.fecha_egreso):
            fila.update(estado=FilaImportacion.RECHAZADA, mensaje=f'{empleado.nombre_completo} no trabajaba en la empresa ese día.')
            continue
        if col['tipo'] is not None:
            crudo = (valor('tipo') or '').lower()
            if crudo in entrada:
                fila['tipo'] = Marcacion.ENTRADA
            elif crudo in salida:
                fila['tipo'] = Marcacion.SALIDA
            else:
                fila.update(estado=FilaImportacion.RECHAZADA, mensaje=f'Entrada/salida "{valor("tipo")}" no reconocida por el perfil.')
                continue
        else:
            fila['tipo'] = Marcacion.DESCONOCIDO
        fila['huella'] = _huella(empresa.pk, empleado.pk, momento, fila['tipo'])

    # Duplicados: dentro del archivo y contra lo ya importado (por huella o por id de evento del reloj).
    validas = [f for _, _, f in resultados if f['estado'] == FilaImportacion.VALIDA]
    existentes = set(Marcacion.objects.filter(empresa=empresa, anulada=False,
                                              huella_deduplicacion__in=[f['huella'] for f in validas])
                     .values_list('huella_deduplicacion', flat=True))
    eventos_existentes = set()
    if reloj is not None:
        eventos_existentes = set(Marcacion.objects.filter(reloj=reloj, anulada=False,
                                                          id_evento_externo__in=[f['id_evento'] for f in validas if f['id_evento']])
                                 .values_list('id_evento_externo', flat=True))
    vistas, eventos_vistos = {}, {}
    for numero, _, fila in resultados:
        if fila['estado'] != FilaImportacion.VALIDA:
            continue
        if fila['huella'] in vistas:
            fila.update(estado=FilaImportacion.DUPLICADA, mensaje=f'Repetida en el archivo (igual a la fila {vistas[fila["huella"]]}).')
        elif fila['id_evento'] and fila['id_evento'] in eventos_vistos:
            fila.update(estado=FilaImportacion.DUPLICADA,
                        mensaje=f'Id de evento {fila["id_evento"]} repetido en el archivo (fila {eventos_vistos[fila["id_evento"]]}).')
        elif fila['huella'] in existentes or (fila['id_evento'] and fila['id_evento'] in eventos_existentes):
            fila.update(estado=FilaImportacion.DUPLICADA, mensaje='Ya importada antes (no se duplica).')
        else:
            vistas[fila['huella']] = numero
            if fila['id_evento']:
                eventos_vistos[fila['id_evento']] = numero

    anterior = LoteImportacion.objects.filter(empresa=empresa, sha256=sha256, estado=LoteImportacion.CONFIRMADO).first()
    with transaction.atomic():
        lote = LoteImportacion(
            empresa=empresa, reloj=reloj, perfil=perfil, perfil_version=perfil.version, modo=perfil.modo,
            nombre_archivo=archivo.name[:255], sha256=sha256, tamano=len(datos), periodo_desde=desde,
            periodo_hasta=hasta, notas=notas, creado_por=usuario, modificado_por=usuario,
            aviso=f'Este mismo archivo ya se importó en el lote {anterior.pk}: sus filas figuran como duplicadas.' if anterior else '',
        )
        lote.archivo.save('importacion.csv', archivo, save=False)
        _contar(lote, [f for _, _, f in resultados])
        lote.save()
        FilaImportacion.objects.bulk_create([
            FilaImportacion(lote=lote, numero_fila=numero, datos=columnas[:50],
                            **{k: v for k, v in fila.items()})
            for numero, columnas, fila in resultados
        ])
    return lote


def _contar(lote, filas):
    lote.total_filas = len(filas)
    lote.aceptadas = sum(1 for f in filas if f['estado'] == FilaImportacion.VALIDA)
    lote.rechazadas = sum(1 for f in filas if f['estado'] == FilaImportacion.RECHAZADA)
    lote.duplicadas = sum(1 for f in filas if f['estado'] == FilaImportacion.DUPLICADA)


def confirmar(lote, usuario):
    """Crea las marcas de las filas válidas, todo o nada."""
    with transaction.atomic():
        lote = LoteImportacion.objects.select_for_update().get(pk=lote.pk)
        if lote.estado != LoteImportacion.VALIDADO:
            raise ValidationError('Solo se confirma un lote validado y sin confirmar.')
        if not ConfiguracionMarcacion.de(lote.empresa).permite_csv:
            raise ValidationError('La importación CSV está deshabilitada.')
        validas = list(lote.filas.filter(estado=FilaImportacion.VALIDA).select_related('empleado'))
        # Por si mientras tanto se importó otro archivo con las mismas marcas.
        ya = set(Marcacion.objects.filter(empresa=lote.empresa, anulada=False,
                                          huella_deduplicacion__in=[f.huella for f in validas])
                 .values_list('huella_deduplicacion', flat=True))
        creadas = 0
        for fila in validas:
            if fila.huella in ya:
                fila.estado, fila.mensaje = FilaImportacion.DUPLICADA, 'Importada por otro lote mientras tanto.'
                fila.save(update_fields=['estado', 'mensaje'])
                continue
            fila.marcacion = Marcacion.objects.create(
                empresa_id=lote.empresa_id, empleado=fila.empleado, fecha_hora=fila.fecha_hora, tipo=fila.tipo,
                metodo=Marcacion.CSV, nivel_verificacion='archivo_importado', reloj=lote.reloj, lote_importacion=lote,
                id_evento_externo=fila.id_evento, huella_deduplicacion=fila.huella,
                referencia=f'Lote {lote.pk}, fila {fila.numero_fila}', creado_por=usuario, modificado_por=usuario,
            )
            fila.save(update_fields=['marcacion'])
            creadas += 1
        _recalcular_asistencia(lote.marcaciones.filter(anulada=False))
        lote.estado = LoteImportacion.CONFIRMADO
        lote.confirmado_en = timezone.now()
        lote.confirmado_por = usuario
        lote.modificado_por = usuario
        _contar(lote, list(lote.filas.values('estado')))
        lote.save()
    return creadas


def _recalcular_asistencia(marcas):
    """Recalcula (al confirmarse la transacción) los días de asistencia que tocan estas marcas."""
    from asistencia.motor import recalcular_despues
    por_empleado = {}
    for marca in marcas.select_related('empleado__empresa'):
        por_empleado.setdefault(marca.empleado_id, (marca.empleado, []))[1].append(marca.fecha_hora)
    for empleado, momentos in por_empleado.values():
        recalcular_despues(empleado, momentos)


def periodo_cerrado(empresa, fecha):
    """¿La fecha cae en un período de nómina cerrado? (nomina/liquidar.py)"""
    from nomina.liquidar import periodo_cerrado as cerrado
    return cerrado(empresa, fecha)


def revertir(lote, usuario, motivo):
    """Anula (sin borrar) las marcas de un lote confirmado."""
    with transaction.atomic():
        lote = LoteImportacion.objects.select_for_update().get(pk=lote.pk)
        if lote.estado != LoteImportacion.CONFIRMADO:
            raise ValidationError('Solo se revierte un lote confirmado.')
        marcas = lote.marcaciones.filter(anulada=False)
        fechas = {timezone.localtime(m.fecha_hora).date() for m in marcas}
        if any(periodo_cerrado(lote.empresa, f) for f in fechas):
            raise ValidationError('Afecta una nómina cerrada: hay que hacer una corrección auditada, no revertir.')
        _recalcular_asistencia(marcas)
        cantidad = marcas.update(anulada=True, anulada_en=timezone.now(), motivo_anulacion=f'Reversión del lote {lote.pk}: {motivo}'[:250])
        lote.estado = LoteImportacion.REVERTIDO
        lote.motivo_reversion = motivo[:250]
        lote.modificado_por = usuario
        lote.save(update_fields=['estado', 'motivo_reversion', 'modificado_por', 'modificado'])
    return cantidad


def cancelar(lote, usuario):
    if lote.estado != LoteImportacion.VALIDADO:
        raise ValidationError('Solo se cancela un lote sin confirmar.')
    lote.estado = LoteImportacion.CANCELADO
    lote.modificado_por = usuario
    lote.save(update_fields=['estado', 'modificado_por', 'modificado'])


# ------------------------------------------------------------------ errores

def _seguro(valor):
    """Protección contra inyección de fórmulas al abrir el archivo en Excel."""
    texto = '' if valor is None else str(valor)
    return "'" + texto if texto[:1] in ('=', '+', '-', '@', '\t', '\r') else texto


def exportar_errores(lote, formato='csv'):
    """(contenido, tipo, extensión) con las filas que no se importaron."""
    encabezado = ['Fila', 'Estado', 'Motivo', 'Empleado en el archivo', 'Datos originales']
    filas = [[f.numero_fila, f.get_estado_display(), f.mensaje, f.codigo_en_archivo, ' | '.join(map(str, f.datos))]
             for f in lote.filas.exclude(estado=FilaImportacion.VALIDA).order_by('numero_fila')]
    if formato == 'xlsx':
        from openpyxl import Workbook
        libro = Workbook()
        hoja = libro.active
        hoja.title = 'Filas no importadas'
        hoja.append(encabezado)
        for fila in filas:
            hoja.append([fila[0]] + [_seguro(v) for v in fila[1:]])
        salida = io.BytesIO()
        libro.save(salida)
        return salida.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx'
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=';')
    escritor.writerow(encabezado)
    for fila in filas:
        escritor.writerow([fila[0]] + [_seguro(v) for v in fila[1:]])
    return ('﻿' + salida.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8', 'csv'

