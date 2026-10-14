"""Almacenamiento de estáticos para producción."""

from whitenoise.storage import CompressedManifestStaticFilesStorage


class EstaticosProduccion(CompressedManifestStaticFilesStorage):
    """Como el de whitenoise (comprimidos y con hash en el nombre), pero sin
    ser estricto: si una plantilla pide algo que no está en el manifiesto,
    se usa el nombre sin hash en vez de dar error 500.

    Hace falta por Jazzmin: su plantilla del admin pide
    `{% static 'vendor/bootswatch' %}`, que es una CARPETA (arma la ruta del
    tema desde JavaScript) y nunca figura en el manifiesto. Con el modo
    estricto, el admin daba 500 apenas se iniciaba sesión en producción.
    """

    manifest_strict = False
