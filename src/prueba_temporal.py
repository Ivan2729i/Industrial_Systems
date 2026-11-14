
from pathlib import Path

import h3
import pandas as pd

DATOS = Path(__file__).resolve().parent / "datos"

COLUMNAS = [
    "latitude", "longitude", "acq_date",
    "acq_time", "satellite", "daynight", "type"
]


def cargar(nombre, satelite):
    df = pd.read_csv(
        DATOS / nombre,
        usecols=COLUMNAS,
        low_memory=False
    )

    df = df[
        df["satellite"].astype(str).str.upper().str.strip()
        == satelite
    ].copy()

    df = df[
        pd.to_numeric(df["type"], errors="coerce") == 0
    ].copy()

    # NASA registra la hora UTC como HHMM.
    # Por ejemplo, 38 se convierte a 0038.
    hora = (
        df["acq_time"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(4)
    )

    df["utc"] = pd.to_datetime(
        df["acq_date"].astype(str).str.strip()
        + " " + hora,
        format="%Y-%m-%d %H%M",
        errors="coerce",
        utc=True
    )

    df["latitude"] = pd.to_numeric(
        df["latitude"], errors="coerce"
    )
    df["longitude"] = pd.to_numeric(
        df["longitude"], errors="coerce"
    )

    df["turno"] = (
        df["daynight"].astype(str).str.upper().str.strip()
    )

    validos = (
        df["utc"].notna()
        & df["latitude"].between(-90, 90)
        & df["longitude"].between(-180, 180)
        & df["turno"].isin(["D", "N"])
    )

    print(f"{nombre}: {len(df):,} registros filtrados")
    print(f"Registros invalidos: {(~validos).sum():,}")

    df = df.loc[validos].copy()

    return df[["latitude", "longitude", "utc", "turno"]]


def asignar_h3(df, resolucion):
    resultado = df.copy()

    resultado["celda"] = [
        h3.latlng_to_cell(lat, lon, resolucion)
        for lat, lon in zip(
            resultado["latitude"],
            resultado["longitude"]
        )
    ]

    # Evitar repetir una celda en el mismo instante.
    return (
        resultado[["utc", "turno", "celda"]]
        .drop_duplicates()
        .sort_values("utc")
        .reset_index(drop=True)
    )


def comparar_tiempos(modis, viirs, minutos):
    datos_viirs = viirs.rename(
        columns={"utc": "utc_viirs"}
    )

    # Para cada celda-instante MODIS, buscar el registro
    # VIIRS temporalmente mas cercano en la misma celda.
    coincidencias = pd.merge_asof(
        modis,
        datos_viirs,
        left_on="utc",
        right_on="utc_viirs",
        by=["celda", "turno"],
        tolerance=pd.Timedelta(minutes=minutos),
        direction="nearest"
    )

    encontrados = coincidencias["utc_viirs"].notna()
    cantidad = int(encontrados.sum())
    total = len(coincidencias)

    porcentaje = 100 * cantidad / total if total else 0

    diferencias = (
        coincidencias.loc[encontrados, "utc"]
        - coincidencias.loc[encontrados, "utc_viirs"]
    ).abs().dt.total_seconds() / 60

    mediana = (
        diferencias.median()
        if not diferencias.empty else None
    )

    print(f"Ventana +/-{minutos:2d} min:")
    print(f"  Coincidencias posibles: {cantidad:,} / {total:,}")
    print(f"  Porcentaje MODIS:      {porcentaje:.2f}%")

    if mediana is not None:
        print(f"  Diferencia mediana:    {mediana:.1f} min")


if __name__ == "__main__":
    print("FIRESIGHT - PRUEBA TEMPORAL\n")

    modis = cargar("modis.csv", "AQUA")
    viirs = cargar("viirs.csv", "SNPP")

    for resolucion in [6, 7]:
        print(f"\n===== H3 {resolucion} =====")

        m = asignar_h3(modis, resolucion)
        v = asignar_h3(viirs, resolucion)

        print(f"MODIS celda-instante: {len(m):,}")
        print(f"VIIRS celda-instante: {len(v):,}")

        for minutos in [5, 10, 30]:
            comparar_tiempos(m, v, minutos)

    print("\nPRUEBA TEMPORAL FINALIZADA")
