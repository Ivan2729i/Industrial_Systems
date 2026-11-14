
from collections import defaultdict
from pathlib import Path

import h3
import h5py
import numpy as np
import pandas as pd

from pyhdf.SD import SD, SDC
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, GeometryCollection
from shapely.ops import unary_union
from shapely.strtree import STRtree
import argparse
from analizar_celdas import CONFIGURACIONES


# ==================================================
# FIRESIGHT - COBERTURA ESPACIAL EXPERIMENTAL
# ==================================================


BASE = Path(__file__).resolve().parent

parser = argparse.ArgumentParser(
    description="FireSight - Cobertura espacial MODIS-VIIRS"
)

parser.add_argument(
    "--fecha",
    default="2024-04-06-noche",
    choices=sorted(CONFIGURACIONES),
)

args = parser.parse_args()

FECHA = args.fecha
CONFIG = CONFIGURACIONES[FECHA]

DATOS = CONFIG["carpeta"]
MODIS_ID = CONFIG["modis"]
VIIRS_ID = CONFIG["viirs"]

HORA_MODIS = MODIS_ID.split(".")[1]
HORA_VIIRS = VIIRS_ID.split(".")[1]

IDENTIFICADOR = (
    f"{FECHA[:10]}_{HORA_MODIS}_{HORA_VIIRS}"
)

SALIDA = (
    BASE / "resultados_lotes"
    / f"cobertura_{IDENTIFICADOR}.csv"
)

ANALISIS_PREVIO = (
    BASE / f"analisis_celdas_{FECHA}.csv"
)


SUR, NORTE = 19.35, 19.60
OESTE, ESTE = -102.15, -101.80

RESOLUCION_H3 = 7
BLOQUE_FILAS = 32

# Incluye centros cercanos al rectangulo cuya huella
# podria intersectar la region.
MARGEN_GRADOS = 0.08

# Limites de seguridad geometricos exploratorios.
# No representan especificaciones oficiales NASA.
LIMITES = {
    "MODIS": {
        "paso_max_m": 8000,
        "area_max_m2": 50_000_000,
    },
    "VIIRS": {
        "paso_max_m": 3000,
        "area_max_m2": 7_000_000,
    },
}


# ==================================================
# PROYECCION DE IGUAL AREA LOCAL
# ==================================================

LAT_CENTRO = (SUR + NORTE) / 2
LON_CENTRO = (OESTE + ESTE) / 2

CRS_LOCAL = CRS.from_proj4(
    f"+proj=laea "
    f"+lat_0={LAT_CENTRO} "
    f"+lon_0={LON_CENTRO} "
    f"+datum=WGS84 +units=m +no_defs"
)

PROYECTOR = Transformer.from_crs(
    "EPSG:4326",
    CRS_LOCAL,
    always_xy=True,
)


def poligono_proyectado(coordenadas):
    longitudes = [p[0] for p in coordenadas]
    latitudes = [p[1] for p in coordenadas]

    x, y = PROYECTOR.transform(
        longitudes, latitudes
    )

    return Polygon(zip(x, y))


REGION = poligono_proyectado([
    (OESTE, SUR),
    (ESTE, SUR),
    (ESTE, NORTE),
    (OESTE, NORTE),
])


# ==================================================
# LOCALIZACION DE ARCHIVOS
# ==================================================

def encontrar(prefijo):
    archivos = sorted(DATOS.glob(f"{prefijo}*"))

    if len(archivos) != 1:
        raise FileNotFoundError(
            f"Se esperaba un archivo con prefijo "
            f"{prefijo}. Encontrados: {len(archivos)}"
        )

    return archivos[0]


# ==================================================
# HEXAGONOS H3 INTERSECTADOS POR LA REGION
# ==================================================

def preparar_hexagonos():
    poligono_h3 = h3.LatLngPoly([
        (SUR, OESTE),
        (SUR, ESTE),
        (NORTE, ESTE),
        (NORTE, OESTE),
    ])

    interiores = h3.polygon_to_cells(
        poligono_h3,
        RESOLUCION_H3,
    )

    if not interiores:
        raise RuntimeError(
            "No se encontraron hexagonos H3."
        )

    # H3 selecciona por centro. Incluimos vecinos
    # para conservar hexagonos que cruzan el borde.
    candidatos = set(interiores)

    for celda in interiores:
        candidatos.update(h3.grid_disk(celda, 1))

    ids = []
    geometria = []

    for celda in sorted(candidatos):
        limite = h3.cell_to_boundary(celda)

        poligono = poligono_proyectado([
            (lon, lat) for lat, lon in limite
        ])

        recorte = poligono.intersection(REGION)

        if recorte.area > 1:
            ids.append(celda)
            geometria.append(recorte)

    return ids, geometria, STRtree(geometria)


# ==================================================
# LECTURA EN BLOQUES MODIS
# ==================================================

def bloques_modis():
    ruta_geo = encontrar(f"MYD03.{MODIS_ID}.061.")
    ruta_fire = encontrar(f"MYD14.{MODIS_ID}.061.")

    geo = SD(str(ruta_geo), SDC.READ)
    fire = None

    try:
        fire = SD(str(ruta_fire), SDC.READ)

        lat_ds = geo.select("Latitude")
        lon_ds = geo.select("Longitude")
        mask_ds = fire.select("fire mask")

        forma = tuple(lat_ds.info()[2])

        if not (
            forma == tuple(lon_ds.info()[2])
            == tuple(mask_ds.info()[2])
        ):
            raise ValueError(
                "Dimensiones MODIS incompatibles."
            )

        filas, columnas = forma

        for inicio in range(0, filas, BLOQUE_FILAS):
            fin = min(inicio + BLOQUE_FILAS, filas)

            # Fila adicional a cada lado para
            # estimar la geometria de cada pixel.
            desde = max(0, inicio - 1)
            hasta = min(filas, fin + 1)

            posicion = (desde, 0)
            cantidad = (hasta - desde, columnas)

            lat = lat_ds.get(
                start=posicion, count=cantidad
            )
            lon = lon_ds.get(
                start=posicion, count=cantidad
            )
            mascara = mask_ds.get(
                start=posicion, count=cantidad
            )

            # Extraer los 4 bits de clase MODIS.
            mascara = np.bitwise_and(mascara, 15)

            yield lat, lon, mascara, inicio - desde, fin - inicio

    finally:
        if fire is not None:
            fire.end()
        geo.end()


# ==================================================
# LECTURA EN BLOQUES VIIRS
# ==================================================

def bloques_viirs():
    ruta_geo = encontrar(f"VNP03IMG.{VIIRS_ID}.002.")
    ruta_fire = encontrar(f"VNP14IMG.{VIIRS_ID}.002.")

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
                "Dimensiones VIIRS incompatibles."
            )

        filas, _ = mask_ds.shape

        for inicio in range(0, filas, BLOQUE_FILAS):
            fin = min(inicio + BLOQUE_FILAS, filas)

            desde = max(0, inicio - 1)
            hasta = min(filas, fin + 1)

            yield (
                lat_ds[desde:hasta, :],
                lon_ds[desde:hasta, :],
                mask_ds[desde:hasta, :],
                inicio - desde,
                fin - inicio,
            )


# ==================================================
# VALIDACION DE COORDENADAS
# ==================================================

def coordenadas_validas(lat, lon):
    return (
        np.isfinite(lat)
        & np.isfinite(lon)
        & (lat >= -90)
        & (lat <= 90)
        & (lon >= -180)
        & (lon <= 180)
    )


# ==================================================
# RECONSTRUCCION APROXIMADA DE HUELLAS
# ==================================================

def acumular_huellas(sensor, bloques, ids, geometrias, indice):
    fragmentos = defaultdict(list)

    estadisticas = {
        "centros_candidatos": 0,
        "geometria_descartada": 0,
        "huellas_en_region": 0,
    }

    max_paso = LIMITES[sensor]["paso_max_m"]
    max_area = LIMITES[sensor]["area_max_m2"]

    for indice_bloque, (
            lat, lon, mascara, offset, n_core
    ) in enumerate(bloques):
        inicio_global = indice_bloque * BLOQUE_FILAS
        lat_core = lat[offset:offset + n_core]
        lon_core = lon[offset:offset + n_core]
        mask_core = mascara[offset:offset + n_core]

        # Solo las clases utiles para este experimento.
        util = np.isin(mask_core, [5, 7, 8, 9])

        # Preseleccion geografica ampliada.
        cerca = (
            coordenadas_validas(lat_core, lon_core)
            & (lat_core >= SUR - MARGEN_GRADOS)
            & (lat_core <= NORTE + MARGEN_GRADOS)
            & (lon_core >= OESTE - MARGEN_GRADOS)
            & (lon_core <= ESTE + MARGEN_GRADOS)
        )

        filas, columnas = np.where(util & cerca)

        if len(filas) == 0:
            continue

        estadisticas["centros_candidatos"] += len(filas)

        # Posicion dentro del bloque con filas de apoyo.

        r = filas + offset
        c = columnas

        # Numero global de fila en el archivo NASA.
        filas_globales = inicio_global + filas

        # Cada instrumento tiene una cantidad distinta
        # de detectores por escaneo.
        filas_por_escaneo = (
            10 if sensor == "MODIS" else 32
        )

        # Limites del escaneo al que pertenece
        # cada pixel.
        primera_fila = (
            filas_globales // filas_por_escaneo
        ) * filas_por_escaneo

        ultima_fila = (
            primera_fila + filas_por_escaneo - 1
        )

        # Los vecinos verticales deben pertenecer
        # al MISMO escaneo del pixel central.
        #
        # En sus bordes usamos una diferencia
        # unilateral en vez de cruzar al siguiente.
        arriba = r - (
            filas_globales > primera_fila
        ).astype(np.int64)

        abajo = r + (
            filas_globales < ultima_fila
        ).astype(np.int64)

        # Vecinos horizontales dentro de la misma
        # fila del sensor.
        izquierda = np.maximum(c - 1, 0)
        derecha = np.minimum(
            c + 1,
            lat.shape[1] - 1,
        )


        # Coordenadas de centro y vecinos.
        la0, lo0 = lat[r, c], lon[r, c]
        lai, loi = lat[r, izquierda], lon[r, izquierda]
        lad, lod = lat[r, derecha], lon[r, derecha]
        las, los = lat[arriba, c], lon[arriba, c]
        lab, lob = lat[abajo, c], lon[abajo, c]

        valido = (
            coordenadas_validas(la0, lo0)
            & coordenadas_validas(lai, loi)
            & coordenadas_validas(lad, lod)
            & coordenadas_validas(las, los)
            & coordenadas_validas(lab, lob)
        )

        indices = np.flatnonzero(valido)

        estadisticas["geometria_descartada"] += (
            len(r) - len(indices)
        )

        if len(indices) == 0:
            continue

        # Proyectar todas las coordenadas del bloque.
        x0, y0 = PROYECTOR.transform(
            lo0[indices], la0[indices]
        )
        xi, yi = PROYECTOR.transform(
            loi[indices], lai[indices]
        )
        xd, yd = PROYECTOR.transform(
            lod[indices], lad[indices]
        )
        xs, ys = PROYECTOR.transform(
            los[indices], las[indices]
        )
        xb, yb = PROYECTOR.transform(
            lob[indices], lab[indices]
        )

        pasos_columnas = (
            derecha[indices] - izquierda[indices]
        )
        pasos_filas = abajo[indices] - arriba[indices]

        dx = (xd - xi) / pasos_columnas
        dy = (yd - yi) / pasos_columnas

        ex = (xb - xs) / pasos_filas
        ey = (yb - ys) / pasos_filas

        for i in range(len(indices)):
            paso_horizontal = np.hypot(dx[i], dy[i])
            paso_vertical = np.hypot(ex[i], ey[i])

            if not (
                25 < paso_horizontal < max_paso
                and 25 < paso_vertical < max_paso
            ):
                estadisticas["geometria_descartada"] += 1
                continue

            # Cuadrilatero local estimado a partir de
            # los vectores de separacion entre centros.
            puntos = [
                (
                    x0[i] - dx[i] / 2 - ex[i] / 2,
                    y0[i] - dy[i] / 2 - ey[i] / 2,
                ),
                (
                    x0[i] + dx[i] / 2 - ex[i] / 2,
                    y0[i] + dy[i] / 2 - ey[i] / 2,
                ),
                (
                    x0[i] + dx[i] / 2 + ex[i] / 2,
                    y0[i] + dy[i] / 2 + ey[i] / 2,
                ),
                (
                    x0[i] - dx[i] / 2 + ex[i] / 2,
                    y0[i] - dy[i] / 2 + ey[i] / 2,
                ),
            ]

            huella = Polygon(puntos)

            if (
                not huella.is_valid
                or huella.area < 1000
                or huella.area > max_area
            ):
                estadisticas["geometria_descartada"] += 1
                continue

            if not huella.intersects(REGION):
                continue

            estadisticas["huellas_en_region"] += 1

            # STRtree evita comparar contra todos los
            # hexagonos de la region.
            candidatos = indice.query(
                huella,
                predicate="intersects",
            )

            for posicion in candidatos:
                posicion = int(posicion)

                fragmento = huella.intersection(
                    geometrias[posicion]
                )

                if fragmento.area > 1:
                    fragmentos[ids[posicion]].append(
                        fragmento
                    )

    return fragmentos, estadisticas


# ==================================================
# CALCULAR AREAS POR CELDA
# ==================================================

def combinar(fragmentos):
    if not fragmentos:
        return GeometryCollection()

    return unary_union(fragmentos)


def calcular_cobertura(ids, geometrias, modis, viirs):
    registros = []

    for celda, geometria in zip(ids, geometrias):
        area_region = geometria.area

        huella_modis = combinar(modis.get(celda, []))
        huella_viirs = combinar(viirs.get(celda, []))

        area_modis = huella_modis.area
        area_viirs = huella_viirs.area

        area_comun = huella_modis.intersection(
            huella_viirs
        ).area

        registros.append({
            "celda_h3": celda,
            "area_h3_en_region_m2": round(
                area_region, 2
            ),
            "area_modis_util_m2": round(
                area_modis, 2
            ),
            "area_viirs_util_m2": round(
                area_viirs, 2
            ),
            "area_compartida_m2": round(
                area_comun, 2
            ),
            "cobertura_modis_pct": round(
                100 * area_modis / area_region, 2
            ),
            "cobertura_viirs_pct": round(
                100 * area_viirs / area_region, 2
            ),
            "cobertura_compartida_pct": round(
                100 * area_comun / area_region, 2
            ),
        })

    return pd.DataFrame(registros)


# ==================================================
# EJECUCION
# ==================================================

def main():
    print("FIRESIGHT - COBERTURA ESPACIAL")
    print(f"Michoacan | {FECHA}")
    print(f"MODIS: {MODIS_ID} | VIIRS: {VIIRS_ID}")
    print("=" * 55)

    ids, geometrias, indice = preparar_hexagonos()

    print(f"Hexagonos que intersectan la region: {len(ids)}")

    print("\nReconstruyendo huellas MODIS...")
    modis, estadisticas_modis = acumular_huellas(
        "MODIS",
        bloques_modis(),
        ids,
        geometrias,
        indice,
    )

    print("\nReconstruyendo huellas VIIRS...")
    viirs, estadisticas_viirs = acumular_huellas(
        "VIIRS",
        bloques_viirs(),
        ids,
        geometrias,
        indice,
    )

    df = calcular_cobertura(
        ids, geometrias, modis, viirs
    )

    # Asociar detecciones H3 del analisis anterior.
    if ANALISIS_PREVIO.is_file():
        anterior = pd.read_csv(ANALISIS_PREVIO)

        columnas = [
            "celda_h3",
            "modis_fuego",
            "viirs_fuego",
        ]

        df = df.merge(
            anterior[columnas],
            on="celda_h3",
            how="left",
        )

        df["modis_fuego"] = (
            df["modis_fuego"].fillna(0).astype(int)
        )
        df["viirs_fuego"] = (
            df["viirs_fuego"].fillna(0).astype(int)
        )

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(
        SALIDA,
        index=False,
        encoding="utf-8-sig",
    )

    print("\nRESULTADOS")
    print("=" * 55)

    for nombre, datos in [
        ("MODIS", estadisticas_modis),
        ("VIIRS", estadisticas_viirs),
    ]:
        print(f"\n{nombre}")

        for campo, valor in datos.items():
            print(f"  {campo}: {valor:,}")

    print("\nRESUMEN GEOGRAFICO")

    print(
        "Celdas con area util MODIS:",
        int((df["area_modis_util_m2"] > 0).sum()),
    )

    print(
        "Celdas con area util VIIRS:",
        int((df["area_viirs_util_m2"] > 0).sum()),
    )

    print(
        "Celdas con area compartida:",
        int((df["area_compartida_m2"] > 0).sum()),
    )

    print(
        "Celdas con al menos 80% de area compartida:",
        int(
            (df["cobertura_compartida_pct"] >= 80).sum()
        ),
    )

    print(
        "Area compartida total estimada (km2):",
        round(df["area_compartida_m2"].sum() / 1e6, 2),
    )

    if "viirs_fuego" in df.columns:
        focos = df[
            (df["modis_fuego"] > 0)
            | (df["viirs_fuego"] > 0)
        ]

        print("\nCELDAS CON DETECCIONES DE FUEGO")

        columnas = [
            "celda_h3",
            "modis_fuego",
            "viirs_fuego",
            "cobertura_modis_pct",
            "cobertura_viirs_pct",
            "cobertura_compartida_pct",
        ]

        print(
            focos[columnas].to_string(index=False)
            if not focos.empty
            else "No se encontraron detecciones."
        )

    print(f"\nCSV generado: {SALIDA}")
    print("\nANALISIS FINALIZADO")

    print(
        "\nADVERTENCIA: Las huellas son aproximadas, "
        "reconstruidas con centros vecinos. "
        "No son las huellas instrumentales exactas."
    )


if __name__ == "__main__":
    main()
