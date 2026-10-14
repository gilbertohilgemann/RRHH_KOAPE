"""Middlewares propios del proyecto."""

from django.conf import settings
from django.http import Http404


class AdminSoloPorHost:
    """El admin de la plataforma responde solo cuando se lo pide por una de
    las direcciones de `ADMIN_HOSTS` (en el servidor: el dominio, a pedido del
    cliente, y "ip:puerto"); por cualquier otra responde 404, como si no
    existiera. Es una segunda barrera además de nginx.

    Con `ADMIN_HOSTS` vacío (desarrollo local) no restringe nada.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        permitidos = settings.ADMIN_HOSTS
        ruta = request.path_info
        if permitidos and (ruta == '/admin' or ruta.startswith('/admin/')):
            if request.get_host().lower() not in permitidos:
                raise Http404
        return self.get_response(request)
