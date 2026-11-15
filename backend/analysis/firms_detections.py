import json
import os
import csv
import math
from datetime import date, datetime, timezone
from pathlib import Path

from django.conf import settings


DATA_DIR = Path(settings.BASE_DIR).parent / "src" / "datos"

FILES = {
    "MODIS": DATA_DIR / "modis.csv",
    "VIIRS": DATA_DIR / "viirs.csv",
}

BOUNDS = {
    "south": 19.35,
    "north": 19.60,
    "west": -102.15,
    "east": -101.80,
}

REQUIRED = {
    "latitude",
    "longitude",
    "acq_date",
    "acq_time",
    "satellite",
    "instrument",
    "confidence",
    "frp",
}


def parse_number(value):
    if value is None or value.strip() == "":
        return None

    number = float(value)

    if not math.isfinite(number):
        raise ValueError("Valor numerico no finito")

    return number


def read_source_detections(
    sensor=None,
    requested_date=None,
    satellite=None,
):
    sensors = [sensor] if sensor else list(FILES)
    results = []

    for current_sensor in sensors:
        path = FILES[current_sensor]

        if not path.is_file():
            raise FileNotFoundError(str(path))

        with path.open(
            "r", encoding="utf-8-sig", newline=""
        ) as file:
            reader = csv.DictReader(file)

            if not REQUIRED.issubset(reader.fieldnames or []):
                raise ValueError(
                    f"Columnas faltantes en {path.name}"
                )

            for line_number, row in enumerate(
                reader, start=2
            ):
                if (
                    requested_date
                    and row["acq_date"] != requested_date
                ):
                    continue

                if (
                    satellite
                    and row["satellite"] != satellite
                ):
                    continue

                lat = parse_number(row["latitude"])
                lon = parse_number(row["longitude"])

                if lat is None or lon is None:
                    continue

                if not (
                    BOUNDS["south"] <= lat <= BOUNDS["north"]
                    and BOUNDS["west"] <= lon <= BOUNDS["east"]
                ):
                    continue

                acquisition_date = date.fromisoformat(
                    row["acq_date"]
                )

                acquisition_time = row["acq_time"].strip()

                if not (
                    len(acquisition_time) <= 4
                    and acquisition_time.isdigit()
                ):
                    raise ValueError(
                        "Hora de adquisicion invalida"
                    )

                acquisition_time = acquisition_time.zfill(4)

                observed_at = datetime.strptime(
                    acquisition_date.isoformat()
                    + acquisition_time,
                    "%Y-%m-%d%H%M",
                ).replace(tzinfo=timezone.utc)

                results.append({
                    "id": (
                        f"{current_sensor}-"
                        f"{line_number}"
                    ),
                    "sensor": current_sensor,
                    "satellite": row["satellite"],
                    "instrument": row["instrument"],
                    "latitude": lat,
                    "longitude": lon,
                    "acq_date": row["acq_date"],
                    "acq_time": acquisition_time,
                    "observed_at": (
                        observed_at.isoformat()
                        .replace("+00:00", "Z")
                    ),
                    "confidence": row["confidence"],
                    "frp": parse_number(row["frp"]),
                    "brightness": parse_number(
                        row.get("brightness")
                    ),
                    "daynight": row.get("daynight"),
                    "source_file": path.name,
                    "source_line": line_number,
                })

    return results

CACHE_FILE = (
    Path(settings.BASE_DIR).parent
    / "src"
    / "resultados_lotes"
    / "firms_pilot_cache.json"
)


def build_detections_cache():
    """
    Genera una copia procesada de las detecciones
    del piloto conservando sus campos originales.
    """
    records = read_source_detections()

    payload = {
        "source": "FIRMS-format CSV (provenance pending)",
        "records": records,
        "source_mtimes_ns": {
            sensor: path.stat().st_mtime_ns
            for sensor, path in FILES.items()
        },
    }

    CACHE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = CACHE_FILE.with_suffix(".tmp")

    try:
        with temporary.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                payload,
                file,
                ensure_ascii=False,
                allow_nan=False,
            )

        os.replace(temporary, CACHE_FILE)
    finally:
        temporary.unlink(missing_ok=True)

    return len(records)


def read_detections(
    sensor=None,
    requested_date=None,
    satellite=None,
):
    """
    Lee el conjunto procesado y aplica los filtros.
    No recorre los CSV originales por solicitud.
    """
    if not CACHE_FILE.is_file():
        raise FileNotFoundError(
            "No existe la cache FIRMS. "
            "Ejecuta build_firms_cache."
        )

    with CACHE_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(file)

    for name, source_path in FILES.items():
        if not source_path.is_file():
            raise FileNotFoundError(
                f"Falta archivo de origen: {source_path}"
            )

        stored_mtime = payload[
            "source_mtimes_ns"
        ].get(name)

        if stored_mtime != source_path.stat().st_mtime_ns:
            raise ValueError(
                "Cache desactualizada. "
                "Ejecuta build_firms_cache."
            )

    results = payload["records"]

    return [
        record
        for record in results
        if (
            not sensor
            or record["sensor"] == sensor
        )
        and (
            not requested_date
            or record["acq_date"] == requested_date
        )
        and (
            not satellite
            or record["satellite"] == satellite
        )
    ]
