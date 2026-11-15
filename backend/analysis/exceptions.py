from django.db import DatabaseError
from rest_framework.views import exception_handler
from rest_framework.response import Response

def api_exception_handler(exc, context):
    if isinstance(exc, DatabaseError):
        return Response({'detail':'PostgreSQL no disponible o esquema pendiente de migrar.'}, status=503)
    return exception_handler(exc, context)
