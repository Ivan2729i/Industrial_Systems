
from pathlib import Path

import h3
import h5py
import numpy as np
from pyhdf.SD import SD, SDC

BASE = Path(__file__).resolve().parent / "datos" / "level2"

# Rectangulo seleccionado en NASA Earthdata: Veracruz
# Nueva zona de prueba con actividad detectada: Michoacan
OESTE = -102.15
ESTE = -101.80
SUR = 19.35
NORTE = 19.60
RESOLUCION_H3 = 7
BLOQUE_FILAS = 32


def archivo(prefijo):
    encontrados = list(BASE.glob(prefijo + "*"))

    if len(encontrados) != 1:
        raise RuntimeError(
            f"{prefijo}: se encontraron "
            f"{len(encontrados)} archivos; se esperaba uno"
        )

    return encontrados[0]


def registrar(resultados, lat, lon, valido, fuego, conteos):
    dentro = (
        np.isfinite(lat)
        & np.isfinite(lon)
        & (lat >= SUR)
        & (lat <= NORTE)
        & (lon >= OESTE)
        & (lon <= ESTE)
    )

    conteos["centros"] += int(dentro.sum())
    conteos["validos"] += int((dentro & valido).sum())
    conteos["fuego"] += int((dentro & fuego).sum())

    filas, columnas = np.where(dentro & (valido | fuego))

    for fila, columna in zip(filas, columnas):
        celda = h3.latlng_to_cell(
            float(lat[fila, columna]),
            float(lon[fila, columna]),
            RESOLUCION_H3
        )

        estado = resultados.setdefault(
            celda, {"observado": False, "fuego": False}
        )

        estado["observado"] |= bool(valido[fila, columna])
        estado["fuego"] |= bool(fuego[fila, columna])


def procesar_modis():
    ruta_geo = archivo("MYD03.A2024097.2020.061.")
    ruta_fire = archivo("MYD14.A2024097.2020.061.")

    geo = SD(str(ruta_geo), SDC.READ)
    fire = SD(str(ruta_fire), SDC.READ)

    try:
        lat_ds = geo.select("Latitude")
        lon_ds = geo.select("Longitude")
        mask_ds = fire.select("fire mask")

        dimensiones = geo.datasets()["Latitude"][1]

        if tuple(dimensiones) != tuple(
            fire.datasets()["fire mask"][1]
        ):
            raise ValueError("Dimensiones MODIS incompatibles")

        filas_total, columnas_total = dimensiones

        resultados = {}
        conteos = {"centros": 0, "validos": 0, "fuego": 0}

        for inicio in range(0, filas_total, BLOQUE_FILAS):
            cantidad = min(BLOQUE_FILAS, filas_total - inicio)
            inicio_hdf = (inicio, 0)
            dimensiones_hdf = (cantidad, columnas_total)

            lat = lat_ds.get(
                start=inicio_hdf, count=dimensiones_hdf
            )
            lon = lon_ds.get(
                start=inicio_hdf, count=dimensiones_hdf
            )
            mascara = mask_ds.get(
                start=inicio_hdf, count=dimensiones_hdf
            )

            # Clasificacion MODIS: bits 0 a 3
            clase = mascara & 15

            # Tierra sin fuego o fuego detectado
            valido = (clase == 5) | (clase >= 7) & (clase <= 9)
            fuego_detectado = (clase >= 7) & (clase <= 9)

            registrar(
                resultados, lat, lon,
                valido, fuego_detectado, conteos
            )

        return resultados, conteos

    finally:
        geo.end()
        fire.end()



def procesar_viirs():
    ruta_geo = archivo("VNP03IMG.A2024097.2030.002.")
    ruta_fire = archivo("VNP14IMG.A2024097.2030.002.")

    resultados = {}
    conteos = {
        "centros": 0,
        "validos": 0,
        "fuego": 0
    }

    with h5py.File(ruta_geo, "r") as geo, \
         h5py.File(ruta_fire, "r") as fire:

        lat_ds = geo["geolocation_data/latitude"]
        lon_ds = geo["geolocation_data/longitude"]
        mask_ds = fire["fire mask"]

        # Comprobar que las tres matrices coincidan.
        if not (
            lat_ds.shape == lon_ds.shape == mask_ds.shape
        ):
            raise ValueError(
                "Dimensiones VIIRS incompatibles"
            )

        filas_total, columnas_total = mask_ds.shape

        print(
            f"\nProcesando VIIRS 375 m: "
            f"{filas_total} x {columnas_total}"
        )

        for inicio in range(0, filas_total, BLOQUE_FILAS):
            fin = min(
                inicio + BLOQUE_FILAS,
                filas_total
            )

            # Leer por bloques para controlar la memoria.
            lat = lat_ds[inicio:fin, :]
            lon = lon_ds[inicio:fin, :]
            mascara = mask_ds[inicio:fin, :]

            # 5 = terreno sin fuego
            # 7, 8, 9 = detecciones de fuego
            valido = np.isin(
                mascara, [5, 7, 8, 9]
            )

            fuego_detectado = np.isin(
                mascara, [7, 8, 9]
            )

            registrar(
                resultados,
                lat,
                lon,
                valido,
                fuego_detectado,
                conteos
            )

    return resultados, conteos



def resumir(nombre, resultados, conteos):
    observadas = {
        celda for celda, estado in resultados.items()
        if estado["observado"]
    }

    con_fuego = {
        celda for celda, estado in resultados.items()
        if estado["fuego"]
    }

    print(f"\n{nombre}")
    print(f"Centros en rectangulo: {conteos['centros']:,}")
    print(f"Centros validos:       {conteos['validos']:,}")
    print(f"Centros con fuego:     {conteos['fuego']:,}")
    print(f"Celdas H3 observadas:  {len(observadas):,}")
    print(f"Celdas H3 con fuego:   {len(con_fuego):,}")

    return observadas, con_fuego


def main():
    print("FIRESIGHT - PRUEBA EXPLORATORIA DE COBERTURA")
    print("Region: Michoacan | 2024-04-06")
    print("=" * 55)

    modis, conteos_m = procesar_modis()
    viirs, conteos_v = procesar_viirs()

    observadas_m, fuego_m = resumir(
        "MODIS", modis, conteos_m
    )

    observadas_v, fuego_v = resumir(
        "VIIRS", viirs, conteos_v
    )

    comunes = observadas_m & observadas_v

    print("\nCOMPARACION")
    print(f"Celdas con observacion valida en ambos: {len(comunes)}")
    print(f"Fuego en ambos: {len(fuego_m & fuego_v & comunes)}")
    print(f"Fuego solo MODIS: {len((fuego_m - fuego_v) & comunes)}")
    print(f"Fuego solo VIIRS: {len((fuego_v - fuego_m) & comunes)}")

    if not comunes:
        print("\nAVISO: No se encontro cobertura valida compartida.")
        print("Esta pareja no sirve para calibrar la region elegida.")
    else:
        print("\nCobertura compartida preliminar identificada.")
        print("Aun falta validar tiempo y geometria de los pixeles.")

    print("\nPRUEBA FINALIZADA")


if __name__ == "__main__":
    main()
