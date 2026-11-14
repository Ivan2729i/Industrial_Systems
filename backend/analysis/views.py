from django.shortcuts import render

from datetime import date as Date

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .services import load_cells


@api_view(["GET"])
def cells_list(request):
    requested_date = request.query_params.get("date")

    if not requested_date:
        return Response(
            {"error": "Debes proporcionar una fecha."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        Date.fromisoformat(requested_date)
    except ValueError:
        return Response(
            {"error": "Formato de fecha invalido. Usa YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        cells = load_cells(requested_date)

    except FileNotFoundError:
        return Response(
            {"error": "No hay datos para esa fecha."},
            status=status.HTTP_404_NOT_FOUND,
        )

    except (ValueError, TypeError):
        return Response(
            {"error": "El archivo contiene datos invalidos."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        "date": requested_date,
        "total": len(cells),
        "data": cells,
    })

# Create your views here.
