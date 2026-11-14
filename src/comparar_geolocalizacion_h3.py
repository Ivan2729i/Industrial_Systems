
from pathlib import Path

import h3
import h5py
import numpy as np

BASE = Path(__file__).resolve().parent / "datos" / "level2"

SUR, NORTE = 19.35, 19.60
OESTE, ESTE = -102.15, -101.80


def encontrar(prefijo):
    archivos = list(BASE.glob(prefijo + "*"))

    if len(archivos) != 1:
        raise RuntimeError(
            f"Se esperaba un archivo {prefijo}, "
            f"encontrados: {len(archivos)}"
        )

    return archivos[0]


def main():
    ruta_fire = encontrar("VNP14IMG.A2024097.2030.002.")
    ruta_geo = encontrar("VNP03MODLL.A2024097.2030.002.")

    base_geo = (
        "HDFEOS/SWATHS/VNP_750M_GEOLOCATION/"
        "Geolocation Fields/"
    )

    with h5py.File(ruta_fire, "r") as fire, \
         h5py.File(ruta_geo, "r") as geo:

        filas = fire["FP_line"][:].astype(int)
        columnas = fire["FP_sample"][:].astype(int)

        lat_original = fire["FP_latitude"][:]
        lon_original = fire["FP_longitude"][:]

        lat_ds = geo[base_geo + "Latitude"]
        lon_ds = geo[base_geo + "Longitude"]

        if len(filas) != len(columnas) or \
           len(filas) != len(lat_original) or \
           len(filas) != len(lon_original):
            raise ValueError("Arreglos de detecciones incompatibles")

        f = filas // 2
        c = columnas // 2

        indices_validos = (
            (f >= 0) & (f < lat_ds.shape[0])
            & (c >= 0) & (c < lat_ds.shape[1])
        )

        if not indices_validos.all():
            raise ValueError("Existen indices fuera de la matriz")

        # h5py admite indices escalares para esta muestra.
        lat_aprox = np.array([
            lat_ds[int(fi), int(ci)]
            for fi, ci in zip(f, c)
        ])

        lon_aprox = np.array([
            lon_ds[int(fi), int(ci)]
            for fi, ci in zip(f, c)
        ])

    validos = (
        np.isfinite(lat_original)
        & np.isfinite(lon_original)
        & np.isfinite(lat_aprox)
        & np.isfinite(lon_aprox)
        & (lat_original >= -90) & (lat_original <= 90)
        & (lon_original >= -180) & (lon_original <= 180)
        & (lat_aprox >= -90) & (lat_aprox <= 90)
        & (lon_aprox >= -180) & (lon_aprox <= 180)
    )

    region = (
        validos
        & (lat_original >= SUR)
        & (lat_original <= NORTE)
        & (lon_original >= OESTE)
        & (lon_original <= ESTE)
    )

    print("FIRESIGHT - COMPARACION GEOLOCALIZACION H3")
    print(f"Detecciones totales: {len(filas)}")
    print(f"Coordenadas validas: {validos.sum()}")
    print(f"Detecciones en Michoacan: {region.sum()}")

    for res in [6, 7, 8]:
        print(f"\n===== H3 RESOLUCION {res} =====")

        for nombre, seleccion in [
            ("Segmento completo", validos),
            ("Michoacan", region),
        ]:
            indices = np.flatnonzero(seleccion)

            originales = [
                h3.latlng_to_cell(
                    float(lat_original[i]),
                    float(lon_original[i]),
                    res
                )
                for i in indices
            ]

            aproximadas = [
                h3.latlng_to_cell(
                    float(lat_aprox[i]),
                    float(lon_aprox[i]),
                    res
                )
                for i in indices
            ]

            cambios = sum(
                a != b
                for a, b in zip(originales, aproximadas)
            )

            total = len(indices)
            porcentaje = 100 * cambios / total if total else 0

            print(f"\n{nombre}")
            print(f"Detecciones: {total}")
            print(f"Cambian de celda: {cambios}")
            print(f"Porcentaje: {porcentaje:.2f}%")

    print("\nCOMPARACION FINALIZADA")


if __name__ == "__main__":
    main()
