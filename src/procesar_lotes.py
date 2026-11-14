
import csv
from datetime import datetime
from pathlib import Path

import pandas as pd

from analizar_celdas import (
    procesar_modis,
    procesar_viirs,
    generar_tabla,
)


# ==================================================
# CONFIGURACION
# ==================================================

BASE = Path(__file__).resolve().parent
DATOS = BASE / "datos"

MANIFIESTO = BASE / "manifiesto_granulos.csv"
SALIDA = BASE / "resultados_lotes"

# Ventana para seleccionar sobrevuelos candidatos.
# No garantiza simultaneidad ni cobertura compartida.
MAX_DIFERENCIA_MINUTOS = 30

COLUMNAS_MANIFIESTO = {
    "sensor",
    "fecha_hora",
    "archivo_fuego",
    "archivo_geo",
}


# ==================================================
# LECTURA DEL MANIFIESTO
# ==================================================

def convertir_fecha(clave):
    return datetime.strptime(
        clave,
        "A%Y%j.%H%M",
    )


def leer_manifiesto():
    if not MANIFIESTO.is_file():
        raise FileNotFoundError(
            f"No existe el manifiesto: {MANIFIESTO}"
        )

    registros = []

    with MANIFIESTO.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as archivo:

        lector = csv.DictReader(archivo)

        columnas = set(lector.fieldnames or [])

        faltantes = COLUMNAS_MANIFIESTO - columnas

        if faltantes:
            raise ValueError(
                "Faltan columnas en el manifiesto: "
                + ", ".join(sorted(faltantes))
            )

        for fila in lector:
            sensor = fila["sensor"].strip().upper()
            clave = fila["fecha_hora"].strip()

            if sensor not in ("MODIS", "VIIRS"):
                raise ValueError(
                    f"Sensor desconocido: {sensor}"
                )

            convertir_fecha(clave)

            registros.append({
                "sensor": sensor,
                "fecha_hora": clave,
                "archivo_fuego": fila[
                    "archivo_fuego"
                ].strip(),
                "archivo_geo": fila[
                    "archivo_geo"
                ].strip(),
            })

    if not registros:
        raise ValueError(
            "El manifiesto no contiene observaciones."
        )

    return registros


# ==================================================
# IDENTIFICACION DE PAREJAS
# ==================================================

def identificar_parejas(registros):
    modis = [
        r for r in registros
        if r["sensor"] == "MODIS"
    ]

    viirs = [
        r for r in registros
        if r["sensor"] == "VIIRS"
    ]

    parejas = []
    identificadores = set()

    for m in modis:
        fecha_modis = convertir_fecha(
            m["fecha_hora"]
        )

        for v in viirs:
            fecha_viirs = convertir_fecha(
                v["fecha_hora"]
            )

            # Comparar sobrevuelos del mismo dia UTC.
            if fecha_modis.date() != fecha_viirs.date():
                continue

            diferencia = abs(
                (fecha_modis - fecha_viirs).total_seconds()
            ) / 60

            if diferencia > MAX_DIFERENCIA_MINUTOS:
                continue

            identificador = (
                m["fecha_hora"],
                v["fecha_hora"],
            )

            if identificador in identificadores:
                continue

            identificadores.add(identificador)

            parejas.append({
                "modis": m,
                "viirs": v,
                "fecha": fecha_modis.date().isoformat(),
                "diferencia_min": diferencia,
            })

    return sorted(
        parejas,
        key=lambda p: (
            p["fecha"],
            p["modis"]["fecha_hora"],
        ),
    )


# ==================================================
# LOCALIZAR ARCHIVOS YA DESCARGADOS
# ==================================================

def buscar_archivo_local(nombre):
    # El manifiesto solo debe contener nombres,
    # nunca rutas arbitrarias.
    if not nombre or Path(nombre).name != nombre:
        raise ValueError(
            f"Nombre de archivo no valido: {nombre}"
        )

    encontrados = [
        ruta
        for ruta in DATOS.rglob(nombre)
        if ruta.is_file()
    ]

    if len(encontrados) > 1:
        raise RuntimeError(
            f"Archivo duplicado: {nombre}"
        )

    if not encontrados:
        return None

    return encontrados[0]


def localizar_pareja(modis, viirs):
    nombres = {
        "modis_fuego": modis["archivo_fuego"],
        "modis_geo": modis["archivo_geo"],
        "viirs_fuego": viirs["archivo_fuego"],
        "viirs_geo": viirs["archivo_geo"],
    }

    rutas = {
        clave: buscar_archivo_local(nombre)
        for clave, nombre in nombres.items()
    }

    faltantes = [
        nombre
        for clave, nombre in nombres.items()
        if rutas[clave] is None
    ]

    return rutas, faltantes


# ==================================================
# PROCESAMIENTO DE UNA PAREJA
# ==================================================

def procesar_pareja(pareja):
    modis = pareja["modis"]
    viirs = pareja["viirs"]

    fecha = pareja["fecha"]
    clave_modis = modis["fecha_hora"]
    clave_viirs = viirs["fecha_hora"]

    hora_modis = clave_modis.split(".")[1]
    hora_viirs = clave_viirs.split(".")[1]

    identificador = (
        f"{fecha}_{hora_modis}_{hora_viirs}"
    )

    print("\n" + "=" * 60)
    print(f"PAREJA: {identificador}")
    print(
        "Diferencia entre inicios:",
        f"{pareja['diferencia_min']:.0f} minutos",
    )
    print("=" * 60)

    resumen = {
        "identificador": identificador,
        "fecha": fecha,
        "modis_sobrevuelo": clave_modis,
        "viirs_sobrevuelo": clave_viirs,
        "diferencia_min": pareja["diferencia_min"],
        "estado": "pendiente",
        "celdas_total": 0,
        "celdas_utiles_ambos": 0,
        "celdas_fuego_ambos": 0,
        "deteccion_solo_modis": 0,
        "deteccion_solo_viirs": 0,
        "discrepancias_candidatas_viirs": 0,
        "celdas_umbral_80": 0,
        "viirs_reflejo_solar_pct": 0.0,
        "archivo_resultado": "",
        "detalle": "",
    }

    rutas, faltantes = localizar_pareja(
        modis,
        viirs,
    )

    if faltantes:
        resumen["estado"] = "faltan_archivos"
        resumen["detalle"] = "; ".join(faltantes)

        print("No se procesa: faltan archivos locales.")

        for nombre in faltantes:
            print(f"  - {nombre}")

        return resumen

    # El analizador existente espera que los
    # archivos de cada sensor compartan carpeta.
    if (
        rutas["modis_fuego"].parent
        != rutas["modis_geo"].parent
    ):
        raise ValueError(
            "Los archivos MODIS no estan "
            "en el mismo directorio."
        )

    if (
        rutas["viirs_fuego"].parent
        != rutas["viirs_geo"].parent
    ):
        raise ValueError(
            "Los archivos VIIRS no estan "
            "en el mismo directorio."
        )

    print("\nArchivos locales encontrados.")
    print("Iniciando procesamiento...")

    # Reutilizamos el analizador ya comprobado.
    datos_modis = procesar_modis(
        rutas["modis_fuego"].parent,
        clave_modis,
    )

    datos_viirs = procesar_viirs(
        rutas["viirs_fuego"].parent,
        clave_viirs,
    )

    config = {
        "modis": clave_modis,
        "viirs": clave_viirs,
    }

    df = generar_tabla(
        datos_modis,
        datos_viirs,
        fecha,
        config,
    )

    # Validacion de consistencia de conteos.
    for sensor in ("modis", "viirs"):
        total = int(df[f"{sensor}_pixeles"].sum())

        clasificados = (
            int(df[f"{sensor}_utiles"].sum())
            + int(df[f"{sensor}_nubes"].sum())
            + int(df[f"{sensor}_otros"].sum())
        )

        if sensor == "viirs":
            clasificados += int(
                df["viirs_reflejo_solar"].sum()
            )

        if total != clasificados:
            raise RuntimeError(
                f"Conteos inconsistentes en {sensor}: "
                f"{total} != {clasificados}"
            )

    salida = SALIDA / f"celdas_{identificador}.csv"

    df.to_csv(
        salida,
        index=False,
        encoding="utf-8-sig",
    )

    total_viirs = int(df["viirs_pixeles"].sum())
    reflejo = int(df["viirs_reflejo_solar"].sum())

    porcentaje_reflejo = (
        round(100 * reflejo / total_viirs, 2)
        if total_viirs else 0.0
    )

    resumen.update({
        "estado": "procesado",
        "celdas_total": len(df),
        "celdas_utiles_ambos": int(
            df["observacion_util_ambos"].sum()
        ),
        "celdas_fuego_ambos": int(
            df["fuego_ambos"].sum()
        ),
        "deteccion_solo_modis": int(
            df["deteccion_solo_modis"].sum()
        ),
        "deteccion_solo_viirs": int(
            df["deteccion_solo_viirs"].sum()
        ),
        "discrepancias_candidatas_viirs": int(
            df["fuego_solo_viirs"].sum()
        ),
        "celdas_umbral_80": int(
            df["supera_umbral_exploratorio"].sum()
        ),
        "viirs_reflejo_solar_pct": porcentaje_reflejo,
        "archivo_resultado": salida.name,
    })

    print("\nProcesamiento finalizado.")
    print(f"Celdas H3: {len(df)}")
    print(
        "Con datos utiles de ambos:",
        resumen["celdas_utiles_ambos"],
    )
    print(
        "Reflejo solar VIIRS:",
        f"{porcentaje_reflejo:.2f}%",
    )

    return resumen


# ==================================================
# EJECUCION AUTOMATICA
# ==================================================

def main():
    print("FIRESIGHT - PROCESAMIENTO AUTOMATICO")
    print("=" * 60)

    SALIDA.mkdir(parents=True, exist_ok=True)

    registros = leer_manifiesto()
    parejas = identificar_parejas(registros)

    print(f"Observaciones encontradas: {len(registros)}")
    print(f"Parejas candidatas: {len(parejas)}")

    resultados = []

    for pareja in parejas:
        try:
            resultado = procesar_pareja(pareja)

        except Exception as error:
            modis = pareja["modis"]["fecha_hora"]
            viirs = pareja["viirs"]["fecha_hora"]

            resultado = {
                "identificador": f"{modis}_{viirs}",
                "fecha": pareja["fecha"],
                "modis_sobrevuelo": modis,
                "viirs_sobrevuelo": viirs,
                "diferencia_min": pareja["diferencia_min"],
                "estado": "error",
                "detalle": (
                    f"{type(error).__name__}: {error}"
                ),
            }

            print(f"\nERROR: {resultado['detalle']}")

        resultados.append(resultado)

    resumen = pd.DataFrame(resultados)

    salida_resumen = SALIDA / "resumen_lotes.csv"

    resumen.to_csv(
        salida_resumen,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n" + "=" * 60)
    print("RESUMEN GENERAL")
    print("=" * 60)

    for estado, cantidad in (
        resumen["estado"].value_counts().items()
    ):
        print(f"{estado}: {cantidad}")

    print("\nResumen guardado en:")
    print(salida_resumen)

    print(
        "\nAVISO: Las parejas se seleccionan por "
        "proximidad temporal de inicio. Todavia "
        "no se valida cobertura espacial real "
        "ni simultaneidad pixel a pixel."
    )


if __name__ == "__main__":
    main()
