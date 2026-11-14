
import argparse
from collections import defaultdict
from pathlib import Path

import h3
import h5py
import numpy as np
import pandas as pd
from pyhdf.SD import SD, SDC

from regiones import REGIONES, obtener_region


# ==================================================
# FIRESIGHT - ANALISIS DE OBSERVACIONES MODIS / VIIRS
# ==================================================

BASE = Path(__file__).resolve().parent
DIRECTORIO_RESULTADOS = BASE / "resultados_lotes"

RESOLUCION_H3 = 7
BLOQUE_FILAS = 32

# Umbral experimental basado en cantidad de centros
# de pixeles utiles, NO en cobertura geografica real.
UMBRAL_UTIL = 80.0

FECHA_PREDETERMINADA = "2024-04-08"
REGION_PREDETERMINADA = "michoacan_piloto"


# ==================================================
# CONFIGURACION DE SOBREVUELOS
# ==================================================

CONFIGURACIONES = {
    "2024-04-06": {
        "carpeta": BASE / "datos" / "level2",
        "modis": "A2024097.2020",
        "viirs": "A2024097.2030",
    },

    "2024-04-06-noche": {
        "carpeta": (
            BASE / "datos" / "lotes" / "2024-04-06-noche"
        ),
        "modis": "A2024097.0925",
        "viirs": "A2024097.0918",
    },

    "2024-04-08": {
        "carpeta": BASE / "datos" / "lotes" / "2024-04-08",
        "modis": "A2024099.2000",
        "viirs": "A2024099.1954",
    },

    "2024-04-16": {
        "carpeta": BASE / "datos" / "lotes" / "2024-04-16",
        "modis": "A2024107.2035",
        "viirs": "A2024107.2042",
    },

    "2024-04-19": {
        "carpeta": BASE / "datos" / "lotes" / "2024-04-19",
        "modis": "A2024110.0830",
        "viirs": "A2024110.0836",
    },
}


# ==================================================
# REGIONES
# ==================================================

def resolver_region(region=None):
    """
    Devuelve la region recibida o la region
    predeterminada para mantener compatibilidad
    con llamadas anteriores.
    """
    if region is None:
        return obtener_region(REGION_PREDETERMINADA)

    return region


# ==================================================
# LOCALIZACION DE ARCHIVOS
# ==================================================

def encontrar_archivo(carpeta, prefijo):
    carpeta = Path(carpeta)

    if not carpeta.is_dir():
        raise FileNotFoundError(
            f"No existe el directorio: {carpeta}"
        )

    encontrados = sorted(
        archivo
        for archivo in carpeta.glob(f"{prefijo}*")
        if archivo.is_file()
    )

    if len(encontrados) != 1:
        raise RuntimeError(
            f"Se esperaba exactamente un archivo "
            f"con prefijo '{prefijo}' en {carpeta}. "
            f"Encontrados: {len(encontrados)}"
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
    region=None,
):
    """
    Agrupa los centros de pixeles en celdas H3
    dentro de una region configurable.

    No calcula huellas reales de los pixeles.
    """

    region = resolver_region(region)

    if not (
        latitudes.shape
        == longitudes.shape
        == mascara.shape
    ):
        raise ValueError(
            "Las dimensiones de latitud, longitud "
            "y mascara no coinciden."
        )

    # MODIS almacena la clase de fuego
    # en los cuatro bits inferiores.
    if es_modis:
        clases = np.bitwise_and(mascara, 15)
    else:
        clases = mascara

    # Filtrado geografico configurable.
    dentro = (
        np.isfinite(latitudes)
        & np.isfinite(longitudes)
        & (latitudes >= region["sur"])
        & (latitudes <= region["norte"])
        & (longitudes >= region["oeste"])
        & (longitudes <= region["este"])
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

        # Clases consideradas utiles
        # en la metodologia experimental.
        if clase in (5, 7, 8, 9):
            registro["utiles"] += 1

        # Pixeles con deteccion de fuego.
        if clase in (7, 8, 9):
            registro["fuego"] += 1

        # Categorias excluyentes de calidad.
        if clase == 4:
            registro["nube"] += 1

        elif not es_modis and clase == 2:
            registro["reflejo_solar"] += 1

        elif clase not in (5, 7, 8, 9):
            registro["otros"] += 1


# ==================================================
# PROCESAMIENTO MODIS AQUA
# ==================================================

def procesar_modis(carpeta, fecha_hora, region=None):
    region = resolver_region(region)

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

            posicion = (inicio, 0)
            dimensiones = (cantidad, columnas)

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

            agregar_pixeles(
                resultados=resultados,
                latitudes=lat,
                longitudes=lon,
                mascara=mascara,
                es_modis=True,
                region=region,
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
# PROCESAMIENTO VIIRS S-NPP
# ==================================================

def procesar_viirs(carpeta, fecha_hora, region=None):
    region = resolver_region(region)

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

            lat = lat_ds[inicio:fin, :]
            lon = lon_ds[inicio:fin, :]
            mascara = mask_ds[inicio:fin, :]

            agregar_pixeles(
                resultados=resultados,
                latitudes=lat,
                longitudes=lon,
                mascara=mascara,
                es_modis=False,
                region=region,
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

    return round(
        100.0 * parte / total,
        2,
    )


def generar_tabla(
    modis,
    viirs,
    fecha,
    config,
    region_id=REGION_PREDETERMINADA,
):
    """
    Genera una fila por celda H3 y pareja
    MODIS-VIIRS.

    La region se identifica explicitamente para
    evitar mezclar observaciones de zonas distintas.
    """

    registros = []

    region = obtener_region(region_id)

    celdas = sorted(
        set(modis) | set(viirs)
    )

    for celda in celdas:
        m = modis.get(celda, {})
        v = viirs.get(celda, {})

        # MODIS
        mt = m.get("total", 0)
        mu = m.get("utiles", 0)
        mf = m.get("fuego", 0)

        # VIIRS
        vt = v.get("total", 0)
        vu = v.get("utiles", 0)
        vf = v.get("fuego", 0)
        vr = v.get("reflejo_solar", 0)

        mp = porcentaje(mu, mt)
        vp = porcentaje(vu, vt)

        # Ambos sensores tienen por lo menos
        # una observacion util en esta celda.
        observacion_ambos = (
            mu > 0 and vu > 0
        )

        # Este umbral utiliza porcentajes de
        # centros de pixel, no superficies reales.
        supera_umbral = (
            mt > 0
            and vt > 0
            and mp >= UMBRAL_UTIL
            and vp >= UMBRAL_UTIL
        )

        registros.append({
            # Identificacion
            "fecha": fecha,
            "region_id": region_id,
            "region_nombre": region["nombre"],
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
            "viirs_reflejo_solar_pct": porcentaje(
                vr, vt
            ),
            "viirs_otros": v.get("otros", 0),
            "viirs_fuego": vf,
            "viirs_util_pct": vp,

            # Observacion util compartida
            "observacion_util_ambos": (
                observacion_ambos
            ),

            # Presencia de fuego
            "fuego_ambos": (
                mf > 0 and vf > 0
            ),

            # Detecciones exclusivas sin validar
            "deteccion_solo_modis": (
                mf > 0 and vf == 0
            ),

            "deteccion_solo_viirs": (
                vf > 0 and mf == 0
            ),

            # Discrepancias candidatas
            # con observacion util compartida
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

            "supera_umbral_exploratorio": (
                supera_umbral
            ),
        })

    columnas = [
        "fecha",
        "region_id",
        "region_nombre",
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

    df = pd.DataFrame(
        registros,
        columns=columnas,
    )

    # Una observacion no puede aparecer
    # dos veces en la misma celda y sobrevuelo.
    clave = [
        "region_id",
        "modis_sobrevuelo",
        "viirs_sobrevuelo",
        "celda_h3",
    ]

    if df.duplicated(clave).any():
        raise RuntimeError(
            "Se encontraron observaciones H3 duplicadas."
        )

    return df


# ==================================================
# RESUMEN Y VALIDACIONES
# ==================================================

def mostrar_resumen(
    df,
    fecha,
    region_nombre=None,
):
    print("\n" + "=" * 55)
    print(f"RESULTADOS FIRESIGHT - {fecha}")

    if region_nombre:
        print(f"Region: {region_nombre}")

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
        print(
            f"{etiqueta}: "
            f"{int(df[columna].sum())}"
        )

    print("\nTOTALES MODIS")

    for campo in (
        "modis_pixeles",
        "modis_utiles",
        "modis_fuego",
        "modis_nubes",
        "modis_otros",
    ):
        print(
            f"{campo}: {int(df[campo].sum()):,}"
        )

    print("\nTOTALES VIIRS")

    for campo in (
        "viirs_pixeles",
        "viirs_utiles",
        "viirs_fuego",
        "viirs_nubes",
        "viirs_reflejo_solar",
        "viirs_otros",
    ):
        print(
            f"{campo}: {int(df[campo].sum()):,}"
        )

    total_viirs = int(
        df["viirs_pixeles"].sum()
    )

    reflejo_viirs = int(
        df["viirs_reflejo_solar"].sum()
    )

    print(
        "\nPorcentaje global VIIRS con reflejo solar:",
        f"{porcentaje(reflejo_viirs, total_viirs):.2f}%",
    )

    # Comprobar que todos los pixeles
    # pertenecen exactamente a una categoria.
    for sensor in ("modis", "viirs"):
        total = int(
            df[f"{sensor}_pixeles"].sum()
        )

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
                f"total={total}, "
                f"categorias={categorias}"
            )

    print("\nVerificacion de conteos: CORRECTA")


# ==================================================
# EJECUCION PRINCIPAL
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
        help="Fecha y pareja de sobrevuelos a procesar.",
    )

    parser.add_argument(
        "--region",
        default=REGION_PREDETERMINADA,
        choices=sorted(REGIONES),
        help="Region geografica a procesar.",
    )

    args = parser.parse_args()

    fecha = args.fecha
    region_id = args.region

    config = CONFIGURACIONES[fecha]
    region = obtener_region(region_id)

    carpeta = config["carpeta"]

    print("=" * 55)
    print("FIRESIGHT - ANALISIS DE CALIDAD POR CELDA")
    print(f"Fecha: {fecha}")
    print(f"Region: {region['nombre']}")
    print(f"Identificador: {region_id}")
    print(f"Resolucion H3: {RESOLUCION_H3}")

    print(
        "BBox (O, S, E, N): "
        f"{region['oeste']}, "
        f"{region['sur']}, "
        f"{region['este']}, "
        f"{region['norte']}"
    )

    print(f"MODIS: {config['modis']}")
    print(f"VIIRS: {config['viirs']}")
    print(f"Directorio: {carpeta}")
    print("=" * 55)

    # Procesar ambos instrumentos usando
    # la misma region geografica.
    modis = procesar_modis(
        carpeta,
        config["modis"],
        region=region,
    )

    viirs = procesar_viirs(
        carpeta,
        config["viirs"],
        region=region,
    )

    # Generar la tabla comun H3.
    df = generar_tabla(
        modis,
        viirs,
        fecha,
        config,
        region_id=region_id,
    )

    mostrar_resumen(
        df,
        fecha,
        region_nombre=region["nombre"],
    )

    # Salidas independientes por fecha y region.
    DIRECTORIO_RESULTADOS.mkdir(
        parents=True,
        exist_ok=True,
    )

    salida = (
        DIRECTORIO_RESULTADOS
        / f"analisis_celdas_{fecha}_{region_id}.csv"
    )

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
        "de pixel y una clasificacion experimental "
        "de calidad. No representan cobertura "
        "geografica real ni equivalencia "
        "cientificamente validada entre sensores."
    )


if __name__ == "__main__":
    main()
