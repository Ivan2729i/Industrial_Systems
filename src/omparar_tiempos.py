
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h3
import h5py
import numpy as np
import pandas as pd
from pyhdf.SD import SD, SDC

from analizar_celdas import CONFIGURACIONES
from regiones import REGIONES, obtener_region, RESOLUCION_H3


# ==================================================
# FIRESIGHT - COMPARACION TEMPORAL MODIS / VIIRS
# ==================================================

BASE = Path(__file__).resolve().parent
DIRECTORIO_RESULTADOS = BASE / "resultados_lotes"

FECHA_PREDETERMINADA = "2024-04-06-noche"
REGION_PREDETERMINADA = "michoacan_piloto"

# Conversion utilizada para los productos de 2024.
# Debe revisarse para otros periodos historicos.
LEAP_SECONDS_1993_2024 = 10

EPOCA_TAI93 = datetime(
    1993, 1, 1, tzinfo=timezone.utc
)


# ==================================================
# CONFIGURACION
# ==================================================

def configurar_argumentos():
    parser = argparse.ArgumentParser(
        description=(
            "FireSight - Comparacion temporal "
            "MODIS-VIIRS por celda H3"
        )
    )

    parser.add_argument(
        "--fecha",
        default=FECHA_PREDETERMINADA,
        choices=sorted(CONFIGURACIONES),
        help="Fecha o pareja de sobrevuelos.",
    )

    parser.add_argument(
        "--region",
        default=REGION_PREDETERMINADA,
        choices=sorted(REGIONES),
        help="Region geografica a analizar.",
    )

    return parser.parse_args()


def obtener_ruta_salida(fecha, region_id, config):
    """
    Conserva los nombres anteriores del piloto
    de Michoacan y utiliza nombres independientes
    para las nuevas regiones.
    """

    hora_modis = config["modis"].split(".")[1]
    hora_viirs = config["viirs"].split(".")[1]

    if region_id == REGION_PREDETERMINADA:
        if fecha == "2024-04-06-noche":
            nombre = "tiempos_2024-04-06_noche.csv"
        else:
            nombre = (
                f"tiempos_{fecha}_"
                f"{hora_modis}_{hora_viirs}.csv"
            )
    else:
        nombre = f"tiempos_{fecha}_{region_id}.csv"

    return DIRECTORIO_RESULTADOS / nombre


# ==================================================
# LOCALIZACION DE ARCHIVOS
# ==================================================

def encontrar(carpeta, prefijo, extension):
    carpeta = Path(carpeta)

    if not carpeta.is_dir():
        raise FileNotFoundError(
            f"No existe el directorio: {carpeta}"
        )

    archivos = sorted(
        archivo
        for archivo in carpeta.glob(f"{prefijo}*")
        if (
            archivo.is_file()
            and archivo.suffix.lower() == extension
        )
    )

    if len(archivos) != 1:
        raise RuntimeError(
            f"Prefijo: {prefijo}\n"
            f"Directorio: {carpeta}\n"
            f"Archivos encontrados: {len(archivos)}"
        )

    return archivos[0]


# ==================================================
# CONVERSION DE TIEMPOS
# ==================================================

def convertir_utc(tai93):
    """
    Convierte los tiempos TAI93 utilizados
    en los archivos del experimento de 2024.
    """

    return EPOCA_TAI93 + timedelta(
        seconds=(
            float(tai93)
            - LEAP_SECONDS_1993_2024
        )
    )


def formato_utc(tai93):
    return (
        convertir_utc(tai93)
        .strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        + " UTC"
    )


# ==================================================
# REGISTROS POR CELDA H3
# ==================================================

def crear_registros():
    return defaultdict(
        lambda: {
            "tiempos": set(),
            "pixeles_utiles": 0,
            "fuego": 0,
        }
    )


def registrar(
    registros,
    lat,
    lon,
    mascara,
    tiempo,
    region,
):
    """
    Registra pixeles utiles dentro de la region.

    Se utiliza el tiempo central del escaneo,
    no un tiempo individual por pixel.
    """

    if not (
        lat.shape == lon.shape == mascara.shape
    ):
        raise ValueError(
            "Dimensiones incompatibles entre "
            "latitud, longitud y mascara."
        )

    dentro = (
        np.isfinite(lat)
        & np.isfinite(lon)
        & (lat >= region["sur"])
        & (lat <= region["norte"])
        & (lon >= region["oeste"])
        & (lon <= region["este"])
    )

    utiles = np.isin(
        mascara,
        (5, 7, 8, 9),
    )

    filas, columnas = np.where(
        dentro & utiles
    )

    for fila, columna in zip(filas, columnas):
        latitud = float(lat[fila, columna])
        longitud = float(lon[fila, columna])
        clase = int(mascara[fila, columna])

        celda = h3.latlng_to_cell(
            latitud,
            longitud,
            RESOLUCION_H3,
        )

        registro = registros[celda]

        registro["tiempos"].add(
            float(tiempo)
        )

        registro["pixeles_utiles"] += 1

        if clase in (7, 8, 9):
            registro["fuego"] += 1


# ==================================================
# MODIS AQUA
# ==================================================

def procesar_modis(carpeta, modis_id, region):
    ruta_geo = encontrar(
        carpeta,
        f"MYD03.{modis_id}.061.",
        ".hdf",
    )

    ruta_fire = encontrar(
        carpeta,
        f"MYD14.{modis_id}.061.",
        ".hdf",
    )

    registros = crear_registros()

    geo = SD(str(ruta_geo), SDC.READ)
    fire = None

    try:
        fire = SD(
            str(ruta_fire),
            SDC.READ,
        )

        lat_ds = geo.select("Latitude")
        lon_ds = geo.select("Longitude")
        mask_ds = fire.select("fire mask")

        tiempos = np.asarray(
            geo.select("EV center time").get(),
            dtype=float,
        ).ravel()

        forma_lat = tuple(lat_ds.info()[2])
        forma_lon = tuple(lon_ds.info()[2])
        forma_mask = tuple(mask_ds.info()[2])

        if not (
            forma_lat == forma_lon == forma_mask
        ):
            raise ValueError(
                "Dimensiones MODIS incompatibles: "
                f"{forma_lat}, {forma_lon}, "
                f"{forma_mask}"
            )

        filas, columnas = forma_mask

        if (
            len(tiempos) == 0
            or filas % len(tiempos) != 0
        ):
            raise ValueError(
                "No se pudo relacionar el tiempo "
                "con las filas MODIS."
            )

        filas_por_escaneo = (
            filas // len(tiempos)
        )

        if filas_por_escaneo != 10:
            raise ValueError(
                "Se esperaban 10 filas por "
                "escaneo MODIS."
            )

        print(
            f"MODIS: {len(tiempos)} escaneos, "
            f"{filas_por_escaneo} filas por escaneo"
        )

        for indice, tiempo in enumerate(tiempos):
            if (
                not np.isfinite(tiempo)
                or tiempo < 0
            ):
                continue

            inicio = indice * filas_por_escaneo

            posicion = (inicio, 0)

            dimensiones = (
                filas_por_escaneo,
                columnas,
            )

            lat = lat_ds.get(
                start=posicion,
                count=dimensiones,
            )

            lon = lon_ds.get(
                start=posicion,
                count=dimensiones,
            )

            mascara = mask_ds.get(
                start=posicion,
                count=dimensiones,
            )

            # MODIS: los cuatro bits inferiores
            # contienen la clase de fire mask.
            mascara = np.bitwise_and(
                mascara,
                15,
            )

            registrar(
                registros=registros,
                lat=lat,
                lon=lon,
                mascara=mascara,
                tiempo=tiempo,
                region=region,
            )

    finally:
        if fire is not None:
            fire.end()

        geo.end()

    return registros


# ==================================================
# VIIRS S-NPP
# ==================================================

def procesar_viirs(carpeta, viirs_id, region):
    ruta_geo = encontrar(
        carpeta,
        f"VNP03IMG.{viirs_id}.002.",
        ".nc",
    )

    ruta_fire = encontrar(
        carpeta,
        f"VNP14IMG.{viirs_id}.002.",
        ".nc",
    )

    registros = crear_registros()

    with (
        h5py.File(ruta_geo, "r") as geo,
        h5py.File(ruta_fire, "r") as fire,
    ):
        lat_ds = geo[
            "geolocation_data/latitude"
        ]

        lon_ds = geo[
            "geolocation_data/longitude"
        ]

        mask_ds = fire["fire mask"]

        tiempos = np.asarray(
            geo[
                "scan_line_attributes/ev_mid_time"
            ][:],
            dtype=float,
        ).ravel()

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

        if (
            len(tiempos) == 0
            or filas % len(tiempos) != 0
        ):
            raise ValueError(
                "No se pudo relacionar el tiempo "
                "con las filas VIIRS."
            )

        filas_por_escaneo = (
            filas // len(tiempos)
        )

        if filas_por_escaneo != 32:
            raise ValueError(
                "Se esperaban 32 filas por "
                "escaneo VIIRS."
            )

        print(
            f"VIIRS: {len(tiempos)} escaneos, "
            f"{filas_por_escaneo} filas por escaneo"
        )

        for indice, tiempo in enumerate(tiempos):
            if (
                not np.isfinite(tiempo)
                or tiempo < 0
            ):
                continue

            inicio = indice * filas_por_escaneo
            fin = inicio + filas_por_escaneo

            registrar(
                registros=registros,
                lat=lat_ds[inicio:fin, :],
                lon=lon_ds[inicio:fin, :],
                mascara=mask_ds[inicio:fin, :],
                tiempo=tiempo,
                region=region,
            )

    return registros


# ==================================================
# COMPARACION TEMPORAL
# ==================================================

def tiempo_cercano(modis, viirs):
    """
    Devuelve el par de tiempos de escaneo
    con menor diferencia absoluta.
    """

    if not modis or not viirs:
        raise ValueError(
            "No hay tiempos suficientes "
            "para realizar la comparacion."
        )

    return min(
        (
            (abs(m - v), m, v)
            for m in modis
            for v in viirs
        ),
        key=lambda resultado: resultado[0],
    )


def generar_tabla(
    registros_modis,
    registros_viirs,
    fecha,
    region_id,
    config,
):
    comunes = sorted(
        set(registros_modis)
        & set(registros_viirs)
    )

    registros = []

    for celda in comunes:
        m = registros_modis[celda]
        v = registros_viirs[celda]

        tiempos_m = sorted(m["tiempos"])
        tiempos_v = sorted(v["tiempos"])

        (
            diferencia_seg,
            tiempo_modis,
            tiempo_viirs,
        ) = tiempo_cercano(
            tiempos_m,
            tiempos_v,
        )

        registros.append({
            "fecha": fecha,
            "region_id": region_id,
            "modis_sobrevuelo": config["modis"],
            "viirs_sobrevuelo": config["viirs"],
            "celda_h3": celda,
            "resolucion_h3": RESOLUCION_H3,

            "modis_utc": formato_utc(
                tiempo_modis
            ),

            "viirs_utc": formato_utc(
                tiempo_viirs
            ),

            "diferencia_min": round(
                diferencia_seg / 60,
                3,
            ),

            "modis_pixeles_utiles":
                m["pixeles_utiles"],

            "viirs_pixeles_utiles":
                v["pixeles_utiles"],

            "modis_fuego": m["fuego"],
            "viirs_fuego": v["fuego"],
        })

    columnas = [
        "fecha",
        "region_id",
        "modis_sobrevuelo",
        "viirs_sobrevuelo",
        "celda_h3",
        "resolucion_h3",
        "modis_utc",
        "viirs_utc",
        "diferencia_min",
        "modis_pixeles_utiles",
        "viirs_pixeles_utiles",
        "modis_fuego",
        "viirs_fuego",
    ]

    df = pd.DataFrame(
        registros,
        columns=columnas,
    )

    clave = [
        "region_id",
        "modis_sobrevuelo",
        "viirs_sobrevuelo",
        "celda_h3",
    ]

    if df.duplicated(clave).any():
        raise RuntimeError(
            "Se encontraron registros "
            "temporales H3 duplicados."
        )

    return df


# ==================================================
# RESUMEN
# ==================================================

def mostrar_resumen(df):
    if df.empty:
        print(
            "\nNo se encontraron celdas con "
            "observaciones utiles de ambos sensores."
        )
        return

    print("\nDIFERENCIAS TEMPORALES")

    print(
        "Minima:",
        round(
            df["diferencia_min"].min(),
            3,
        ),
        "min",
    )

    print(
        "Mediana:",
        round(
            df["diferencia_min"].median(),
            3,
        ),
        "min",
    )

    print(
        "Maxima:",
        round(
            df["diferencia_min"].max(),
            3,
        ),
        "min",
    )

    print("\nCELDAS CON DETECCIONES DE FUEGO")

    focos = df[
        (df["modis_fuego"] > 0)
        | (df["viirs_fuego"] > 0)
    ]

    if focos.empty:
        print(
            "No se encontraron celdas "
            "con detecciones de fuego."
        )
    else:
        columnas = [
            "celda_h3",
            "modis_utc",
            "viirs_utc",
            "diferencia_min",
            "modis_fuego",
            "viirs_fuego",
        ]

        print(
            focos[columnas].to_string(
                index=False
            )
        )

    # Estratos temporales experimentales.
    estricto = df["diferencia_min"].le(5)

    exploratorio = (
        df["diferencia_min"].gt(5)
        & df["diferencia_min"].le(15)
    )

    print("\nESTRATOS TEMPORALES")

    print(
        "0 a 5 minutos:",
        int(estricto.sum()),
    )

    print(
        "Mas de 5 hasta 15 minutos:",
        int(exploratorio.sum()),
    )

    print(
        "Mas de 15 minutos:",
        int(
            df["diferencia_min"].gt(15).sum()
        ),
    )

    print(
        "\nEstos estratos son experimentales. "
        "No determinan por si solos la "
        "comparabilidad cientifica."
    )


# ==================================================
# EJECUCION PRINCIPAL
# ==================================================

def main():
    args = configurar_argumentos()

    fecha = args.fecha
    region_id = args.region

    config = CONFIGURACIONES[fecha]
    region = obtener_region(region_id)

    carpeta = Path(config["carpeta"])

    salida = obtener_ruta_salida(
        fecha,
        region_id,
        config,
    )

    print("FIRESIGHT - COMPARACION TEMPORAL")
    print(f"Fecha: {fecha}")
    print(f"Region: {region['nombre']}")
    print(f"Identificador: {region_id}")

    print(
        "BBox (O, S, E, N): "
        f"{region['oeste']}, "
        f"{region['sur']}, "
        f"{region['este']}, "
        f"{region['norte']}"
    )

    print(f"MODIS: {config['modis']}")
    print(f"VIIRS: {config['viirs']}")
    print("=" * 55)

    modis = procesar_modis(
        carpeta,
        config["modis"],
        region,
    )

    viirs = procesar_viirs(
        carpeta,
        config["viirs"],
        region,
    )

    comunes = set(modis) & set(viirs)

    print(
        f"\nCeldas utiles MODIS: {len(modis)}"
    )

    print(
        f"Celdas utiles VIIRS: {len(viirs)}"
    )

    print(
        "Celdas con tiempos de ambos:",
        len(comunes),
    )

    df = generar_tabla(
        registros_modis=modis,
        registros_viirs=viirs,
        fecha=fecha,
        region_id=region_id,
        config=config,
    )

    mostrar_resumen(df)

    DIRECTORIO_RESULTADOS.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        salida,
        index=False,
        encoding="utf-8-sig",
    )

    print("\nCSV generado:", salida)
    print("\nCOMPARACION FINALIZADA")

    print(
        "\nNOTA: Se comparan tiempos centrales "
        "de escaneos con pixeles utiles en "
        "una misma celda H3. No son tiempos "
        "individuales exactos de cada pixel."
    )


if __name__ == "__main__":
    main()
