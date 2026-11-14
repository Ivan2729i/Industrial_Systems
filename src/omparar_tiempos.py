
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h3
import h5py
import numpy as np
import pandas as pd
from pyhdf.SD import SD, SDC
import argparse
from analizar_celdas import CONFIGURACIONES


# FIRESIGHT - COMPARACION TEMPORAL POR CELDA H3


BASE = Path(__file__).resolve().parent

parser = argparse.ArgumentParser(
    description="FireSight - Comparacion temporal MODIS-VIIRS"
)

parser.add_argument(
    "--fecha",
    default="2024-04-06-noche",
    choices=sorted(CONFIGURACIONES),
)

args = parser.parse_args()

config = CONFIGURACIONES[args.fecha]

DATOS = config["carpeta"]
MODIS_ID = config["modis"]
VIIRS_ID = config["viirs"]

if args.fecha == "2024-04-06-noche":
    SALIDA = (
        BASE / "resultados_lotes"
        / "tiempos_2024-04-06_noche.csv"
    )
else:
    hora_modis = MODIS_ID.split(".")[1]
    hora_viirs = VIIRS_ID.split(".")[1]

    SALIDA = (
        BASE / "resultados_lotes"
        / f"tiempos_{args.fecha}_{hora_modis}_{hora_viirs}.csv"
    )


SUR, NORTE = 19.35, 19.60
OESTE, ESTE = -102.15, -101.80
RESOLUCION_H3 = 7

# Valido para las observaciones analizadas de 2024.
# Para otras epocas se debe consultar la tabla de
# segundos intercalares, no dejar este valor fijo.
LEAP_SECONDS_1993_2024 = 10

EPOCA_TAI93 = datetime(
    1993, 1, 1, tzinfo=timezone.utc
)

CELDAS_FUEGO = (
    "874985089ffffff",
    "8749850d4ffffff",
)


def encontrar(prefijo):
    archivos = list(DATOS.glob(prefijo + "*"))

    if len(archivos) != 1:
        raise RuntimeError(
            f"{prefijo}: encontrados {len(archivos)} archivos"
        )

    return archivos[0]


def convertir_utc(tai93):
    return EPOCA_TAI93 + timedelta(
        seconds=float(tai93) - LEAP_SECONDS_1993_2024
    )


def formato_utc(tai93):
    return convertir_utc(tai93).strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )[:-3] + " UTC"


def registrar(registros, lat, lon, mascara, tiempo):
    dentro = (
        np.isfinite(lat)
        & np.isfinite(lon)
        & (lat >= SUR)
        & (lat <= NORTE)
        & (lon >= OESTE)
        & (lon <= ESTE)
    )

    utiles = np.isin(mascara, (5, 7, 8, 9))
    filas, columnas = np.where(dentro & utiles)

    for fila, columna in zip(filas, columnas):
        celda = h3.latlng_to_cell(
            float(lat[fila, columna]),
            float(lon[fila, columna]),
            RESOLUCION_H3,
        )

        registro = registros[celda]
        registro["tiempos"].add(float(tiempo))
        registro["pixeles_utiles"] += 1

        if int(mascara[fila, columna]) in (7, 8, 9):
            registro["fuego"] += 1


def crear_registros():
    return defaultdict(
        lambda: {
            "tiempos": set(),
            "pixeles_utiles": 0,
            "fuego": 0,
        }
    )


def procesar_modis():
    ruta_geo = encontrar(f"MYD03.{MODIS_ID}.061.")
    ruta_fire = encontrar(f"MYD14.{MODIS_ID}.061.")

    registros = crear_registros()

    geo = SD(str(ruta_geo), SDC.READ)
    fire = None

    try:
        fire = SD(str(ruta_fire), SDC.READ)

        lat_ds = geo.select("Latitude")
        lon_ds = geo.select("Longitude")
        mask_ds = fire.select("fire mask")

        tiempos = np.asarray(
            geo.select("EV center time").get(),
            dtype=float,
        ).ravel()

        filas, columnas = mask_ds.info()[2]

        if not (
            lat_ds.info()[2] == lon_ds.info()[2]
            == mask_ds.info()[2]
        ):
            raise ValueError("Dimensiones MODIS incompatibles")

        if len(tiempos) == 0 or filas % len(tiempos):
            raise ValueError(
                "No se pudo relacionar tiempo y filas MODIS"
            )

        filas_por_escaneo = filas // len(tiempos)

        if filas_por_escaneo != 10:
            raise ValueError(
                "Se esperaban 10 filas por escaneo MODIS"
            )

        print(
            f"MODIS: {len(tiempos)} escaneos, "
            f"{filas_por_escaneo} filas por escaneo"
        )

        for indice, tiempo in enumerate(tiempos):
            if not np.isfinite(tiempo) or tiempo < 0:
                continue

            inicio = indice * filas_por_escaneo
            cantidad = (filas_por_escaneo, columnas)
            posicion = (inicio, 0)

            lat = lat_ds.get(
                start=posicion, count=cantidad
            )
            lon = lon_ds.get(
                start=posicion, count=cantidad
            )
            mascara = mask_ds.get(
                start=posicion, count=cantidad
            )

            mascara = np.bitwise_and(mascara, 15)

            registrar(
                registros, lat, lon, mascara, tiempo
            )

    finally:
        if fire is not None:
            fire.end()
        geo.end()

    return registros


def procesar_viirs():
    ruta_geo = encontrar(f"VNP03IMG.{VIIRS_ID}.002.")
    ruta_fire = encontrar(f"VNP14IMG.{VIIRS_ID}.002.")

    registros = crear_registros()

    with (
        h5py.File(ruta_geo, "r") as geo,
        h5py.File(ruta_fire, "r") as fire,
    ):
        lat_ds = geo["geolocation_data/latitude"]
        lon_ds = geo["geolocation_data/longitude"]
        mask_ds = fire["fire mask"]

        tiempos = np.asarray(
            geo["scan_line_attributes/ev_mid_time"][:],
            dtype=float,
        )

        if not (
            lat_ds.shape == lon_ds.shape
            == mask_ds.shape
        ):
            raise ValueError("Dimensiones VIIRS incompatibles")

        filas, columnas = mask_ds.shape

        if len(tiempos) == 0 or filas % len(tiempos):
            raise ValueError(
                "No se pudo relacionar tiempo y filas VIIRS"
            )

        filas_por_escaneo = filas // len(tiempos)

        if filas_por_escaneo != 32:
            raise ValueError(
                "Se esperaban 32 filas por escaneo VIIRS"
            )

        print(
            f"VIIRS: {len(tiempos)} escaneos, "
            f"{filas_por_escaneo} filas por escaneo"
        )

        for indice, tiempo in enumerate(tiempos):
            if not np.isfinite(tiempo) or tiempo < 0:
                continue

            inicio = indice * filas_por_escaneo
            fin = inicio + filas_por_escaneo

            registrar(
                registros,
                lat_ds[inicio:fin, :],
                lon_ds[inicio:fin, :],
                mask_ds[inicio:fin, :],
                tiempo,
            )

    return registros



def tiempo_cercano(modis, viirs):
    return min(
        (
            (abs(m - v), m, v)
            for m in modis
            for v in viirs
        ),
        key=lambda resultado: resultado[0],
    )



def main():
    print("FIRESIGHT - COMPARACION TEMPORAL")
    print(f"Michoacan | {args.fecha}")
    print("=" * 55)

    modis = procesar_modis()
    viirs = procesar_viirs()

    comunes = sorted(set(modis) & set(viirs))

    print(f"\nCeldas utiles MODIS: {len(modis)}")
    print(f"Celdas utiles VIIRS: {len(viirs)}")
    print(f"Celdas con tiempos de ambos: {len(comunes)}")

    registros = []

    for celda in comunes:
        m = modis[celda]
        v = viirs[celda]

        tiempos_m = sorted(m["tiempos"])
        tiempos_v = sorted(v["tiempos"])

        diferencia_seg, tiempo_modis, tiempo_viirs = tiempo_cercano(
            tiempos_m, tiempos_v
        )

        registros.append({
            "celda_h3": celda,
            "modis_utc": formato_utc(tiempo_modis),
            "viirs_utc": formato_utc(tiempo_viirs),
            "diferencia_min": round(
                diferencia_seg / 60, 3
            ),
            "modis_pixeles_utiles": m["pixeles_utiles"],
            "viirs_pixeles_utiles": v["pixeles_utiles"],
            "modis_fuego": m["fuego"],
            "viirs_fuego": v["fuego"],
        })

    df = pd.DataFrame(registros)

    if df.empty:
        print("No hay celdas con tiempos de ambos sensores.")
        return

    SALIDA.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(
        SALIDA,
        index=False,
        encoding="utf-8-sig",
    )

    print("\nDIFERENCIAS TEMPORALES")
    print(
        "Minima:",
        round(df["diferencia_min"].min(), 3),
        "min"
    )
    print(
        "Mediana:",
        round(df["diferencia_min"].median(), 3),
        "min"
    )
    print(
        "Maxima:",
        round(df["diferencia_min"].max(), 3),
        "min"
    )

    print("\nCELDAS CON FUEGO VIIRS")

    focos = df[
        (df["modis_fuego"] > 0)
        | (df["viirs_fuego"] > 0)
        ]

    if focos.empty:
        print("No se encontraron las celdas esperadas.")
    else:
        print(
            focos[
                [
                    "celda_h3",
                    "modis_utc",
                    "viirs_utc",
                    "diferencia_min",
                    "modis_fuego",
                    "viirs_fuego",
                ]
            ].to_string(index=False)
        )

    print("\nCSV generado:", SALIDA)
    print("\nCOMPARACION FINALIZADA")
    print(
        "\nNOTA: Se comparan tiempos centrales de "
        "escaneos con pixeles utiles en una misma "
        "celda H3. No son tiempos individuales "
        "exactos de cada pixel."
    )


if __name__ == "__main__":
    main()
