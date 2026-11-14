
from pathlib import Path

import h5py
import numpy as np
from pyhdf.SD import SD, SDC

BASE = Path(__file__).resolve().parent / "datos" / "level2"

SUR, NORTE = 19.35, 19.60
OESTE, ESTE = -102.15, -101.80


def encontrar(prefijo):
    archivos = list(BASE.glob(prefijo + "*"))
    if len(archivos) != 1:
        raise RuntimeError(
            f"{prefijo}: encontrados {len(archivos)} archivos"
        )
    return archivos[0]


def leer_modis():
    ruta = encontrar("MYD14.A2024097.2020.061.")
    archivo = SD(str(ruta), SDC.READ)

    try:
        return {
            nombre: archivo.select(nombre).get()
            for nombre in (
                "fire mask",
                "FP_line",
                "FP_sample",
                "FP_latitude",
                "FP_longitude",
            )
        }
    finally:
        archivo.end()


def leer_viirs():
    ruta = encontrar("VNP14IMG.A2024097.2030.002.")

    with h5py.File(ruta, "r") as archivo:
        return {
            nombre: archivo[nombre][:]
            for nombre in (
                "fire mask",
                "FP_line",
                "FP_sample",
                "FP_latitude",
                "FP_longitude",
            )
        }


def auditar(nombre, datos):
    mascara = datos["fire mask"]
    filas = np.asarray(datos["FP_line"], dtype=int)
    columnas = np.asarray(datos["FP_sample"], dtype=int)
    lat = np.asarray(datos["FP_latitude"])
    lon = np.asarray(datos["FP_longitude"])

    assert len(filas) == len(columnas) == len(lat) == len(lon)

    indices_validos = (
        (filas >= 0) & (filas < mascara.shape[0])
        & (columnas >= 0)
        & (columnas < mascara.shape[1])
    )

    region = (
        (lat >= SUR) & (lat <= NORTE)
        & (lon >= OESTE) & (lon <= ESTE)
    )

    seleccion = indices_validos & region

    clases = mascara[
        filas[seleccion],
        columnas[seleccion]
    ]

    fuego = np.isin(clases, [7, 8, 9])

    print(f"\n===== {nombre} =====")
    print(f"Detecciones del segmento: {len(filas)}")
    print(f"Indices invalidos: {(~indices_validos).sum()}")
    print(f"Detecciones en region: {seleccion.sum()}")
    print(f"Clasificadas como fuego: {fuego.sum()}")
    print(f"Inconsistencias: {(~fuego).sum()}")

    valores, frecuencias = np.unique(
        clases, return_counts=True
    )

    print("Clases de mascara:")
    for valor, cantidad in zip(valores, frecuencias):
        print(f"  Clase {valor}: {cantidad}")

    return int((~fuego).sum())


def main():
    print("FIRESIGHT - AUDITORIA DE DETECCIONES")

    errores_m = auditar("MODIS", leer_modis())
    errores_v = auditar("VIIRS", leer_viirs())

    print("\nRESULTADO")
    if errores_m == 0 and errores_v == 0:
        print("Detecciones verificadas contra las mascaras.")
    else:
        print("Existen discrepancias que debemos investigar.")


if __name__ == "__main__":
    main()
