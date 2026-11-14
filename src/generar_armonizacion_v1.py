
from collections import defaultdict
from pathlib import Path
from datetime import datetime

import h3
import h5py
import numpy as np
import pandas as pd

from analizar_celdas import CONFIGURACIONES
from regiones import obtener_region, RESOLUCION_H3


BASE = Path(__file__).resolve().parent
RESULTADOS = BASE / "resultados_lotes"

REGIONES_NUEVAS = {
    "guerrero": "2024-04-16",
    "tabasco_chiapas": "2024-04-19",
}

COLUMNAS_COBERTURA = [
    "celda_h3",
    "area_modis_util_m2",
    "area_viirs_util_m2",
    "area_compartida_m2",
    "cobertura_modis_pct",
    "cobertura_viirs_pct",
    "cobertura_compartida_pct",
]

COLUMNAS_TIEMPO = [
    "celda_h3",
    "modis_utc",
    "viirs_utc",
    "diferencia_min",
]


def leer_csv(ruta):
    if not ruta.is_file():
        raise FileNotFoundError(
            f"Falta el archivo requerido: {ruta}"
        )

    return pd.read_csv(
        ruta,
        dtype={"celda_h3": str},
    )


def validar_unicos(df, nombre):
    if df["celda_h3"].isna().any():
        raise ValueError(
            f"{nombre}: existen identificadores H3 vacios."
        )

    if df["celda_h3"].duplicated().any():
        raise ValueError(
            f"{nombre}: existen celdas H3 duplicadas."
        )


def archivo_viirs(fecha):
    config = CONFIGURACIONES[fecha]

    encontrados = sorted(
        config["carpeta"].glob(
            f"VNP14IMG.{config['viirs']}.002.*"
        )
    )

    if len(encontrados) != 1:
        raise RuntimeError(
            f"{fecha}: se esperaba un archivo VNP14IMG; "
            f"encontrados {len(encontrados)}."
        )

    return encontrados[0]


def auditar_viirs(fecha, region_id):
    """
    Recorre los pixeles de fuego VIIRS.
    Conserva conteos originales y variantes QA.

    Bit 22: bow-tie residual.
    Bit 5: geolocalizacion no nominal.
    """

    region = obtener_region(region_id)
    config = CONFIGURACIONES[fecha]

    ruta_fire = archivo_viirs(fecha)

    rutas_geo = sorted(
        config["carpeta"].glob(
            f"VNP03IMG.{config['viirs']}.002.*"
        )
    )

    if len(rutas_geo) != 1:
        raise RuntimeError(
            f"{fecha}: archivo VNP03IMG no identificado."
        )

    registros = defaultdict(
        lambda: {
            "viirs_fuego_qa_total": 0,
            "viirs_bowtie_residual": 0,
            "viirs_geo_no_nominal": 0,
            "viirs_fuego_sin_bowtie": 0,
            "viirs_fuego_qa_nominal": 0,
        }
    )

    with (
        h5py.File(ruta_fire, "r") as fire,
        h5py.File(rutas_geo[0], "r") as geo,
    ):
        mascara = fire["fire mask"]
        qa = fire["algorithm QA"]
        lat = geo["geolocation_data/latitude"]
        lon = geo["geolocation_data/longitude"]

        if not (
            mascara.shape == qa.shape
            == lat.shape == lon.shape
        ):
            raise ValueError(
                "Dimensiones VIIRS y QA incompatibles."
            )

        for inicio in range(0, mascara.shape[0], 32):
            fin = min(inicio + 32, mascara.shape[0])

            bloque = mascara[inicio:fin, :]
            filas, columnas = np.where(
                np.isin(bloque, [7, 8, 9])
            )

            if len(filas) == 0:
                continue

            latitudes = lat[inicio:fin, :][filas, columnas]
            longitudes = lon[inicio:fin, :][filas, columnas]
            valores_qa = np.asarray(
                qa[inicio:fin, :][filas, columnas],
                dtype=np.uint32,
            )

            for latitud, longitud, bits in zip(
                latitudes, longitudes, valores_qa
            ):
                if not (
                    np.isfinite(latitud)
                    and np.isfinite(longitud)
                    and region["sur"] <= latitud <= region["norte"]
                    and region["oeste"] <= longitud <= region["este"]
                ):
                    continue

                celda = h3.latlng_to_cell(
                    float(latitud),
                    float(longitud),
                    RESOLUCION_H3,
                )

                bowtie = bool(
                    (int(bits) >> 22) & 1
                )

                geo_mala = bool(
                    (int(bits) >> 5) & 1
                )

                registro = registros[celda]

                registro["viirs_fuego_qa_total"] += 1
                registro["viirs_bowtie_residual"] += int(bowtie)
                registro["viirs_geo_no_nominal"] += int(geo_mala)

                if not bowtie:
                    registro["viirs_fuego_sin_bowtie"] += 1

                if not bowtie and not geo_mala:
                    registro["viirs_fuego_qa_nominal"] += 1

    columnas = [
        "celda_h3",
        "viirs_fuego_qa_total",
        "viirs_bowtie_residual",
        "viirs_geo_no_nominal",
        "viirs_fuego_sin_bowtie",
        "viirs_fuego_qa_nominal",
    ]

    filas = [
        {"celda_h3": celda, **valores}
        for celda, valores in sorted(registros.items())
    ]

    return pd.DataFrame(filas, columns=columnas)


def clasificar(modis, viirs, evaluable):
    return np.select(
        [
            evaluable & modis & viirs,
            evaluable & modis & ~viirs,
            evaluable & ~modis & viirs,
            evaluable & ~modis & ~viirs,
        ],
        [
            "AMBOS",
            "SOLO_MODIS",
            "SOLO_VIIRS",
            "NINGUNO",
        ],
        default="NO_EVALUABLE",
    )


def procesar_region(region_id, fecha):
    print(f"\nProcesando {region_id} | {fecha}")

    analisis = leer_csv(
        RESULTADOS
        / f"analisis_celdas_{fecha}_{region_id}.csv"
    )

    tiempos = leer_csv(
        RESULTADOS
        / f"tiempos_{fecha}_{region_id}.csv"
    )

    cobertura = leer_csv(
        RESULTADOS
        / f"cobertura_{fecha}_{region_id}.csv"
    )

    for nombre, tabla in [
        ("analisis", analisis),
        ("tiempos", tiempos),
        ("cobertura", cobertura),
    ]:
        validar_unicos(tabla, nombre)

    if not analisis["region_id"].eq(region_id).all():
        raise RuntimeError(
            "El CSV de analisis pertenece a otra region."
        )

    if not analisis["fecha"].eq(fecha).all():
        raise RuntimeError(
            "El CSV de analisis pertenece a otra fecha."
        )

    df = analisis.merge(
        tiempos[COLUMNAS_TIEMPO],
        on="celda_h3",
        how="left",
        validate="one_to_one",
    )

    df = df.merge(
        cobertura[COLUMNAS_COBERTURA],
        on="celda_h3",
        how="left",
        validate="one_to_one",
    )

    qa = auditar_viirs(fecha, region_id)
    validar_unicos(qa, "QA VIIRS")

    ruta_qa = (
        RESULTADOS
        / f"qa_viirs_{fecha}_{region_id}.csv"
    )
    qa.to_csv(ruta_qa, index=False)

    df = df.merge(
        qa,
        on="celda_h3",
        how="left",
        validate="one_to_one",
    )

    columnas_qa = [
        columna
        for columna in qa.columns
        if columna != "celda_h3"
    ]

    # QA fue inspeccionado para toda la region.
    # Ausencia de detecciones significa cero focos,
    # no ausencia del archivo QA.
    df[columnas_qa] = (
        df[columnas_qa]
        .fillna(0)
        .astype(int)
    )

    if not (
        df["viirs_fuego"]
        == df["viirs_fuego_qa_total"]
    ).all():
        diferencias = df.loc[
            df["viirs_fuego"]
            != df["viirs_fuego_qa_total"],
            "celda_h3",
        ].tolist()

        raise RuntimeError(
            "Los conteos VIIRS no coinciden con QA. "
            f"Celdas: {diferencias[:10]}"
        )

    tiempo = pd.to_numeric(
        df["diferencia_min"],
        errors="coerce",
    )

    cobertura_pct = pd.to_numeric(
        df["cobertura_compartida_pct"],
        errors="coerce",
    )

    utiles = (
        df["observacion_util_ambos"]
        .astype(str)
        .str.lower()
        .eq("true")
    )

    cobertura_ok = cobertura_pct >= 80

    estricto = (
        utiles
        & cobertura_ok
        & tiempo.between(0, 5)
    )

    exploratorio = (
        utiles
        & cobertura_ok
        & tiempo.gt(5)
        & tiempo.le(15)
    )

    evaluable = estricto | exploratorio

    df["estrato_temporal"] = np.select(
        [estricto, exploratorio],
        ["A_0_A_5_MIN", "B_MAS_5_A_15_MIN"],
        default="NO_EVALUABLE",
    )

    df["alineacion_experimental"] = evaluable
    df["qa_viirs_disponible"] = True

    fuego_modis = df["modis_fuego"] > 0
    fuego_viirs = df["viirs_fuego"] > 0
    fuego_viirs_qa = df["viirs_fuego_sin_bowtie"] > 0

    df["coincidencia_original"] = clasificar(
        fuego_modis,
        fuego_viirs,
        evaluable,
    )

    df["coincidencia_qa"] = clasificar(
        fuego_modis,
        fuego_viirs_qa,
        evaluable,
    )

    df["origen_datos"] = "regional_v1"

    print("Registros:", len(df))
    print("Evaluables:", int(evaluable.sum()))
    print("Fuego VIIRS:", int(df["viirs_fuego"].sum()))
    print(
        "Bow-tie residual:",
        int(df["viirs_bowtie_residual"].sum()),
    )

    return df


def fecha_desde_granulo(valor):
    codigo = str(valor).split(".")[0].removeprefix("A")
    return datetime.strptime(codigo, "%Y%j").date().isoformat()


def main():
    print("FIRESIGHT - ARMONIZACION V1")
    print("=" * 55)

    RESULTADOS.mkdir(parents=True, exist_ok=True)

    piloto = leer_csv(
        RESULTADOS / "observaciones_h3_armonizadas_v0.csv"
    )

    piloto["region_id"] = "michoacan_piloto"
    piloto["region_nombre"] = "Michoacan - piloto inicial"
    piloto["origen_datos"] = "piloto_v0"

    if "fecha" not in piloto.columns:
        piloto["fecha"] = piloto[
            "modis_sobrevuelo"
        ].map(fecha_desde_granulo)

    nuevas = [
        procesar_region(region_id, fecha)
        for region_id, fecha in REGIONES_NUEVAS.items()
    ]

    armonizado = pd.concat(
        [piloto, *nuevas],
        ignore_index=True,
        sort=False,
    )

    clave = [
        "region_id",
        "modis_sobrevuelo",
        "viirs_sobrevuelo",
        "celda_h3",
    ]

    if armonizado[clave].isna().any().any():
        raise RuntimeError("Existen claves incompletas.")

    if armonizado.duplicated(clave).any():
        raise RuntimeError(
            "Existen observaciones H3 duplicadas."
        )

    armonizado["version_armonizacion"] = "v1_experimental"
    armonizado["calibracion_estadistica"] = False
    armonizado["geometria_validada"] = False
    armonizado["metodo"] = "H3_7_PRESENCIA_DETECCION"

    salida = (
        RESULTADOS / "observaciones_h3_armonizadas_v1.csv"
    )

    resumen_salida = (
        RESULTADOS / "resumen_armonizacion_v1.csv"
    )

    resumen = (
        armonizado.groupby(
            [
                "region_id",
                "estrato_temporal",
                "coincidencia_qa",
            ],
            dropna=False,
        )
        .size()
        .unstack("coincidencia_qa", fill_value=0)
        .reset_index()
    )

    armonizado.to_csv(
        salida,
        index=False,
        encoding="utf-8-sig",
    )

    resumen.to_csv(
        resumen_salida,
        index=False,
        encoding="utf-8-sig",
    )

    print("\nRESULTADO FINAL")
    print("Registros V0:", len(piloto))
    print(
        "Registros nuevos:",
        sum(len(df) for df in nuevas),
    )
    print("Total V1:", len(armonizado))

    print("\nRESUMEN POR REGION")
    print(resumen.to_string(index=False))

    print("\nArchivo:", salida)
    print("Resumen:", resumen_salida)

    print(
        "\nAVISO: Armonizacion experimental. "
        "Sin calibracion estadistica de sensibilidad."
    )


if __name__ == "__main__":
    main()
