
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


def read_detections(
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
