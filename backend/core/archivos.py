"""Archivos privados del legajo (contratos firmados, certificados...).

Se guardan en `PRIVADO_ROOT` (fuera de /media/, que es público) con un
nombre aleatorio, y solo se entregan por la API a quien puede ver el
registro (`servir()`). Al subirlos se valida el contenido real (los primeros
bytes), no solo la extensión o el tipo que dice el navegador: un .exe
renombrado a .pdf se rechaza."""
import hashlib
import mimetypes
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse
from django.utils.http import content_disposition_header

TAMANO_MAXIMO = 10 * 1024 * 1024

# Firma (primeros bytes) → tipo de archivo aceptado.
FIRMAS = [
    (b'%PDF-', 'application/pdf', '.pdf'),
    (b'\xff\xd8\xff', 'image/jpeg', '.jpg'),
    (b'\x89PNG\r\n\x1a\n', 'image/png', '.png'),
]


def almacenamiento_privado():
    # Función (no instancia fija): así toma PRIVADO_ROOT en el momento, y las
    # pruebas lo pueden cambiar.
    return FileSystemStorage(location=settings.PRIVADO_ROOT, base_url=None)


def ruta_aleatoria(instancia, nombre_original):
    """documentos/AAAA/MM/<uuid>.<ext>: el nombre real no queda en el disco."""
    from django.utils import timezone
    extension = Path(nombre_original).suffix.lower()[:10]
    hoy = timezone.localdate()
    return f'documentos/{hoy:%Y/%m}/{uuid.uuid4().hex}{extension}'


def ruta_foto(instancia, nombre_original):
    """fotos/<uuid>.jpg: el nombre real no queda en el disco."""
    return f'fotos/{uuid.uuid4().hex}.jpg'


TAMANO_MAXIMO_FOTO = 5 * 1024 * 1024
LADO_MAXIMO_FOTO = 600


def preparar_foto(archivo):
    """Valida que sea una imagen real (JPG, PNG o WEBP de hasta 5 MB), la
    endereza según su EXIF, la achica a 600 px como máximo y la devuelve como
    JPEG (ContentFile). Así la foto pesa poco y no lleva datos EXIF (ubicación…)."""
    import io
    from django.core.files.base import ContentFile
    from PIL import Image, ImageOps, UnidentifiedImageError
    if archivo.size > TAMANO_MAXIMO_FOTO:
        raise ValidationError('La foto no puede pasar de 5 MB.')
    try:
        imagen = Image.open(archivo)
        imagen.verify()
        archivo.seek(0)
        imagen = Image.open(archivo)
    except (UnidentifiedImageError, OSError):
        raise ValidationError('El archivo no es una imagen válida.')
    if imagen.format not in ('JPEG', 'PNG', 'WEBP'):
        raise ValidationError('Usá una foto JPG, PNG o WEBP.')
    imagen = ImageOps.exif_transpose(imagen).convert('RGB')
    imagen.thumbnail((LADO_MAXIMO_FOTO, LADO_MAXIMO_FOTO))
    salida = io.BytesIO()
    imagen.save(salida, 'JPEG', quality=85)
    return ContentFile(salida.getvalue(), name='foto.jpg')


def validar_archivo(archivo):
    """Devuelve (tipo_mime, sha256). Rechaza tamaño excesivo y tipos no admitidos."""
    if archivo.size > TAMANO_MAXIMO:
        raise ValidationError('El archivo no puede pasar de 10 MB.')
    archivo.seek(0)
    inicio = archivo.read(16)
    archivo.seek(0)
    for firma, tipo, _ in FIRMAS:
        if inicio.startswith(firma):
            break
    else:
        if inicio[:4] == b'RIFF' and inicio[8:12] == b'WEBP':
            tipo = 'image/webp'
        else:
            raise ValidationError('Solo se aceptan PDF, JPG, PNG o WEBP.')
    resumen = hashlib.sha256()
    for parte in archivo.chunks():
        resumen.update(parte)
    archivo.seek(0)
    return tipo, resumen.hexdigest()


def servir(campo_archivo, nombre_descarga, tipo_mime=None):
    """Respuesta de descarga de un archivo privado."""
    respuesta = FileResponse(campo_archivo.open('rb'),
                             content_type=tipo_mime or mimetypes.guess_type(nombre_descarga)[0] or 'application/octet-stream')
    respuesta['Content-Disposition'] = content_disposition_header(True, nombre_descarga)
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta
