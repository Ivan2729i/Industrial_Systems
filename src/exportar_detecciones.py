
import csv
from pathlib import Path

import h3
import numpy as np

from auditar_detecciones import (
    encontrar,
    leer_modis,
    leer_viirs,
    SUR,
    NORTE,
    OESTE,
    ESTE,
)


BASE = Path(__file__).resolve().parent
SALIDA = (
    BASE / "resultados_lotes"
    / "detecciones_2024-04-06.csv"
)

FECHA = "2024-04-06"
RESOLUCION_H3 = 7
CLASES_FUEGO = {7, 8, 9}

CAMPOS = [
    "id",
    "sensor",
    "fecha",
    "latitud",
    "longitud",
    "celda_h3",
    "clasificacion",
    "fila",
    "columna",
    "sobrevuelo",
    "producto",
    "archivo_origen",
    "observed_at",
    "estado",
]


def extraer_detecciones(
    sensor,
    datos,
    sobrevuelo,
    producto,
    archivo_origen,
):
    mascara = np.asarray(datos["fire mask"])

    filas = np.asarray(
        datos["FP_line"], dtype=int
    ).ravel()

    columnas = np.asarray(
        datos["FP_sample"], dtype=int
    ).ravel()

    latitudes = np.asarray(
        datos["FP_latitude"], dtype=float
    ).ravel()

    longitudes = np.asarray(
        datos["FP_longitude"], dtype=float
    ).ravel()

    if mascara.ndim != 2:
        raise ValueError("Mascara de fuego invalida")

    if len({
        len(filas),
        len(columnas),
        len(latitudes),
        len(longitudes),
    }) != 1:
        raise ValueError(
            "Las dimensiones de las detecciones no coinciden"
        )

    registros = []
    identificadores = set()

    for fila, columna, lat, lon in zip(
        filas, columnas, latitudes, longitudes
    ):
        # Verificar indices originales del producto
        if not (
            0 <= fila < mascara.shape[0]
            and 0 <= columna < mascara.shape[1]
        ):
            raise ValueError(
                f"Indice invalido en {sensor}"
            )

        # Verificar coordenadas
        if not (
            np.isfinite(lat) and np.isfinite(lon)
            and -90 <= lat <= 90
            and -180 <= lon <= 180
        ):
            raise ValueError(
                f"Coordenadas invalidas en {sensor}"
            )

        # Seleccionar region piloto
        if not (
            SUR <= lat <= NORTE
            and OESTE <= lon <= ESTE
        ):
            continue

        clasificacion = int(
            mascara[fila, columna]
        )

        if clasificacion not in CLASES_FUEGO:
            raise ValueError(
                f"Deteccion con clase no esperada: "
                f"{clasificacion}"
            )

        identificador = (
            f"{sensor}-{sobrevuelo}-{fila}-{columna}"
        )

        if identificador in identificadores:
            raise ValueError(
                f"Deteccion duplicada: {identificador}"
            )

        identificadores.add(identificador)

        celda = h3.latlng_to_cell(
            float(lat),
            float(lon),
            RESOLUCION_H3,
        )

        registros.append({
            "id": identificador,
            "sensor": sensor,
            "fecha": FECHA,
            "latitud": float(lat),
            "longitud": float(lon),
            "celda_h3": celda,
            "clasificacion": clasificacion,
            "fila": int(fila),
            "columna": int(columna),
            "sobrevuelo": sobrevuelo,
            "producto": producto,
            "archivo_origen": archivo_origen,
            "observed_at": "",
            "estado": "pendiente_validacion",
        })

    return registros


def main():
    print("FIRESIGHT - EXPORTACION DE DETECCIONES")

    fuentes = [
        {
            "sensor": "MODIS",
            "sobrevuelo": "A2024097.2020",
            "producto": "MYD14",
            "prefijo": "MYD14.A2024097.2020.061.",
            "lector": leer_modis,
        },
        {
            "sensor": "VIIRS",
            "sobrevuelo": "A2024097.2030",
            "producto": "VNP14IMG",
            "prefijo": "VNP14IMG.A2024097.2030.002.",
            "lector": leer_viirs,
        },
    ]

    registros = []

    for fuente in fuentes:
        archivo = encontrar(fuente["prefijo"])
        datos = fuente["lector"]()

        detecciones = extraer_detecciones(
            sensor=fuente["sensor"],
            datos=datos,
            sobrevuelo=fuente["sobrevuelo"],
            producto=fuente["producto"],
            archivo_origen=archivo.name,
        )

        print(
            f'{fuente["sensor"]}: '
            f'{len(detecciones)} detecciones en region'
        )

        registros.extend(detecciones)

    SALIDA.parent.mkdir(
        parents=True, exist_ok=True
    )

    with SALIDA.open(
        "w", encoding="utf-8-sig", newline=""
    ) as archivo:
        escritor = csv.DictWriter(
            archivo, fieldnames=CAMPOS
        )

        escritor.writeheader()
        escritor.writerows(registros)

    print(f"\nTotal exportado: {len(registros)}")
    print(f"Archivo generado: {SALIDA}")
    print("Estado: pendiente de validacion")


if __name__ == "__main__":
    main()
