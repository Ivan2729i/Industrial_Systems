
def calculate_coverage(cells):
    """
    Resume cobertura y observación útil
    usando los indicadores del CSV procesado.

    No determina comparabilidad temporal.
    """
    total = len(cells)

    modis_observed = sum(
        cell["modis_pixeles"] > 0
        for cell in cells
    )

    viirs_observed = sum(
        cell["viirs_pixeles"] > 0
        for cell in cells
    )

    both_observed = sum(
        cell["modis_pixeles"] > 0
        and cell["viirs_pixeles"] > 0
        for cell in cells
    )

    both_usable = sum(
        cell["observacion_util_ambos"]
        for cell in cells
    )

    modis_fire_cells = sum(
        cell["modis_fuego"] > 0
        for cell in cells
    )

    viirs_fire_cells = sum(
        cell["viirs_fuego"] > 0
        for cell in cells
    )

    return {
        "total_cells": total,
        "coverage": {
            "modis_observed_cells": modis_observed,
            "viirs_observed_cells": viirs_observed,
            "both_observed_cells": both_observed,
            "both_usable_cells": both_usable,
        },
        "fire": {
            "modis_fire_cells": modis_fire_cells,
            "viirs_fire_cells": viirs_fire_cells,
        },
        "temporal_comparability": {
            "status": "not_evaluated"
        },
    }
