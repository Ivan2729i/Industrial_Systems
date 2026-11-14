
from pathlib import Path

import h3
import h5py
import numpy as np
from pyhdf.SD import SD, SDC

BASE = Path(__file__).resolve().parent / "datos" / "level2"

# Rectangulo original
SUR, NORTE = 19.35, 19.60
OESTE, ESTE = -102.15, -101.80


def encontrar(prefijo):
    archivos = list(BASE.glob(prefijo + "*"))

    if len(archivos) != 1:
        raise RuntimeError(
            f"Se esperaba 1 archivo {prefijo}, "
            f"encontrados: {len(archivos)}"
        )

    return archivos[0]


def leer_modis():
    ruta = encontrar("MYD14.A2024097.2020.061.")
    archivo = SD(str(ruta), SDC.READ)

    try:
        lat = archivo.select("FP_latitude").get()
        lon = archivo.select("FP_longitude").get()
    finally:
        archivo.end()

    return limpiar(lat, lon)


def leer_viirs():
    ruta = encontrar("VNP14IMG.A2024097.2030.002.")

    with h5py.File(ruta, "r") as archivo:
        lat = archivo["FP_latitude"][:]
        lon = archivo["FP_longitude"][:]

    return limpiar(lat, lon)


def limpiar(lat, lon):
    lat = np.asarray(lat, dtype=float).ravel()
    lon = np.asarray(lon, dtype=float).ravel()

    validos = (
        np.isfinite(lat)
        & np.isfinite(lon)
        & (lat >= -90) & (lat <= 90)
        & (lon >= -180) & (lon <= 180)
    )

    return list(zip(lat[validos], lon[validos]))


def dentro_veracruz(puntos):
    return [
        (lat, lon) for lat, lon in puntos
        if SUR <= lat <= NORTE
        and OESTE <= lon <= ESTE
    ]


def celdas(puntos, resolucion):
    resultado = {}

    for lat, lon in puntos:
        celda = h3.latlng_to_cell(
            float(lat), float(lon), resolucion
        )
        resultado.setdefault(celda, []).append((lat, lon))

    return resultado


def main():
    print("FIRESIGHT - VERIFICACION DE FOCOS LEVEL 2")
    print("=" * 50)

    modis = leer_modis()
    viirs = leer_viirs()

    print(f"Focos MODIS en segmento: {len(modis):,}")
    print(f"Focos VIIRS en segmento: {len(viirs):,}")

    print("\nRectangulo de Veracruz:")
    print(f"MODIS: {len(dentro_veracruz(modis))}")
    print(f"VIIRS: {len(dentro_veracruz(viirs))}")

    for resolucion in [6, 7]:
        m = celdas(dentro_veracruz(modis), resolucion)
        v = celdas(dentro_veracruz(viirs), resolucion)

        comunes = sorted(set(m) & set(v))

        print(f"\nH3 resolucion {resolucion}")
        print(f"Celdas con fuego MODIS: {len(m)}")
        print(f"Celdas con fuego VIIRS: {len(v)}")
        print(f"Celdas con fuego en ambos: {len(comunes)}")

        for celda in comunes[:10]:
            lat, lon = h3.cell_to_latlng(celda)
            print(
                f"  Celda {celda} "
                f"| centro: {lat:.5f}, {lon:.5f} "
                f"| MODIS: {len(m[celda])} "
                f"| VIIRS: {len(v[celda])}"
            )

    print("\nDIAGNOSTICO FINALIZADO")


if __name__ == "__main__":
    main()
