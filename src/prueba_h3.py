
from pathlib import Path
from collections import defaultdict

import pandas as pd
import h3


# CONFIGURACION
BASE = Path(__file__).resolve().parent
DATOS = BASE / "datos"
SALIDA = BASE / "resultados_h3.csv"

FECHA_INICIO = pd.Timestamp("2024-04-01")
FECHA_FIN = pd.Timestamp("2024-04-10")

RESOLUCIONES = [6, 7, 8]

COLUMNAS = {
    "latitude", "longitude", "acq_date", "acq_time",
    "satellite", "instrument", "daynight", "type"
}


def cargar_datos(nombre, satelites):
    ruta = DATOS / nombre

    if not ruta.is_file():
        raise FileNotFoundError(f"No existe: {ruta}")

    df = pd.read_csv(
        ruta,
        usecols=lambda c: c.strip().lower() in COLUMNAS,
        low_memory=False,
    )

    df.columns = df.columns.str.strip().str.lower()

    faltantes = COLUMNAS - set(df.columns)
    if faltantes:
        raise ValueError(
            f"{nombre}: faltan columnas {sorted(faltantes)}"
        )

    print(f"\n========== {nombre.upper()} ==========")
    print(f"Registros originales: {len(df):,}")

    # 1. Seleccionar el satelite correcto.
    df["satellite"] = (
        df["satellite"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df = df[df["satellite"].isin(satelites)].copy()

    print(f"Registros del satelite: {len(df):,}")

    if df.empty:
        raise ValueError(
            f"No hay registros de {satelites} en {nombre}"
        )

    # 2. Verificar el instrumento esperado.
    instrumentos = (
        df["instrument"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    if nombre == "modis.csv":
        esperado = {"MODIS"}
    else:
        esperado = {"SNPP", "VIIRS"}

    if not instrumentos.isin(esperado).all():
        raise ValueError(
            f"Instrumento inesperado en {nombre}: "
            f"{instrumentos.unique().tolist()}"
        )

    # 3. Conservar presuntos incendios de vegetacion.
    df["type"] = pd.to_numeric(
        df["type"], errors="coerce"
    )
    df = df[df["type"] == 0].copy()

    print(f"Presuntos incendios vegetacion: {len(df):,}")

    # 4. Convertir coordenadas.
    df["latitude"] = pd.to_numeric(
        df["latitude"], errors="coerce"
    )
    df["longitude"] = pd.to_numeric(
        df["longitude"], errors="coerce"
    )

    # 5. Interpretar fechas ISO y dia/mes/anio.
    texto_fecha = df["acq_date"].astype(str).str.strip()

    fecha_iso = pd.to_datetime(
        texto_fecha,
        format="%Y-%m-%d",
        errors="coerce"
    )

    fecha_dmy = pd.to_datetime(
        texto_fecha,
        format="%d/%m/%Y",
        errors="coerce"
    )

    df["fecha"] = fecha_iso.fillna(fecha_dmy)

    # 6. Normalizar dia y noche.
    df["turno"] = (
        df["daynight"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # 7. Validar coordenadas, fechas y turnos.
    validos = (
        df["latitude"].between(-90, 90)
        & df["longitude"].between(-180, 180)
        & df["fecha"].notna()
        & df["fecha"].between(FECHA_INICIO, FECHA_FIN)
        & df["turno"].isin(["D", "N"])
    )

    print(f"Registros excluidos por validacion: {(~validos).sum():,}")


    # DIAGNOSTICO DE REGISTROS EXCLUIDOS
    print("\n--- DIAGNOSTICO DE VALIDACION ---")

    coordenadas_validas = (
        df["latitude"].between(-90, 90)
        & df["longitude"].between(-180, 180)
    )

    fechas_fuera = (
        df["fecha"].notna()
        & ~df["fecha"].between(FECHA_INICIO, FECHA_FIN)
    )

    print("Coordenadas invalidas:",
          (~coordenadas_validas).sum())

    print("Fechas sin interpretar:",
          df["fecha"].isna().sum())

    print("Fechas fuera del rango:",
          fechas_fuera.sum())

    print("Turnos invalidos:",
          (~df["turno"].isin(["D", "N"])).sum())

    print("\nRegistros por fecha:")
    print(
        df["fecha"]
        .value_counts(dropna=False)
        .sort_index()
        .to_string()
    )


    df = df.loc[validos].copy()

    if df.empty:
        raise ValueError(
            f"{nombre}: no quedaron registros utilizables"
        )

    df["fecha"] = df["fecha"].dt.strftime("%Y-%m-%d")

    print(f"Registros finales: {len(df):,}")
    print(f"Fechas disponibles: {df['fecha'].nunique()}")

    return df[[
        "latitude", "longitude", "fecha", "turno"
    ]]


def agrupar_h3(df, resolucion):
    grupos = defaultdict(set)

    for lat, lon, fecha, turno in df.itertuples(
        index=False, name=None
    ):
        celda = h3.latlng_to_cell(
            float(lat),
            float(lon),
            resolucion
        )

        # Cada celda cuenta solo una vez por dia y turno.
        grupos[(fecha, turno)].add(celda)

    return grupos


def comparar(modis, viirs):
    resultados = []

    for resolucion in RESOLUCIONES:
        print(f"\n===== H3 RESOLUCION {resolucion} =====")

        grupos_m = agrupar_h3(modis, resolucion)
        grupos_v = agrupar_h3(viirs, resolucion)

        claves = sorted(set(grupos_m) | set(grupos_v))

        total_m = 0
        total_v = 0
        total_comunes = 0
        total_union = 0

        for fecha, turno in claves:
            m = grupos_m.get((fecha, turno), set())
            v = grupos_v.get((fecha, turno), set())

            comunes = len(m & v)
            solo_modis = len(m - v)
            solo_viirs = len(v - m)
            union = len(m | v)

            total_m += len(m)
            total_v += len(v)
            total_comunes += comunes
            total_union += union

            porcentaje = (
                100 * comunes / union if union else 0
            )

            resultados.append({
                "resolucion_h3": resolucion,
                "fecha": fecha,
                "turno": turno,
                "celdas_modis": len(m),
                "celdas_viirs": len(v),
                "celdas_comunes": comunes,
                "solo_modis": solo_modis,
                "solo_viirs": solo_viirs,
                "jaccard_pct": round(porcentaje, 2),
            })

        # Verificar consistencia de los conteos.
        assert total_comunes <= min(total_m, total_v)
        assert (
            total_union
            == total_m + total_v - total_comunes
        )

        jaccard_global = (
            100 * total_comunes / total_union
            if total_union else 0
        )

        print(f"Celdas-dia-turno MODIS: {total_m:,}")
        print(f"Celdas-dia-turno VIIRS: {total_v:,}")
        print(f"Celdas coincidentes:   {total_comunes:,}")
        print(f"Solo MODIS:            {total_m-total_comunes:,}")
        print(f"Solo VIIRS:            {total_v-total_comunes:,}")
        print(f"Coincidencia Jaccard:  {jaccard_global:.2f}%")

    resultado = pd.DataFrame(resultados)
    resultado.to_csv(SALIDA, index=False, encoding="utf-8-sig")

    print("\n====================================")
    print("PRUEBA FINALIZADA CORRECTAMENTE")
    print(f"Resultados guardados en: {SALIDA}")
    print("====================================")


if __name__ == "__main__":
    print("INICIANDO PRUEBA H3 - FIRESIGHT")

    modis = cargar_datos(
        "modis.csv",
        {"AQUA", "A"}
    )

    viirs = cargar_datos(
        "viirs.csv",
        {"SNPP"}
    )

    comparar(modis, viirs)
