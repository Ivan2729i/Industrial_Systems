
from pathlib import Path
from math import radians, sin, cos, asin, sqrt

import h5py
import numpy as np

BASE = Path(__file__).resolve().parent / "datos" / "level2"

SUR, NORTE = 19.35, 19.60
OESTE, ESTE = -102.15, -101.80


def encontrar(prefijo):
    archivos = list(BASE.glob(prefijo + "*"))

    if len(archivos) != 1:
        raise RuntimeError(
            f"{prefijo}: se esperaban 1 archivo, "
            f"encontrados {len(archivos)}"
        )

    return archivos[0]


def distancia_m(lat1, lon1, lat2, lon2):
    radio = 6371000.0

    a1, a2 = radians(lat1), radians(lat2)
    dlat = a2 - a1
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(a1) * cos(a2) * sin(dlon / 2) ** 2
    )

    return 2 * radio * asin(min(1.0, sqrt(a)))


def main():
    ruta_fire = encontrar("VNP14IMG.A2024097.2030.002.")
    ruta_geo = encontrar("VNP03MODLL.A2024097.2030.002.")

    with h5py.File(ruta_fire, "r") as fire, \
         h5py.File(ruta_geo, "r") as geo:

        base = (
            "HDFEOS/SWATHS/VNP_750M_GEOLOCATION/"
            "Geolocation Fields/"
        )

        lat_geo = geo[base + "Latitude"]
        lon_geo = geo[base + "Longitude"]

        filas = fire["FP_line"][:].astype(int)
        columnas = fire["FP_sample"][:].astype(int)

        lat_fp = fire["FP_latitude"][:]
        lon_fp = fire["FP_longitude"][:]

        if not (
            len(filas) == len(columnas)
            == len(lat_fp) == len(lon_fp)
        ):
            raise ValueError("Arreglos de detecciones incompatibles")

        errores_globales = []
        errores_region = []
        invalidos = 0

        for fila, col, lat, lon in zip(
            filas, columnas, lat_fp, lon_fp
        ):
            # Aproximacion al pixel de 750 m
            f = fila // 2
            c = col // 2

            if not (
                0 <= f < lat_geo.shape[0]
                and 0 <= c < lat_geo.shape[1]
            ):
                invalidos += 1
                continue

            lat_aprox = float(lat_geo[f, c])
            lon_aprox = float(lon_geo[f, c])

            if not (
                -90 <= lat_aprox <= 90
                and -180 <= lon_aprox <= 180
                and np.isfinite(lat_aprox)
                and np.isfinite(lon_aprox)
            ):
                invalidos += 1
                continue

            error = distancia_m(
                float(lat), float(lon),
                lat_aprox, lon_aprox
            )

            errores_globales.append(error)

            if SUR <= lat <= NORTE and OESTE <= lon <= ESTE:
                errores_region.append(error)

    print("FIRESIGHT - VALIDACION GEOGRAFICA VIIRS")
    print("=" * 45)
    print(f"Detecciones analizadas: {len(filas)}")
    print(f"Sin ubicacion valida: {invalidos}")

    for nombre, valores in [
        ("Segmento completo", errores_globales),
        ("Region Michoacan", errores_region),
    ]:
        print(f"\n{nombre}")

        if not valores:
            print("Sin detecciones para evaluar")
            continue

        print(f"Detecciones: {len(valores)}")
        print(f"Distancia mediana: {np.median(valores):.1f} m")
        print(f"Percentil 95: {np.percentile(valores, 95):.1f} m")
        print(f"Distancia maxima: {np.max(valores):.1f} m")

    print("\nDIAGNOSTICO FINALIZADO")


if __name__ == "__main__":
    main()
