
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

from pyhdf.SD import SD, SDC
from pyproj import Geod


# FireSight: auditoria puntual MODIS - VIIRS

BASE = Path(__file__).resolve().parent
DATOS = BASE / "datos" / "lotes" / "2024-04-06-noche"
SALIDA = BASE / "resultados_lotes" / "auditoria_focos.csv"

SUR, NORTE = 19.35, 19.60
OESTE, ESTE = -102.15, -101.80

MARGEN_GRADOS = 0.07
RADIO_VECINOS_M = 2000

GEOD = Geod(ellps="WGS84")
EPOCA = datetime(1993, 1, 1, tzinfo=timezone.utc)

# Conversion especifica para los productos de 2024.
SEGUNDOS_INTERCALARES = 10


def encontrar(prefijo):
    archivos = list(DATOS.glob(prefijo + "*"))

    if len(archivos) != 1:
        raise RuntimeError(
            f"{prefijo}: encontrados {len(archivos)} archivos"
        )

    return archivos[0]


def formato_utc(tai93):
    fecha = EPOCA + timedelta(
        seconds=float(tai93) - SEGUNDOS_INTERCALARES
    )
    return fecha.isoformat(timespec="milliseconds")


def obtener_focos_viirs():
    ruta_fire = encontrar("VNP14IMG.A2024097.0918.002.")
    ruta_geo = encontrar("VNP03IMG.A2024097.0918.002.")

    focos = []

    with h5py.File(ruta_fire, "r") as fire, \
         h5py.File(ruta_geo, "r") as geo:

        filas = fire["FP_line"][:].astype(int)
        columnas = fire["FP_sample"][:].astype(int)
        latitudes = fire["FP_latitude"][:]
        longitudes = fire["FP_longitude"][:]

        mascara = fire["fire mask"]

        tiempos = geo[
            "scan_line_attributes/ev_mid_time"
        ][:]

        if mascara.shape[0] != len(tiempos) * 32:
            raise ValueError(
                "Relacion filas-escaneos VIIRS invalida"
            )

        for fila, columna, lat, lon in zip(
            filas, columnas, latitudes, longitudes
        ):
            if not (
                SUR <= lat <= NORTE
                and OESTE <= lon <= ESTE
            ):
                continue

            if not (
                0 <= fila < mascara.shape[0]
                and 0 <= columna < mascara.shape[1]
            ):
                raise ValueError(
                    "Indice de deteccion VIIRS invalido"
                )

            clase = int(mascara[fila, columna])

            if clase not in (7, 8, 9):
                raise ValueError(
                    f"Deteccion inconsistente: clase {clase}"
                )

            indice_escaneo = fila // 32
            tiempo = float(tiempos[indice_escaneo])

            focos.append({
                "viirs_fila": int(fila),
                "viirs_columna": int(columna),
                "latitud": float(lat),
                "longitud": float(lon),
                "viirs_clase": clase,
                "viirs_tai93": tiempo,
                "viirs_utc": formato_utc(tiempo),
            })

    return focos


def obtener_pixeles_modis():
    ruta_geo = encontrar("MYD03.A2024097.0925.061.")
    ruta_fire = encontrar("MYD14.A2024097.0925.061.")

    candidatos = []

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

        if filas != len(tiempos) * 10:
            raise ValueError(
                "Relacion filas-escaneos MODIS invalida"
            )

        for indice, tiempo in enumerate(tiempos):
            if not np.isfinite(tiempo):
                continue

            inicio = indice * 10
            posicion = (inicio, 0)
            cantidad = (10, columnas)

            lat = lat_ds.get(
                start=posicion, count=cantidad
            )
            lon = lon_ds.get(
                start=posicion, count=cantidad
            )
            mascara = np.bitwise_and(
                mask_ds.get(
                    start=posicion,
                    count=cantidad
                ),
                15
            )

            dentro = (
                np.isfinite(lat)
                & np.isfinite(lon)
                & (lat >= SUR - MARGEN_GRADOS)
                & (lat <= NORTE + MARGEN_GRADOS)
                & (lon >= OESTE - MARGEN_GRADOS)
                & (lon <= ESTE + MARGEN_GRADOS)
            )

            ff, cc = np.where(dentro)

            for f, c in zip(ff, cc):
                candidatos.append({
                    "lat": float(lat[f, c]),
                    "lon": float(lon[f, c]),
                    "clase": int(mascara[f, c]),
                    "fila": int(inicio + f),
                    "columna": int(c),
                    "tai93": float(tiempo),
                })

    finally:
        if fire is not None:
            fire.end()
        geo.end()

    return candidatos


def comparar(focos, candidatos):
    if not candidatos:
        raise RuntimeError(
            "No se encontraron pixeles MODIS cercanos"
        )

    lat_m = np.array([p["lat"] for p in candidatos])
    lon_m = np.array([p["lon"] for p in candidatos])
    clases_m = np.array([p["clase"] for p in candidatos])

    resultados = []

    for foco in focos:
        cantidad = len(candidatos)

        _, _, distancias = GEOD.inv(
            np.full(cantidad, foco["longitud"]),
            np.full(cantidad, foco["latitud"]),
            lon_m,
            lat_m,
        )

        cercano = int(np.argmin(distancias))
        pixel = candidatos[cercano]

        vecinos = distancias <= RADIO_VECINOS_M

        sin_fuego = int(np.count_nonzero(
            vecinos & (clases_m == 5)
        ))

        con_fuego = int(np.count_nonzero(
            vecinos & np.isin(clases_m, [7, 8, 9])
        ))

        diferencia_min = abs(
            pixel["tai93"] - foco["viirs_tai93"]
        ) / 60

        resultados.append({
            "viirs_fila": foco["viirs_fila"],
            "viirs_columna": foco["viirs_columna"],
            "latitud": foco["latitud"],
            "longitud": foco["longitud"],
            "viirs_clase": foco["viirs_clase"],
            "viirs_utc": foco["viirs_utc"],

            "modis_fila_cercana": pixel["fila"],
            "modis_columna_cercana": pixel["columna"],
            "modis_clase_cercana": pixel["clase"],
            "modis_utc": formato_utc(pixel["tai93"]),

            "distancia_centros_m": round(
                float(distancias[cercano]), 2
            ),
            "diferencia_min": round(
                diferencia_min, 3
            ),
            "modis_sin_fuego_2km": sin_fuego,
            "modis_con_fuego_2km": con_fuego,
        })

    return pd.DataFrame(resultados)


def main():
    print("FIRESIGHT - AUDITORIA PUNTUAL DE FOCOS")
    print("Michoacan | 2024-04-06 | Madrugada")
    print("=" * 55)

    focos = obtener_focos_viirs()
    candidatos = obtener_pixeles_modis()

    print(f"Focos VIIRS en la region: {len(focos)}")
    print(f"Centros MODIS candidatos: {len(candidatos)}")

    if not focos:
        print("No se encontraron focos VIIRS.")
        return

    df = comparar(focos, candidatos)

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(
        SALIDA, index=False, encoding="utf-8-sig"
    )

    print("\nRESULTADOS")
    print(
        df[
            [
                "latitud",
                "longitud",
                "viirs_clase",
                "modis_clase_cercana",
                "distancia_centros_m",
                "diferencia_min",
                "modis_sin_fuego_2km",
            ]
        ].to_string(index=False)
    )

    print("\nCSV generado:", SALIDA)
    print("\nAUDITORIA FINALIZADA")
    print(
        "\nAVISO: La distancia entre centros "
        "no demuestra que ambos pixeles tengan "
        "la misma huella geografica."
    )


if __name__ == "__main__":
    main()
