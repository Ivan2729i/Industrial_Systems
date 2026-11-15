r"""FireSight: cobertura espacial EXPERIMENTAL entre MODIS Aqua y VIIRS S-NPP.

Reconstruye cuadrilateros aproximados usando separaciones entre centros
vecinos, restringidas al mismo escaneo. No son huellas instrumentales exactas.

Ejemplos:
    python .\src\cobertura_espacial.py --fecha 2024-04-16 --region guerrero
    python .\src\cobertura_espacial.py --fecha 2024-04-19 --region tabasco_chiapas
"""

import argparse
from collections import defaultdict
from pathlib import Path

import h3
import h5py
import numpy as np
import pandas as pd
from pyhdf.SD import SD, SDC
from pyproj import CRS, Transformer
from shapely.geometry import GeometryCollection, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

from analizar_celdas import CONFIGURACIONES
from regiones import REGIONES, RESOLUCION_H3, obtener_region


BASE = Path(__file__).resolve().parent
RESULTADOS = BASE / "resultados_lotes"
REGION_PREDETERMINADA = "michoacan_piloto"
FECHA_PREDETERMINADA = "2024-04-06-noche"

BLOQUE_FILAS = 32
MARGEN_GRADOS = 0.08  # Preseleccion de centros; no es un buffer de cobertura garantizado.
UMBRAL_COBERTURA_PCT = 80.0  # Experimental, NO validado.

# Limites de descarte exploratorios, NO especificaciones instrumentales NASA.
LIMITES = {
    "MODIS": {"filas_escaneo": 10, "paso_max_m": 8000, "area_max_m2": 50_000_000},
    "VIIRS": {"filas_escaneo": 32, "paso_max_m": 3000, "area_max_m2": 7_000_000},
}

COLUMNAS_COBERTURA = [
    "celda_h3",
    "area_h3_en_region_m2",
    "area_modis_util_m2",
    "area_viirs_util_m2",
    "area_compartida_m2",
    "cobertura_modis_pct",
    "cobertura_viirs_pct",
    "cobertura_compartida_pct",
]


def configurar_argumentos():
    parser = argparse.ArgumentParser(
        description="FireSight - Cobertura espacial experimental MODIS-VIIRS por region"
    )
    parser.add_argument(
        "--fecha", choices=sorted(CONFIGURACIONES), default=FECHA_PREDETERMINADA,
        help="Pareja de sobrevuelos registrada en analizar_celdas.py",
    )
    parser.add_argument(
        "--region", choices=sorted(REGIONES), default=REGION_PREDETERMINADA,
        help="Region registrada en regiones.py",
    )
    return parser.parse_args()


def ruta_salida(fecha, region_id, config):
    # Compatibilidad con los archivos del piloto historico de Michoacan.
    if region_id == REGION_PREDETERMINADA:
        hora_modis = config["modis"].split(".")[1]
        hora_viirs = config["viirs"].split(".")[1]
        nombre = f"cobertura_{fecha[:10]}_{hora_modis}_{hora_viirs}.csv"
    else:
        nombre = f"cobertura_{fecha}_{region_id}.csv"
    return RESULTADOS / nombre


def ruta_analisis(fecha, region_id):
    principal = RESULTADOS / f"analisis_celdas_{fecha}_{region_id}.csv"
    if principal.is_file():
        return principal

    # Las versiones previas de analizar_celdas guardaban los CSV en src/.
    if region_id == REGION_PREDETERMINADA:
        anterior = BASE / f"analisis_celdas_{fecha}.csv"
        if anterior.is_file():
            return anterior

    raise FileNotFoundError(
        f"No existe el analisis H3 previo para fecha={fecha}, region={region_id}. "
        f"Ejecuta antes: python .\\src\\analizar_celdas.py --fecha {fecha} --region {region_id}"
    )


def encontrar(carpeta, prefijo, extension):
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise FileNotFoundError(f"No existe el directorio NASA: {carpeta}")
    archivos = sorted(
        p for p in carpeta.glob(f"{prefijo}*")
        if p.is_file() and p.suffix.lower() == extension
    )
    if len(archivos) != 1:
        raise FileNotFoundError(
            f"Se esperaba exactamente un archivo {prefijo}*{extension} "
            f"en {carpeta}; encontrados: {len(archivos)}"
        )
    return archivos[0]


def proyeccion_local(region):
    sur, norte = region["sur"], region["norte"]
    oeste, este = region["oeste"], region["este"]
    if not (-90 < sur < norte < 90 and -180 < oeste < este < 180):
        raise ValueError(f"BBox geografico invalido: {region}")

    lat_centro = (sur + norte) / 2
    lon_centro = (oeste + este) / 2
    crs_local = CRS.from_proj4(
        f"+proj=laea +lat_0={lat_centro} +lon_0={lon_centro} "
        "+datum=WGS84 +units=m +no_defs"
    )
    proyector = Transformer.from_crs("EPSG:4326", crs_local, always_xy=True)

    def poligono_proyectado(coordenadas):
        lon = [p[0] for p in coordenadas]
        lat = [p[1] for p in coordenadas]
        x, y = proyector.transform(lon, lat)
        return Polygon(zip(x, y))

    rectangulo = poligono_proyectado([
        (oeste, sur), (este, sur), (este, norte), (oeste, norte)
    ])
    if not rectangulo.is_valid or rectangulo.area <= 0:
        raise ValueError("El poligono proyectado de la region es invalido")
    return proyector, poligono_proyectado, rectangulo


def preparar_hexagonos(region, poligono_proyectado, rectangulo):
    poligono_h3 = h3.LatLngPoly([
        (region["sur"], region["oeste"]),
        (region["sur"], region["este"]),
        (region["norte"], region["este"]),
        (region["norte"], region["oeste"]),
    ])
    interiores = h3.polygon_to_cells(poligono_h3, RESOLUCION_H3)
    if not interiores:
        # Permite ventanas menores que una celda, aun si ningun centro cae dentro.
        centro = h3.latlng_to_cell(
            (region["sur"] + region["norte"]) / 2,
            (region["oeste"] + region["este"]) / 2,
            RESOLUCION_H3,
        )
        interiores = {centro}

    candidatos = set(interiores)
    for celda in interiores:
        candidatos.update(h3.grid_disk(celda, 1))

    ids = []
    geometrias = []
    for celda in sorted(candidatos):
        limite = h3.cell_to_boundary(celda)
        poligono = poligono_proyectado([(lon, lat) for lat, lon in limite])
        recorte = poligono.intersection(rectangulo)
        if recorte.area > 1:
            ids.append(celda)
            geometrias.append(recorte)

    if not ids:
        raise RuntimeError("No se encontraron hexagonos H3 que intersecten la region")
    return ids, geometrias, STRtree(geometrias)


def bloques_modis(carpeta, modis_id):
    ruta_geo = encontrar(carpeta, f"MYD03.{modis_id}.061.", ".hdf")
    ruta_fire = encontrar(carpeta, f"MYD14.{modis_id}.061.", ".hdf")
    geo = SD(str(ruta_geo), SDC.READ)
    fire = None
    try:
        fire = SD(str(ruta_fire), SDC.READ)
        lat_ds = geo.select("Latitude")
        lon_ds = geo.select("Longitude")
        mask_ds = fire.select("fire mask")
        forma = tuple(lat_ds.info()[2])
        if not (forma == tuple(lon_ds.info()[2]) == tuple(mask_ds.info()[2])):
            raise ValueError("Dimensiones MODIS incompatibles")

        filas, columnas = forma
        for inicio in range(0, filas, BLOQUE_FILAS):
            fin = min(inicio + BLOQUE_FILAS, filas)
            desde = max(0, inicio - 1)
            hasta = min(filas, fin + 1)
            posicion = (desde, 0)
            cantidad = (hasta - desde, columnas)
            lat = lat_ds.get(start=posicion, count=cantidad)
            lon = lon_ds.get(start=posicion, count=cantidad)
            mascara = np.bitwise_and(
                mask_ds.get(start=posicion, count=cantidad), 15
            )
            # inicio evita inferir fila global a partir de enumerate(bloques).
            yield lat, lon, mascara, inicio - desde, fin - inicio, inicio
    finally:
        if fire is not None:
            fire.end()
        geo.end()


def bloques_viirs(carpeta, viirs_id):
    ruta_geo = encontrar(carpeta, f"VNP03IMG.{viirs_id}.002.", ".nc")
    ruta_fire = encontrar(carpeta, f"VNP14IMG.{viirs_id}.002.", ".nc")
    with h5py.File(ruta_geo, "r") as geo, h5py.File(ruta_fire, "r") as fire:
        lat_ds = geo["geolocation_data/latitude"]
        lon_ds = geo["geolocation_data/longitude"]
        mask_ds = fire["fire mask"]
        if not (lat_ds.shape == lon_ds.shape == mask_ds.shape):
            raise ValueError("Dimensiones VIIRS incompatibles")
        filas, _ = mask_ds.shape
        for inicio in range(0, filas, BLOQUE_FILAS):
            fin = min(inicio + BLOQUE_FILAS, filas)
            desde = max(0, inicio - 1)
            hasta = min(filas, fin + 1)
            yield (
                lat_ds[desde:hasta, :], lon_ds[desde:hasta, :],
                mask_ds[desde:hasta, :], inicio - desde, fin - inicio, inicio,
            )


def coordenadas_validas(lat, lon):
    return (
        np.isfinite(lat) & np.isfinite(lon)
        & (lat >= -90) & (lat <= 90)
        & (lon >= -180) & (lon <= 180)
    )


def reconstruir_huella(x, y, dx, dy, ex, ey, sensor):
    """Shared V1 footprint reconstruction; no change to its exploratory limits."""
    horizontal,vertical=np.hypot(dx,dy),np.hypot(ex,ey)
    limits=LIMITES[sensor]
    if not (np.isfinite(horizontal) and np.isfinite(vertical) and 25<horizontal<limits['paso_max_m'] and 25<vertical<limits['paso_max_m']):return None
    shape=Polygon([(x-dx/2-ex/2,y-dy/2-ey/2),(x+dx/2-ex/2,y+dy/2-ey/2),(x+dx/2+ex/2,y+dy/2+ey/2),(x-dx/2+ex/2,y-dy/2+ey/2)])
    return shape if shape.is_valid and 1000<=shape.area<=limits['area_max_m2'] else None


def acumular_huellas(sensor, bloques, ids, geometrias, indice, region,
                     proyector, rectangulo):
    """Estima cuadrilateros, recorta contra H3 y acumula areas sin duplicar."""
    fragmentos = defaultdict(list)
    estadisticas = {
        "centros_candidatos": 0,
        "geometria_descartada": 0,
        "huellas_en_region": 0,
    }
    max_paso = LIMITES[sensor]["paso_max_m"]
    max_area = LIMITES[sensor]["area_max_m2"]
    filas_por_escaneo = LIMITES[sensor]["filas_escaneo"]

    for lat, lon, mascara, offset, n_core, inicio_global in bloques:
        lat_core = lat[offset:offset + n_core]
        lon_core = lon[offset:offset + n_core]
        mask_core = mascara[offset:offset + n_core]

        util = np.isin(mask_core, [5, 7, 8, 9])
        cerca = (
            coordenadas_validas(lat_core, lon_core)
            & (lat_core >= region["sur"] - MARGEN_GRADOS)
            & (lat_core <= region["norte"] + MARGEN_GRADOS)
            & (lon_core >= region["oeste"] - MARGEN_GRADOS)
            & (lon_core <= region["este"] + MARGEN_GRADOS)
        )
        filas, columnas = np.where(util & cerca)
        if not len(filas):
            continue
        estadisticas["centros_candidatos"] += len(filas)

        r = filas + offset
        c = columnas
        filas_globales = inicio_global + filas
        primera_fila = (filas_globales // filas_por_escaneo) * filas_por_escaneo
        ultima_fila = primera_fila + filas_por_escaneo - 1

        # Nunca utilizar el centro de otro escaneo para la derivada vertical.
        arriba = r - (filas_globales > primera_fila).astype(np.int64)
        abajo = r + (filas_globales < ultima_fila).astype(np.int64)
        izquierda = np.maximum(c - 1, 0)
        derecha = np.minimum(c + 1, lat.shape[1] - 1)

        # Validar los indices antes de extraer los vecinos.
        indices_en_rango = (
            (arriba >= 0) & (abajo < lat.shape[0])
            & (izquierda >= 0) & (derecha < lat.shape[1])
        )
        # Con bloques de halo +/-1 esto deberia cumplirse siempre.
        if not np.all(indices_en_rango):
            estadisticas["geometria_descartada"] += int((~indices_en_rango).sum())
        r = r[indices_en_rango]
        c = c[indices_en_rango]
        arriba = arriba[indices_en_rango]
        abajo = abajo[indices_en_rango]
        izquierda = izquierda[indices_en_rango]
        derecha = derecha[indices_en_rango]
        if not len(r):
            continue

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
        estadisticas["geometria_descartada"] += len(r) - len(indices)
        if not len(indices):
            continue

        x0, y0 = proyector.transform(lo0[indices], la0[indices])
        xi, yi = proyector.transform(loi[indices], lai[indices])
        xd, yd = proyector.transform(lod[indices], lad[indices])
        xs, ys = proyector.transform(los[indices], las[indices])
        xb, yb = proyector.transform(lob[indices], lab[indices])

        pasos_columnas = derecha[indices] - izquierda[indices]
        pasos_filas = abajo[indices] - arriba[indices]
        # En archivos con una sola columna o un escaneo con una sola fila,
        # no se puede derivar geometria. Se descartan esas situaciones.
        buenas = (pasos_columnas > 0) & (pasos_filas > 0)
        estadisticas["geometria_descartada"] += int((~buenas).sum())
        if not np.any(buenas):
            continue
        dx = (xd[buenas] - xi[buenas]) / pasos_columnas[buenas]
        dy = (yd[buenas] - yi[buenas]) / pasos_columnas[buenas]
        ex = (xb[buenas] - xs[buenas]) / pasos_filas[buenas]
        ey = (yb[buenas] - ys[buenas]) / pasos_filas[buenas]
        x0 = x0[buenas]
        y0 = y0[buenas]

        for i in range(len(x0)):
            huella=reconstruir_huella(x0[i],y0[i],dx[i],dy[i],ex[i],ey[i],sensor)
            if huella is None:
                estadisticas['geometria_descartada']+=1
                continue
            if not huella.intersects(rectangulo):
                continue
            estadisticas["huellas_en_region"] += 1

            for posicion in indice.query(huella, predicate="intersects"):
                posicion = int(posicion)  # STRtree de Shapely >= 2.0
                fragmento = huella.intersection(geometrias[posicion])
                if fragmento.area > 1:
                    fragmentos[ids[posicion]].append(fragmento)

    return fragmentos, estadisticas


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
        area_comun = huella_modis.intersection(huella_viirs).area

        # Consistencia geometrica interna. No valida los footprints reales.
        tolerancia = max(1e-4, area_region * 1e-6)
        if (
            area_modis > area_region + tolerancia
            or area_viirs > area_region + tolerancia
            or area_comun > min(area_modis, area_viirs) + tolerancia
        ):
            raise RuntimeError(f"Area inconsistente para H3 {celda}")

        registros.append({
            "celda_h3": celda,
            "area_h3_en_region_m2": round(area_region, 2),
            "area_modis_util_m2": round(area_modis, 2),
            "area_viirs_util_m2": round(area_viirs, 2),
            "area_compartida_m2": round(area_comun, 2),
            "cobertura_modis_pct": round(100 * area_modis / area_region, 2),
            "cobertura_viirs_pct": round(100 * area_viirs / area_region, 2),
            "cobertura_compartida_pct": round(100 * area_comun / area_region, 2),
        })
    return pd.DataFrame(registros, columns=COLUMNAS_COBERTURA)


def incorporar_detecciones(df, fecha, region_id, config):
    ruta = ruta_analisis(fecha, region_id)
    anterior = pd.read_csv(ruta, dtype={"celda_h3": str})
    clave = ["celda_h3"]
    necesarias = clave + ["modis_fuego", "viirs_fuego"]
    faltantes = set(necesarias) - set(anterior.columns)
    if faltantes:
        raise ValueError(f"Columnas faltantes en {ruta.name}: {sorted(faltantes)}")
    if anterior["celda_h3"].isna().any() or anterior.duplicated(clave).any():
        raise RuntimeError(f"Celdas H3 vacias o duplicadas en {ruta.name}")
    if "region_id" in anterior.columns and not anterior["region_id"].eq(region_id).all():
        raise RuntimeError(f"El archivo {ruta.name} no pertenece a la region {region_id}")
    for campo, valor in (
        ("modis_sobrevuelo", config["modis"]),
        ("viirs_sobrevuelo", config["viirs"]),
    ):
        if campo in anterior.columns and not anterior[campo].eq(valor).all():
            raise RuntimeError(f"Sobrevuelo distinto al esperado en {ruta.name}: {campo}")

    # Las celdas de borde no incluidas por centro del pixel pueden tener
    # cobertura de huella pero no detecciones: ahi cero ES un conteo real.
    df = df.merge(
        anterior[necesarias], on="celda_h3", how="left", validate="one_to_one"
    )
    df[["modis_fuego", "viirs_fuego"]] = (
        df[["modis_fuego", "viirs_fuego"]].fillna(0).astype("int64")
    )
    # Verificar que todo H3 con detecciones del CSV anterior tenga
    # representacion en la grilla geometrica, si esta dentro de la bbox.
    ausentes = set(anterior["celda_h3"]) - set(df["celda_h3"])
    if ausentes:
        raise RuntimeError(
            f"El mallado de cobertura excluye {len(ausentes)} celdas del analisis H3: "
            f"{sorted(ausentes)[:3]}"
        )
    return df


def main():
    args = configurar_argumentos()
    config = CONFIGURACIONES[args.fecha]
    region = obtener_region(args.region)
    carpeta = Path(config["carpeta"])
    salida = ruta_salida(args.fecha, args.region, config)

    # Validar el CSV antes de empezar la reconstruccion costosa.
    ruta_analisis(args.fecha, args.region)
    proyector, poligono_proyectado, rectangulo = proyeccion_local(region)

    print("FIRESIGHT - COBERTURA ESPACIAL")
    print(f"Fecha: {args.fecha}")
    print(f"Region: {region['nombre']} [{args.region}]")
    print(
        f"BBox (O, S, E, N): {region['oeste']}, {region['sur']}, "
        f"{region['este']}, {region['norte']}"
    )
    print(f"MODIS: {config['modis']} | VIIRS: {config['viirs']}")
    print("=" * 55)

    ids, geometrias, indice = preparar_hexagonos(
        region, poligono_proyectado, rectangulo
    )
    print(f"Hexagonos que intersectan la region: {len(ids)}")

    print("\nReconstruyendo huellas MODIS...", flush=True)
    modis, estadisticas_modis = acumular_huellas(
        "MODIS", bloques_modis(carpeta, config["modis"]), ids,
        geometrias, indice, region, proyector, rectangulo,
    )
    print("\nReconstruyendo huellas VIIRS...", flush=True)
    viirs, estadisticas_viirs = acumular_huellas(
        "VIIRS", bloques_viirs(carpeta, config["viirs"]), ids,
        geometrias, indice, region, proyector, rectangulo,
    )

    df = calcular_cobertura(ids, geometrias, modis, viirs)
    df = incorporar_detecciones(df, args.fecha, args.region, config)
    df.insert(0, "resolucion_h3", RESOLUCION_H3)
    df.insert(0, "viirs_sobrevuelo", config["viirs"])
    df.insert(0, "modis_sobrevuelo", config["modis"])
    df.insert(0, "region_id", args.region)
    df.insert(0, "fecha", args.fecha)
    df["cobertura_estimacion"] = "centros_vecinos_mismo_escaneo"
    df["geometria_validada"] = False
    if df["celda_h3"].duplicated().any():
        raise RuntimeError("Celdas duplicadas en el archivo de cobertura")

    salida.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(salida, index=False, encoding="utf-8-sig")

    print("\nRESULTADOS")
    print("=" * 55)
    for sensor, stats in (("MODIS", estadisticas_modis), ("VIIRS", estadisticas_viirs)):
        print(f"\n{sensor}")
        for campo, valor in stats.items():
            print(f"  {campo}: {valor:,}")

    print("\nRESUMEN GEOGRAFICO")
    print("Celdas con area util MODIS:", int(df["area_modis_util_m2"].gt(0).sum()))
    print("Celdas con area util VIIRS:", int(df["area_viirs_util_m2"].gt(0).sum()))
    print("Celdas con area compartida:", int(df["area_compartida_m2"].gt(0).sum()))
    print(
        f"Celdas con al menos {UMBRAL_COBERTURA_PCT:g}% de area compartida:",
        int(df["cobertura_compartida_pct"].ge(UMBRAL_COBERTURA_PCT).sum()),
    )
    print(
        "Area compartida total estimada (km2):",
        round(df["area_compartida_m2"].sum() / 1e6, 2),
    )

    focos = df.loc[df["modis_fuego"].gt(0) | df["viirs_fuego"].gt(0)]
    print("\nCELDAS CON DETECCIONES DE FUEGO")
    if focos.empty:
        print("No se encontraron detecciones de fuego en esta region")
    else:
        columnas = [
            "celda_h3", "modis_fuego", "viirs_fuego",
            "cobertura_modis_pct", "cobertura_viirs_pct", "cobertura_compartida_pct",
        ]
        print(focos[columnas].to_string(index=False))

    print(f"\nCSV generado: {salida}")
    print("\nANALISIS FINALIZADO")
    print(
        "\nADVERTENCIA: Huellas aproximadas reconstruidas con centros vecinos. "
        "No son footprints instrumentales exactos ni superficie observada validada."
    )


if __name__ == "__main__":
    main()
