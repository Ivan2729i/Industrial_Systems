
import h3


def build_comparison(spatial_cells, temporal_cells):
    """
    Integra los resultados espaciales y temporales
    utilizando identificadores H3.

    No determina comparabilidad científica.
    """

    temporal_index = {}

    # Indexar las observaciones temporales
    for record in temporal_cells:
        cell_id = record["celda_h3"]

        if cell_id in temporal_index:
            raise ValueError(
                f"Celda temporal duplicada: {cell_id}"
            )

        temporal_index[cell_id] = record

    spatial_ids = set()
    results = []

    # Recorrer las celdas del análisis espacial
    for spatial in spatial_cells:
        cell_id = spatial["celda_h3"]

        if not h3.is_valid_cell(cell_id):
            raise ValueError(
                f"Identificador H3 inválido: {cell_id}"
            )

        if h3.get_resolution(cell_id) != 7:
            raise ValueError(
                f"Resolución H3 incorrecta: {cell_id}"
            )

        if cell_id in spatial_ids:
            raise ValueError(
                f"Celda espacial duplicada: {cell_id}"
            )

        spatial_ids.add(cell_id)

        temporal = temporal_index.get(cell_id)

        has_temporal = temporal is not None

        results.append({
            "celda_h3": cell_id,

            "modis_pixeles": spatial["modis_pixeles"],
            "viirs_pixeles": spatial["viirs_pixeles"],

            "modis_fuego": spatial["modis_fuego"],
            "viirs_fuego": spatial["viirs_fuego"],

            "observacion_util_ambos": spatial[
                "observacion_util_ambos"
            ],

            "has_temporal_data": has_temporal,

            "temporal_difference_min": (
                temporal["diferencia_min"]
                if has_temporal else None
            ),

            "modis_utc": (
                temporal["modis_utc"]
                if has_temporal else None
            ),

            "viirs_utc": (
                temporal["viirs_utc"]
                if has_temporal else None
            ),

            "temporal_validation": (
                "pending"
                if has_temporal else "not_available"
            ),

            "comparable": None,
        })

    # Comprobar que ninguna celda temporal sea desconocida
    missing_spatial = set(temporal_index) - spatial_ids

    if missing_spatial:
        raise ValueError(
            "Existen celdas temporales ausentes "
            "del análisis espacial"
        )

    return {
        "summary": {
            "total_cells": len(results),

            "cells_with_temporal_data": sum(
                cell["has_temporal_data"]
                for cell in results
            ),

            "cells_without_temporal_data": sum(
                not cell["has_temporal_data"]
                for cell in results
            ),

            "cells_with_both_usable": sum(
                cell["observacion_util_ambos"]
                for cell in results
            ),
        },

        "scientific_validation": "pending",
        "cells": results,
    }
