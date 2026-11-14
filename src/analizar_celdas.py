
import argparse
from collections import defaultdict
from pathlib import Path

import h3
import h5py
import numpy as np
import pandas as pd
from pyhdf.SD import SD, SDC


# ==================================================
# CONFIGURACION GENERAL
# ==================================================

BASE = Path(__file__).resolve().parent

# Region de prueba: Michoacan, Mexico
SUR = 19.35
NORTE = 19.60
OESTE = -102.15
ESTE = -101.80

RESOLUCION_H3 = 7
BLOQUE_FILAS = 32

# Umbral experimental, NO cobertura geografica real.
UMBRAL_UTIL = 80.0

FECHA_PREDETERMINADA = "2024-04-08"


# ==================================================
# SOBREVUELOS DISPONIBLES
# ==================================================

CONFIGURACIONES = {
    "2024-04-06": {
        "carpeta": BASE / "datos" / "level2",
        "modis": "A2024097.2020",
        "viirs": "A2024097.2030",
    },
    "2024-04-08": {
        "carpeta": BASE / "datos" / "lotes" / "2024-04-08",
        "modis": "A2024099.2000",
        "viirs": "A2024099.1954",
    },

    "2024-04-06-noche": {
        "carpeta": BASE / "datos" / "lotes" / "2024-04-06-noche",
        "modis": "A2024097.0925",
        "viirs": "A2024097.0918",
    },
}


CONFIGURACIONES.update({
    "2024-04-19": {
        "carpeta": Path(__file__).resolve().parent / "datos" / "lotes" / "2024-04-19",
        "modis": "A2024110.0830",
        "viirs": "A2024110.0836",
    },
    "2024-04-16": {
        "carpeta": Path(__file__).resolve().parent / "datos" / "lotes" / "2024-04-16",
        "modis": "A2024107.2035",
        "viirs": "A2024107.2042",
    },
})



# ==================================================
# ARCHIVOS
# ==================================================

def encontrar_archivo(carpeta, prefijo):
    if not carpeta.is_dir():
        raise FileNotFoundError(
            f"No existe el directorio: {carpeta}"
        )

    encontrados = sorted(carpeta.glob(f"{prefijo}*"))

    if len(encontrados) != 1:
        raise RuntimeError(
            f"Se esperaba un archivo con prefijo "
            f"'{prefijo}', encontrados: {len(encontrados)}"
        )

    return encontrados[0]


# ==================================================
# CONTADORES
# ==================================================

def crear_contadores():
    return defaultdict(
        lambda: {
            "total": 0,
            "utiles": 0,
            "fuego": 0,
            "nube": 0,
            "reflejo_solar": 0,
            "otros": 0,
        }
    )


def agregar_pixeles(
    resultados,
    latitudes,
    longitudes,
    mascara,
    es_modis=False,
):
    if not (
        latitudes.shape
        == longitudes.shape
        == mascara.shape
    ):
        raise ValueError(
            "Las matrices de coordenadas y mascara "
            "no tienen las mismas dimensiones."
        )

    # En MODIS, la clase ocupa los cuatro bits bajos.
    if es_modis:
        clases = np.bitwise_and(mascara, 15)
    else:
        clases = mascara

    # Seleccion por centro de pixel.
    dentro = (
        np.isfinite(latitudes)
        & np.isfinite(longitudes)
        & (latitudes >= SUR)
        & (latitudes <= NORTE)
        & (longitudes >= OESTE)
        & (longitudes <= ESTE)
    )

    filas, columnas = np.where(dentro)

    for fila, columna in zip(filas, columnas):
        lat = float(latitudes[fila, columna])
        lon = float(longitudes[fila, columna])
        clase = int(clases[fila, columna])

        celda = h3.latlng_to_cell(
            lat,
            lon,
            RESOLUCION_H3,
        )

        registro = resultados[celda]
        registro["total"] += 1

        # Clases aceptadas como observacion util
        # para este experimento.
        if clase in (5, 7, 8, 9):
            registro["utiles"] += 1

        # Detecciones de fuego.
        if clase in (7, 8, 9):
            registro["fuego"] += 1

        # Clasificacion excluyente para calidad.
        if clase == 4:
            registro["nube"] += 1

        elif not es_modis and clase == 2:
            # VIIRS: posible reflejo solar.
            registro["reflejo_solar"] += 1

        elif clase not in (5, 7, 8, 9):
            registro["otros"] += 1


# ==================================================
# MODIS AQUA
# ==================================================

def procesar_modis(carpeta, fecha_hora):
    print("\nProcesando MODIS Aqua...", flush=True)

    ruta_geo = encontrar_archivo(
        carpeta,
        f"MYD03.{fecha_hora}.061.",
    )

    ruta_fire = encontrar_archivo(
        carpeta,
        f"MYD14.{fecha_hora}.061.",
    )

    print(f"Geolocalizacion: {ruta_geo.name}")
    print(f"Mascara: {ruta_fire.name}")

    resultados = crear_contadores()

    geo = SD(str(ruta_geo), SDC.READ)
    fire = None

    try:
        fire = SD(str(ruta_fire), SDC.READ)

        lat_ds = geo.select("Latitude")
        lon_ds = geo.select("Longitude")
        mask_ds = fire.select("fire mask")

        forma_lat = tuple(lat_ds.info()[2])
        forma_lon = tuple(lon_ds.info()[2])
        forma_mask = tuple(mask_ds.info()[2])

        if not (
            forma_lat == forma_lon == forma_mask
        ):
            raise ValueError(
                "Dimensiones MODIS incompatibles: "
                f"{forma_lat}, {forma_lon}, {forma_mask}"
            )

        filas, columnas = forma_mask
        print(f"Dimensiones: {filas} x {columnas}")

        for inicio in range(0, filas, BLOQUE_FILAS):
            cantidad = min(
                BLOQUE_FILAS,
                filas - inicio,
            )

            inicio_hdf = (inicio, 0)
            forma_bloque = (cantidad, columnas)

            lat = lat_ds.get(
                start=inicio_hdf,
                count=forma_bloque,
            )

            lon = lon_ds.get(
                start=inicio_hdf,
                count=forma_bloque,
            )

            mascara = mask_ds.get(
                start=inicio_hdf,
                count=forma_bloque,
            )

            agregar_pixeles(
                resultados,
                lat,
                lon,
                mascara,
                es_modis=True,
            )

    finally:
        if fire is not None:
            fire.end()
        geo.end()

    print(
        f"Celdas MODIS: {len(resultados)}",
        flush=True,
    )

    return resultados


# ==================================================
# VIIRS S-NPP
# ==================================================

def procesar_viirs(carpeta, fecha_hora):
    print("\nProcesando VIIRS S-NPP...", flush=True)

    ruta_geo = encontrar_archivo(
        carpeta,
        f"VNP03IMG.{fecha_hora}.002.",
    )

    ruta_fire = encontrar_archivo(
        carpeta,
        f"VNP14IMG.{fecha_hora}.002.",
    )

    print(f"Geolocalizacion: {ruta_geo.name}")
    print(f"Mascara: {ruta_fire.name}")

    resultados = crear_contadores()

    with (
        h5py.File(ruta_geo, "r") as geo,
        h5py.File(ruta_fire, "r") as fire,
    ):
        lat_ds = geo["geolocation_data/latitude"]
        lon_ds = geo["geolocation_data/longitude"]
        mask_ds = fire["fire mask"]

        if not (
            lat_ds.shape
            == lon_ds.shape
            == mask_ds.shape
        ):
            raise ValueError(
                "Dimensiones VIIRS incompatibles: "
                f"{lat_ds.shape}, "
                f"{lon_ds.shape}, "
                f"{mask_ds.shape}"
            )

        filas, columnas = mask_ds.shape
        print(f"Dimensiones: {filas} x {columnas}")

        for inicio in range(0, filas, BLOQUE_FILAS):
            fin = min(
                inicio + BLOQUE_FILAS,
                filas,
            )

            agregar_pixeles(
                resultados,
                lat_ds[inicio:fin, :],
                lon_ds[inicio:fin, :],
                mask_ds[inicio:fin, :],
                es_modis=False,
            )

    print(
        f"Celdas VIIRS: {len(resultados)}",
        flush=True,
    )

    return resultados


# ==================================================
# INDICADORES
# ==================================================

def porcentaje(parte, total):
    if total == 0:
        return 0.0

    return round(100.0 * parte / total, 2)


def generar_tabla(modis, viirs, fecha, config):
    registros = []

    celdas = sorted(set(modis) | set(viirs))

    for celda in celdas:
        m = modis.get(celda, {})
        v = viirs.get(celda, {})

        mt = m.get("total", 0)
        mu = m.get("utiles", 0)
        mf = m.get("fuego", 0)

        vt = v.get("total", 0)
        vu = v.get("utiles", 0)
        vf = v.get("fuego", 0)
        vr = v.get("reflejo_solar", 0)

        mp = porcentaje(mu, mt)
        vp = porcentaje(vu, vt)

        # Ambos sensores tienen al menos un pixel
        # clasificado como util en la misma celda.
        observacion_ambos = mu > 0 and vu > 0

        # Porcentajes basados en centros de pixel,
        # NO en la superficie del hexagono.
        supera_umbral = (
            mt > 0
            and vt > 0
            and mp >= UMBRAL_UTIL
            and vp >= UMBRAL_UTIL
        )

        registros.append({
            "fecha": fecha,
            "modis_sobrevuelo": config["modis"],
            "viirs_sobrevuelo": config["viirs"],
            "celda_h3": celda,
            "resolucion_h3": RESOLUCION_H3,

            # MODIS
            "modis_pixeles": mt,
            "modis_utiles": mu,
            "modis_nubes": m.get("nube", 0),
            "modis_otros": m.get("otros", 0),
            "modis_fuego": mf,
            "modis_util_pct": mp,

            # VIIRS
            "viirs_pixeles": vt,
            "viirs_utiles": vu,
            "viirs_nubes": v.get("nube", 0),
            "viirs_reflejo_solar": vr,
            "viirs_reflejo_solar_pct": porcentaje(vr, vt),
            "viirs_otros": v.get("otros", 0),
            "viirs_fuego": vf,
            "viirs_util_pct": vp,

            # Comparacion espacial preliminar
            "observacion_util_ambos": observacion_ambos,

            "fuego_ambos": mf > 0 and vf > 0,

            # Deteccion exclusiva en la misma celda,
            # sin exigir cobertura valida del otro sensor.
            "deteccion_solo_modis": mf > 0 and vf == 0,
            "deteccion_solo_viirs": vf > 0 and mf == 0,

            # Discrepancias candidatas:
            # ambos tienen alguna observacion util.
            # Aun NO son discrepancias validadas.
            "fuego_solo_modis": (
                mf > 0
                and vf == 0
                and observacion_ambos
            ),

            "fuego_solo_viirs": (
                vf > 0
                and mf == 0
                and observacion_ambos
            ),

            "supera_umbral_exploratorio": supera_umbral,
        })

    columnas = [
        "fecha",
        "modis_sobrevuelo",
        "viirs_sobrevuelo",
        "celda_h3",
        "resolucion_h3",
        "modis_pixeles",
        "modis_utiles",
        "modis_nubes",
        "modis_otros",
        "modis_fuego",
        "modis_util_pct",
        "viirs_pixeles",
        "viirs_utiles",
        "viirs_nubes",
        "viirs_reflejo_solar",
        "viirs_reflejo_solar_pct",
        "viirs_otros",
        "viirs_fuego",
        "viirs_util_pct",
        "observacion_util_ambos",
        "fuego_ambos",
        "deteccion_solo_modis",
        "deteccion_solo_viirs",
        "fuego_solo_modis",
        "fuego_solo_viirs",
        "supera_umbral_exploratorio",
    ]

    return pd.DataFrame(registros, columns=columnas)


# ==================================================
# RESUMEN DE RESULTADOS
# ==================================================

def mostrar_resumen(df, fecha):
    print("\n" + "=" * 55)
    print(f"RESULTADOS FIRESIGHT - {fecha}")
    print("=" * 55)

    print(f"Celdas H3 analizadas: {len(df)}")

    if df.empty:
        print("No se encontraron pixeles en la region.")
        return

    indicadores = {
        "Celdas con observacion util de ambos":
            "observacion_util_ambos",

        "Celdas con fuego en ambos":
            "fuego_ambos",

        "Deteccion solo MODIS (sin validar)":
            "deteccion_solo_modis",

        "Deteccion solo VIIRS (sin validar)":
            "deteccion_solo_viirs",

        "Discrepancias candidatas MODIS":
            "fuego_solo_modis",

        "Discrepancias candidatas VIIRS":
            "fuego_solo_viirs",

        "Celdas con umbral exploratorio":
            "supera_umbral_exploratorio",
    }

    for etiqueta, columna in indicadores.items():
        print(f"{etiqueta}: {int(df[columna].sum())}")

    print("\nTOTALES MODIS")

    for campo in (
        "modis_pixeles",
        "modis_utiles",
        "modis_fuego",
        "modis_nubes",
        "modis_otros",
    ):
        print(f"{campo}: {int(df[campo].sum()):,}")

    print("\nTOTALES VIIRS")

    for campo in (
        "viirs_pixeles",
        "viirs_utiles",
        "viirs_fuego",
        "viirs_nubes",
        "viirs_reflejo_solar",
        "viirs_otros",
    ):
        print(f"{campo}: {int(df[campo].sum()):,}")

    total_viirs = int(df["viirs_pixeles"].sum())
    reflejo_viirs = int(df["viirs_reflejo_solar"].sum())

    print(
        "\nPorcentaje global VIIRS con reflejo solar:",
        f"{porcentaje(reflejo_viirs, total_viirs):.2f}%",
    )

    # Verificacion interna de consistencia.
    for sensor in ("modis", "viirs"):
        total = int(df[f"{sensor}_pixeles"].sum())

        categorias = (
            int(df[f"{sensor}_utiles"].sum())
            + int(df[f"{sensor}_nubes"].sum())
            + int(df[f"{sensor}_otros"].sum())
        )

        if sensor == "viirs":
            categorias += reflejo_viirs

        if total != categorias:
            raise RuntimeError(
                f"Conteos inconsistentes en {sensor}: "
                f"total={total}, categorias={categorias}"
            )

    print("\nVerificacion de conteos: CORRECTA")


# ==================================================
# EJECUCION
# ==================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "FireSight - Analisis experimental de "
            "observaciones MODIS y VIIRS mediante H3"
        )
    )

    parser.add_argument(
        "--fecha",
        default=FECHA_PREDETERMINADA,
        choices=sorted(CONFIGURACIONES),
        help="Fecha de observacion a procesar.",
    )

    args = parser.parse_args()

    fecha = args.fecha
    config = CONFIGURACIONES[fecha]
    carpeta = config["carpeta"]

    print("=" * 55)
    print("FIRESIGHT - ANALISIS DE CALIDAD POR CELDA")
    print(f"Fecha: {fecha}")
    print("Region: Michoacan, Mexico")
    print(f"Resolucion H3: {RESOLUCION_H3}")
    print(f"Directorio: {carpeta}")
    print("=" * 55)

    modis = procesar_modis(
        carpeta,
        config["modis"],
    )

    viirs = procesar_viirs(
        carpeta,
        config["viirs"],
    )

    df = generar_tabla(
        modis,
        viirs,
        fecha,
        config,
    )

    mostrar_resumen(df, fecha)

    salida = BASE / f"analisis_celdas_{fecha}.csv"

    df.to_csv(
        salida,
        index=False,
        encoding="utf-8-sig",
    )

    print("\nArchivo CSV generado:")
    print(salida)

    print("\nANALISIS FINALIZADO")
    print(
        "\nAVISO: Los indicadores utilizan centros "
        "de pixel. No representan cobertura real "
        "de superficie ni equivalencia validada "
        "entre los sensores."
    )


if __name__ == "__main__":
    main()
