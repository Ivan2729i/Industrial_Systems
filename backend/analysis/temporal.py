
import csv
import math
from datetime import datetime
from pathlib import Path
from statistics import median

from django.conf import settings


TEMPORAL_DIRECTORY = (
    Path(settings.BASE_DIR).parent
    / "src"
    / "resultados_lotes"
)

REQUIRED_FIELDS = {
    "celda_h3",
    "modis_utc",
    "viirs_utc",
    "diferencia_min",
    "modis_pixeles_utiles",
    "viirs_pixeles_utiles",
    "modis_fuego",
    "viirs_fuego",
}

INTEGER_FIELDS = {
    "modis_pixeles_utiles",
    "viirs_pixeles_utiles",
    "modis_fuego",
    "viirs_fuego",
}


def load_temporal_data(date):
    """
    Lee un resultado temporal existente.
    No reprocesa los archivos satelitales.
    """
    files = sorted(
        TEMPORAL_DIRECTORY.glob(
            f"tiempos_{date}_*.csv"
        )
    )

    if not files:
        raise FileNotFoundError(
            f"No hay resultados temporales para {date}"
        )

    if len(files) > 1:
        raise ValueError(
            "Existen varios análisis temporales "
            "para la fecha solicitada."
        )

    records = []
    seen_cells = set()

    with files[0].open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)

        if not REQUIRED_FIELDS.issubset(
            set(reader.fieldnames or [])
        ):
            raise ValueError(
                "Faltan columnas temporales obligatorias"
            )

        for row in reader:
            cell = row["celda_h3"]

            if cell in seen_cells:
                raise ValueError(
                    f"Celda H3 duplicada: {cell}"
                )
            seen_cells.add(cell)

            record = dict(row)

            for field in INTEGER_FIELDS:
                record[field] = int(row[field])
                if record[field] < 0:
                    raise ValueError(
                        f"Conteo negativo: {field}"
                    )

            difference = float(row["diferencia_min"])

            if not math.isfinite(difference) or difference < 0:
                raise ValueError(
                    "Diferencia temporal inválida"
                )

            record["diferencia_min"] = difference

            for field in ("modis_utc", "viirs_utc"):
                datetime.strptime(
                    row[field], "%Y-%m-%d %H:%M:%S.%f UTC"
                )

            records.append(record)

    return records


def calculate_temporal_summary(records):
    differences = [
        record["diferencia_min"]
        for record in records
    ]

    if not differences:
        return {
            "total_cells": 0,
            "minimum_difference_min": None,
            "median_difference_min": None,
            "maximum_difference_min": None,
        }

    return {
        "total_cells": len(records),
        "minimum_difference_min": min(differences),
        "median_difference_min": median(differences),
        "maximum_difference_min": max(differences),
    }
