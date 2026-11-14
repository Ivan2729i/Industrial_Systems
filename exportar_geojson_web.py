
import json
from pathlib import Path

import h3
import numpy as np
import pandas as pd


BASE = Path(__file__).resolve().parent / "src"

ENTRADA = (
    BASE / "resultados_lotes"
    / "observaciones_h3_armonizadas_v1.csv"
)

SALIDA = (
    BASE / "resultados_lotes" / "web"
    / "observaciones_h3_v1.geojson"
)

CAMPOS = [
    "region_id",
    "fecha",
    "modis_sobrevuelo",
    "viirs_sobrevuelo",
    "celda_h3",
    "modis_fuego",
    "viirs_fuego",
    "viirs_fuego_sin_bowtie",
    "diferencia_min",
    "cobertura_compartida_pct",
    "estrato_temporal",
    "coincidencia_original",
    "coincidencia_qa",
    "alineacion_experimental",
    "qa_viirs_disponible",
    "version_armonizacion",
]


def convertir_valor(valor):
    if valor is None or pd.isna(valor):
        return None

    if isinstance(valor, np.generic):
        return valor.item()

    return valor


def convertir_celda(celda):
    if not h3.is_valid_cell(celda):
        raise ValueError(
            f"Identificador H3 invalido: {celda}"
        )

    # H3 devuelve (latitud, longitud).
    # GeoJSON exige [longitud, latitud].
    vertices = [
        [float(lon), float(lat)]
        for lat, lon in h3.cell_to_boundary(celda)
    ]

    vertices.append(vertices[0].copy())

    return {
        "type": "Polygon",
        "coordinates": [vertices],
    }


def main():
    if not ENTRADA.is_file():
        raise FileNotFoundError(
            f"No existe el dataset V1: {ENTRADA}"
        )

    df = pd.read_csv(
        ENTRADA,
        dtype={"celda_h3": str},
    )

    claves = [
        "region_id",
        "modis_sobrevuelo",
        "viirs_sobrevuelo",
        "celda_h3",
    ]

    if df[claves].isna().any().any():
        raise ValueError(
            "Hay identificadores incompletos."
        )

    if df.duplicated(claves).any():
        raise ValueError(
            "Hay observaciones duplicadas."
        )

    features = []

    for _, fila in df.iterrows():
        celda = fila["celda_h3"]

        propiedades = {
            campo: convertir_valor(fila[campo])
            if campo in df.columns else None
            for campo in CAMPOS
        }

        identificador = (
            f"{fila['region_id']}:"
            f"{fila['modis_sobrevuelo']}:"
            f"{fila['viirs_sobrevuelo']}:"
            f"{celda}"
        )

        features.append({
            "type": "Feature",
            "id": identificador,
            "geometry": convertir_celda(celda),
            "properties": propiedades,
        })

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    SALIDA.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with SALIDA.open(
        "w",
        encoding="utf-8",
    ) as archivo:
        json.dump(
            geojson,
            archivo,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )

    print("FIRESIGHT - EXPORTACION PARA WEB")
    print("=" * 45)
    print("Observaciones:", len(df))
    print("Poligonos GeoJSON:", len(features))
    print("Archivo generado:", SALIDA)
    print(
        "\nNota: los poligonos representan "
        "celdas H3, no perimetros reales "
        "de incendios."
    )


if __name__ == "__main__":
    main()
