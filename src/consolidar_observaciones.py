
from pathlib import Path

import pandas as pd


BASE = Path(__file__).resolve().parent
DATOS = BASE / "resultados_lotes"

SALIDA = DATOS / "observaciones_pareadas_piloto.csv"
RESUMEN = DATOS / "resumen_compatibilidad_piloto.csv"

CLAVE = [
    "modis_sobrevuelo",
    "viirs_sobrevuelo",
    "celda_h3",
]

METRICAS = [
    "cobertura_compartida_pct",
    "diferencia_min",
    "modis_utc",
    "viirs_utc",
]

# Umbrales de investigacion, no validados.
MIN_COBERTURA = 80.0
MAX_DIFERENCIA_MIN = 5.0


def leer_csv(ruta):
    return pd.read_csv(
        ruta,
        dtype={"celda_h3": str},
    )


def comprobar_claves(df, origen):
    faltantes = set(CLAVE) - set(df.columns)

    if faltantes:
        raise ValueError(
            f"{origen}: faltan columnas {faltantes}"
        )

    if df[CLAVE].isna().any().any():
        raise ValueError(
            f"{origen}: existen identificadores vacios"
        )

    if df.duplicated(CLAVE).any():
        raise ValueError(
            f"{origen}: existen observaciones duplicadas"
        )


def main():
    print("FIRESIGHT - CONSOLIDACION DE OBSERVACIONES")
    print("=" * 55)

    archivos = sorted(
        DATOS.glob("celdas_????-??-??_????_????.csv")
    )

    if not archivos:
        raise FileNotFoundError(
            "No se encontraron resultados de lotes."
        )

    observaciones = []

    for ruta in archivos:
        tabla = leer_csv(ruta)
        comprobar_claves(tabla, ruta.name)

        print(f"Leyendo {ruta.name}: {len(tabla)} celdas")
        observaciones.append(tabla)

    df = pd.concat(
        observaciones,
        ignore_index=True,
    )

    comprobar_claves(df, "observaciones consolidadas")

    # Leer comparaciones espaciales y temporales
    # que ya hayan sido generadas.
    mediciones = []

    for ruta in sorted(DATOS.glob("comparacion_*.csv")):
        tabla = leer_csv(ruta)

        disponibles = [
            columna
            for columna in METRICAS
            if columna in tabla.columns
        ]

        if not disponibles:
            continue

        comprobar_claves(tabla, ruta.name)

        mediciones.append(
            tabla[CLAVE + disponibles]
        )

    if mediciones:
        medidas = pd.concat(
            mediciones,
            ignore_index=True,
        )

        comprobar_claves(
            medidas,
            "mediciones espaciotemporales",
        )

        df = df.merge(
            medidas,
            on=CLAVE,
            how="left",
            validate="one_to_one",
        )

    for columna in METRICAS:
        if columna not in df.columns:
            df[columna] = pd.NA

    tiene_espacio = df[
        "cobertura_compartida_pct"
    ].notna()

    tiene_tiempo = df[
        "diferencia_min"
    ].notna()

    observacion_compartida = (
        df["observacion_util_ambos"] == True
    )

    # Solo se evalua cuando existen ambas
    # mediciones y observaciones utiles.
    df["comparacion_candidata"] = (
        observacion_compartida
        & tiene_espacio
        & tiene_tiempo
        & df["cobertura_compartida_pct"].ge(
            MIN_COBERTURA
        )
        & df["diferencia_min"].le(
            MAX_DIFERENCIA_MIN
        )
    )

    def clasificar(fila):
        if not fila["observacion_util_ambos"]:
            return "sin_observacion_util_compartida"

        if (
            pd.isna(fila["cobertura_compartida_pct"])
            or pd.isna(fila["diferencia_min"])
        ):
            return "pendiente_medicion"

        if fila["comparacion_candidata"]:
            return "candidata_experimental"

        return "fuera_de_umbrales"

    df["estado_comparacion"] = df.apply(
        clasificar,
        axis=1,
    )

    df["region"] = "Michoacan_prueba"
    df["metodologia_validada"] = False

    # Una deteccion no equivale necesariamente
    # a un incendio independiente.
    df["viirs_detecta"] = df["viirs_fuego"] > 0
    df["modis_detecta"] = df["modis_fuego"] > 0


    # ==================================================
    # INCORPORAR CALIDAD DE DETECCIONES VIIRS
    # ==================================================

    ruta_qa = DATOS / "viirs_calidad_focos_h3.csv"

    if not ruta_qa.is_file():
        raise FileNotFoundError(
            f"No existe el archivo de calidad: {ruta_qa}"
        )

    qa = pd.read_csv(
        ruta_qa,
        dtype={"celda_h3": str},
    )

    # Relacionar las auditorias con sus sobrevuelos.
    mapa_sobrevuelos = {
        "madrugada": "A2024097.0918",
        "tarde": "A2024097.2030",
    }

    if not qa["sobrevuelo"].isin(
        mapa_sobrevuelos
    ).all():
        raise ValueError(
            "La auditoria contiene sobrevuelos desconocidos."
        )

    qa["viirs_sobrevuelo"] = qa[
        "sobrevuelo"
    ].map(mapa_sobrevuelos)

    qa = qa.rename(columns={
        "detecciones_originales": "qa_originales",
        "bowtie_residual": "viirs_bowtie_residual",
        "geo_no_nominal": "viirs_geo_no_nominal",
        "detecciones_sin_bowtie": "viirs_fuego_sin_bowtie",
    })

    clave_qa = ["viirs_sobrevuelo", "celda_h3"]

    if qa.duplicated(clave_qa).any():
        raise ValueError(
            "Existen registros QA duplicados."
        )

    columnas_qa = [
        "qa_originales",
        "viirs_bowtie_residual",
        "viirs_geo_no_nominal",
        "viirs_fuego_sin_bowtie",
    ]

    df = df.merge(
        qa[clave_qa + columnas_qa],
        on=clave_qa,
        how="left",
        validate="many_to_one",
    )

    # Solo conocemos la auditoria de los dos
    # sobrevuelos del 6 de abril.
    tiene_auditoria = df["viirs_sobrevuelo"].isin(
        mapa_sobrevuelos.values()
    )

    # En esos sobrevuelos, una celda ausente de QA
    # significa que no tuvo detecciones de fuego.
    # No aplicamos esta regla al 8 de abril.
    df.loc[tiene_auditoria, columnas_qa] = (
        df.loc[tiene_auditoria, columnas_qa].fillna(0)
    )

    for columna in columnas_qa:
        df[columna] = df[columna].astype("Int64")

    # Comprobar que QA y mascara original coincidan.
    inconsistencias = (
        tiene_auditoria
        & (
            df["viirs_fuego"]
            != df["qa_originales"]
        )
    ).fillna(False)

    if inconsistencias.any():
        raise RuntimeError(
            "El conteo QA no coincide con "
            "las detecciones originales VIIRS."
        )

    # Conservar presencia de fuego sin redundancia
    # como indicador alternativo, no definitivo.
    df["viirs_detecta_sin_bowtie"] = (
        df["viirs_fuego_sin_bowtie"]
        .gt(0)
        .astype("boolean")
    )

    df.loc[
        ~tiene_auditoria,
        "viirs_detecta_sin_bowtie"
    ] = pd.NA

    print("\nAUDITORIA QA INTEGRADA")
    print(
        "Detecciones originales VIIRS auditadas:",
        int(df.loc[tiene_auditoria, "viirs_fuego"].sum())
    )
    print(
        "Detecciones con bow-tie residual:",
        int(df["viirs_bowtie_residual"].sum())
    )
    print(
        "Detecciones sin bow-tie residual:",
        int(df["viirs_fuego_sin_bowtie"].sum())
    )
    print(
        "Registros sin auditoria QA:",
        int((~tiene_auditoria).sum())
    )


    df.to_csv(
        SALIDA,
        index=False,
        encoding="utf-8-sig",
    )

    agrupacion = [
        "modis_sobrevuelo",
        "viirs_sobrevuelo",
    ]

    resumen = df.groupby(
        agrupacion,
        as_index=False,
    ).agg(
        celdas=("celda_h3", "size"),
        observacion_ambos=(
            "observacion_util_ambos", "sum"
        ),
        candidatas=(
            "comparacion_candidata", "sum"
        ),
        celdas_fuego_modis=(
            "modis_detecta", "sum"
        ),
        celdas_fuego_viirs=(
            "viirs_detecta", "sum"
        ),
    )

    resumen.to_csv(
        RESUMEN,
        index=False,
        encoding="utf-8-sig",
    )

    print("\nRESULTADOS")
    print(f"Observaciones consolidadas: {len(df)}")
    print(
        "Con medicion espacial:",
        int(tiene_espacio.sum()),
    )
    print(
        "Con medicion temporal:",
        int(tiene_tiempo.sum()),
    )
    print(
        "Comparaciones candidatas:",
        int(df["comparacion_candidata"].sum()),
    )

    print("\nRESUMEN POR PAREJA")
    print(resumen.to_string(index=False))

    print("\nArchivos generados:")
    print(SALIDA)
    print(RESUMEN)

    print(
        "\nLos datos siguen siendo experimentales. "
        "No representan armonizacion validada."
    )


if __name__ == "__main__":
    main()
