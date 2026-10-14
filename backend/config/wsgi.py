"""
Punto de entrada WSGI (lo usa gunicorn en el servidor).

Expone la aplicación en la variable ``application``.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
