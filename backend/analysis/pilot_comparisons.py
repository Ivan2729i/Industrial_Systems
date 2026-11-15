
import csv
import math
from collections import Counter
from pathlib import Path

from django.conf import settings


PILOT_FILE = (
    Path(settings.BASE_DIR).parent
    / "src"
    / "resultados_lotes"
    / "observaciones_pareadas_piloto.csv"
)

KEY_FIELDS = (
    "modis_sobrevuelo",
    "viirs_sobrevuelo",
    "celda_h3",
)

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
    "qa_originales",
    "viirs_bowtie_residual",
    "viirs_geo_no_nominal",
    "viirs_fuego_sin_bowtie",
}

FLOAT_FIELDS = {
    "modis_util_pct",
    "viirs_util_pct",
    "viirs_reflejo_solar_pct",
    "cobertura_compartida_pct",
    "diferencia_min",
}

BOOLEAN_FIELDS = {
    "observacion_util_ambos",
    "fuego_ambos",
    "deteccion_solo_modis",
    "deteccion_solo_viirs",
    "fuego_solo_modis",
    "fuego_solo_viirs",
    "supera_umbral_exploratorio",
    "comparacion_candidata",
    "metodologia_validada",
    "viirs_detecta",
    "modis_detecta",
    "viirs_detecta_sin_bowtie",
}

STATUSES = {
    "candidata_experimental",
    "fuera_de_umbrales",
    "sin_observacion_util_compartida",
    "pendiente_medicion",
}

REQUIRED_FIELDS = (
    set(KEY_FIELDS)
    | INTEGER_FIELDS
    | FLOAT_FIELDS
    | BOOLEAN_FIELDS
    | {"fecha", "estado_comparacion",
       "modis_utc", "viirs_utc", "region"}
)


def convert_value(field, value):
    if value is None:
        return None

    value = value.strip()

    if value == "":
        return None

    if field in BOOLEAN_FIELDS:
        if value not in {"True", "False"}:
            raise ValueError(
                f"Booleano invalido en {field}: {value}"
            )
        return value == "True"

    if field in INTEGER_FIELDS:
        number = int(value)
        if number < 0:
            raise ValueError(
                f"Conteo negativo en {field}"
            )
        return number

    if field in FLOAT_FIELDS:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(
                f"Numero no finito en {field}"
            )
        if field == "diferencia_min" and number < 0:
            raise ValueError(
                "Diferencia temporal negativa"
            )
        return number

    return value


def load_pilot_comparisons():
    if not PILOT_FILE.is_file():
        raise FileNotFoundError(
            "No existe el CSV consolidado del piloto"
        )

    records = []
    keys = set()

    with PILOT_FILE.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)

        if (
            reader.fieldnames is None
            or not REQUIRED_FIELDS.issubset(reader.fieldnames)
        ):
            raise ValueError(
                "Faltan columnas requeridas en el CSV"
            )

        for row_number, row in enumerate(reader, start=2):
            record = {
                field: convert_value(field, value)
                for field, value in row.items()
            }

            key = tuple(
                record[field] for field in KEY_FIELDS
            )

            if any(value is None for value in key):
                raise ValueError(
                    f"Clave incompleta en fila {row_number}"
                )

            if key in keys:
                raise ValueError(
                    f"Clave duplicada en fila {row_number}"
                )

            keys.add(key)

            if record["estado_comparacion"] not in STATUSES:
                raise ValueError(
                    f"Estado desconocido en fila {row_number}"
                )

            records.append(record)

    return records


def filter_pilot_comparisons(
    records,
    date=None,
    status=None,
    modis_overpass=None,
    viirs_overpass=None,
):
    filtered = []

    for record in records:
        if date and record["fecha"] != date:
            continue

        if status and record["estado_comparacion"] != status:
            continue

        if (
            modis_overpass
            and record["modis_sobrevuelo"] != modis_overpass
        ):
            continue

        if (
            viirs_overpass
            and record["viirs_sobrevuelo"] != viirs_overpass
        ):
            continue

        filtered.append(record)

    return filtered


def summarize_pilot(records):
    statuses = Counter(
        row["estado_comparacion"]
        for row in records
    )

    return {
        "total_records": len(records),
        "experimental_candidates": sum(
            row["comparacion_candidata"] is True
            for row in records
        ),
        "validated_records": sum(
            row["metodologia_validada"] is True
            for row in records
        ),
        "modis_fire_pixels": sum(
            row["modis_fuego"] for row in records
        ),
        "viirs_fire_pixels": sum(
            row["viirs_fuego"] for row in records
        ),
        "by_status": {
            name: statuses.get(name, 0)
            for name in sorted(STATUSES)
        },
    }
