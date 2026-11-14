
import csv
from pathlib import Path

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
