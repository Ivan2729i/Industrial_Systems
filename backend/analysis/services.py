
import csv
from pathlib import Path
from datetime import date as Date
from django.conf import settings


CSV_DIRECTORY = Path(settings.BASE_DIR).parent / "src"

INTEGER_FIELDS = {
    "resolucion_h3",
    "modis_pixeles",
    "modis_utiles",
    "modis_nubes",
    "modis_otros",
    "modis_fuego",
    "viirs_pixeles",
    "viirs_utiles",
    "viirs_nubes",
    "viirs_reflejo_solar",
    "viirs_otros",
    "viirs_fuego",
}

FLOAT_FIELDS = {
    "modis_util_pct",
    "viirs_util_pct",
    "viirs_reflejo_solar_pct",
}

BOOLEAN_FIELDS = {
    "observacion_util_ambos",
    "fuego_ambos",
    "deteccion_solo_modis",
    "deteccion_solo_viirs",
    "fuego_solo_modis",
    "fuego_solo_viirs",
    "supera_umbral_exploratorio",
}


def convert_row(row):
    result = {}

    for field, value in row.items():
        if field in INTEGER_FIELDS:
            result[field] = int(value)
        elif field in FLOAT_FIELDS:
            result[field] = float(value)
        elif field in BOOLEAN_FIELDS:
            if value not in ("True", "False"):
                raise ValueError(
                    f"Valor booleano invalido: {field}"
                )
            result[field] = value == "True"
        else:
            result[field] = value

    return result


def load_cells(date):
    path = CSV_DIRECTORY / f"analisis_celdas_{date}.csv"

    if not path.is_file():
        raise FileNotFoundError(
            f"No existe un CSV para {date}"
        )

    cells = []

    with path.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            cells.append(convert_row(row))

    return cells


def calculate_statistics(cells):
    def count_if(field):
        return sum(
            1 for cell in cells
            if cell[field]
        )

    return {
        "total_cells": len(cells),

        "modis_observed_cells": sum(
            cell["modis_pixeles"] > 0
            for cell in cells
        ),

        "viirs_observed_cells": sum(
            cell["viirs_pixeles"] > 0
            for cell in cells
        ),

        "both_observed_cells": count_if(
            "observacion_util_ambos"
        ),

        "modis_fire_pixels": sum(
            cell["modis_fuego"]
            for cell in cells
        ),

        "viirs_fire_pixels": sum(
            cell["viirs_fuego"]
            for cell in cells
        ),

        "both_fire_cells": count_if(
            "fuego_ambos"
        ),

        "modis_only_cells": count_if(
            "deteccion_solo_modis"
        ),

        "viirs_only_cells": count_if(
            "deteccion_solo_viirs"
        ),
    }


import re

def get_available_dates():
    """
    Devuelve fechas con archivos de análisis
    disponibles en el directorio configurado.
    """
    dates = set()

    pattern = re.compile(
        r"^analisis_celdas_(\d{4}-\d{2}-\d{2})\.csv$"
    )

    for file in CSV_DIRECTORY.glob("analisis_celdas_*.csv"):
        match = pattern.fullmatch(file.name)

        if not match:
            continue

        candidate = match.group(1)

        try:
            parsed = Date.fromisoformat(candidate)
        except ValueError:
            continue

        if parsed.isoformat() == candidate:
            dates.add(candidate)

    return sorted(dates)
