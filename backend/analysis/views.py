from django.shortcuts import render

from datetime import date as Date
from .services import get_available_dates
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .geojson import cells_to_geojson
from .coverage import calculate_coverage
from .temporal import (
    load_temporal_data,
    calculate_temporal_summary,
)


from .services import load_cells
from .services import load_cells, calculate_statistics

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


@api_view(["GET"])
def statistics_view(request):
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
            {"error": "Formato de fecha invalido."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        cells = load_cells(requested_date)
        statistics = calculate_statistics(cells)

    except FileNotFoundError:
        return Response(
            {"error": "No hay datos para esa fecha."},
            status=status.HTTP_404_NOT_FOUND,
        )

    except (ValueError, TypeError, KeyError):
        return Response(
            {"error": "No se pudieron procesar los datos."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        "date": requested_date,
        "statistics": statistics,
    })


@api_view(["GET"])
def geojson_view(request):
    requested_date = request.query_params.get("date")

    if not requested_date:
        return Response(
            {"error": "Debes proporcionar una fecha."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        parsed_date = Date.fromisoformat(requested_date)

        if parsed_date.isoformat() != requested_date:
            raise ValueError("Formato incorrecto")

    except ValueError:
        return Response(
            {"error": "Fecha invalida. Usa YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        cells = load_cells(requested_date)
        geojson = cells_to_geojson(cells)

    except FileNotFoundError:
        return Response(
            {"error": "No hay datos para esa fecha."},
            status=status.HTTP_404_NOT_FOUND,
        )

    except (ValueError, TypeError, KeyError):
        return Response(
            {"error": "Los datos geograficos son invalidos."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(geojson)


@api_view(["GET"])
def available_dates_view(request):
    dates = get_available_dates()

    return Response({
        "available_dates": dates,
        "total": len(dates),
    })


@api_view(["GET"])
def coverage_view(request):
    requested_date = request.query_params.get("date")

    if not requested_date:
        return Response(
            {"error": "Debes proporcionar una fecha."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        parsed_date = Date.fromisoformat(requested_date)

        if parsed_date.isoformat() != requested_date:
            raise ValueError("Formato incorrecto")

    except ValueError:
        return Response(
            {"error": "Fecha invalida. Usa YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        cells = load_cells(requested_date)
        result = calculate_coverage(cells)

    except FileNotFoundError:
        return Response(
            {"error": "No hay datos para esa fecha."},
            status=status.HTTP_404_NOT_FOUND,
        )

    except (ValueError, TypeError, KeyError):
        return Response(
            {"error": "Datos de cobertura invalidos."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        "date": requested_date,
        **result,
    })


@api_view(["GET"])
def temporal_view(request):
    requested_date = request.query_params.get("date")

    if not requested_date:
        return Response(
            {"error": "Debes proporcionar una fecha."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        parsed = Date.fromisoformat(requested_date)

        if parsed.isoformat() != requested_date:
            raise ValueError

    except ValueError:
        return Response(
            {"error": "Fecha inválida. Usa YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        records = load_temporal_data(requested_date)
        summary = calculate_temporal_summary(records)

    except FileNotFoundError:
        return Response(
            {"error": "No hay análisis temporal para esa fecha."},
            status=status.HTTP_404_NOT_FOUND,
        )

    except (ValueError, TypeError, KeyError) as exc:
        return Response(
            {"error": str(exc)},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return Response({
        "date": requested_date,
        "status": "measured_not_validated",
        "summary": summary,
        "cells": records,
    })

