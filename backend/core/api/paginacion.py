"""Paginación por defecto de toda la API (ver REST_FRAMEWORK en settings.py).

Vive en su propio módulo, separada de `base.py`, a propósito: DRF importa esta
clase al cargar sus propias vistas genéricas, y `base.py` a su vez importa
esas vistas — si estuviera ahí, se arma un import circular y Django no arranca."""
from rest_framework.pagination import PageNumberPagination


class Paginacion(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'por_pagina'
    max_page_size = 200
