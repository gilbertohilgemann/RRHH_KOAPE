"""Cifrado de datos sensibles en la base (números de cuenta bancaria).

Fernet (AES-128-CBC + HMAC): el valor guardado no se puede leer sin la
`CLAVE_CIFRADO` del .env, aunque alguien se lleve la base de datos. Nunca
se descifra para listados ni para la bitácora: solo cuando un usuario con
permiso lo pide expresamente (y eso queda en la auditoría)."""
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    return Fernet(settings.CLAVE_CIFRADO.encode())


def cifrar(texto):
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(token):
    """El texto original, o None si no se puede descifrar (clave cambiada)."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def enmascarar(ultimos):
    """'1234' → '•••• 1234'."""
    return f'•••• {ultimos}' if ultimos else ''
