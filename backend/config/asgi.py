"""
Punto de entrada ASGI (no se usa hoy: el servidor corre con gunicorn y WSGI).

Expone la aplicación en la variable ``application``.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_asgi_application()
