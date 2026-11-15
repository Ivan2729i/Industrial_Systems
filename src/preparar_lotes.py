
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlsplit, unquote
import csv
import re
import time

import earthaccess

BASE = Path(__file__).resolve().parent
SALIDA = BASE / "manifiesto_granulos.csv"

# Michoacan: region de nuestra prueba
REGION = (-102.15, 19.35, -101.80, 19.60)

PERIODO = (
    "2024-04-06T00:00:00",
    "2024-04-08T23:59:59",
)

PRODUCTOS = {
    "MODIS": ("MYD14", "MYD03", "061"),
    "VIIRS": ("VNP14IMG", "VNP03IMG", "002"),
}


def buscar(**filtros):
    for intento in range(3):
        try:
            return earthaccess.search_data(**filtros)
        except Exception as error:
            print(f"Error de consulta NASA: {type(error).__name__}")
            if intento == 2:
                raise
            time.sleep(2 * (intento + 1))


def obtener_nombre(granulo, producto):
    # El catalogo LAADS puede devolver un ID en vez
    # del nombre del archivo. Usamos sus enlaces reales.
    for enlace in granulo.data_links(access="external"):
        nombre = unquote(urlsplit(enlace).path.rsplit("/", 1)[-1])
        if nombre.startswith(producto + ".A"):
            return nombre

    metadata = granulo.get("umm", {})
    datos = metadata.get("DataGranule", {})

    for nombre in (
        datos.get("ProducerGranuleId"),
        metadata.get("GranuleUR")
    ):
        if isinstance(nombre, str) and nombre.startswith(producto + ".A"):
            return nombre

    raise ValueError(f"No se pudo identificar archivo {producto}")


def fecha_hora(clave):
    return datetime.strptime(clave, "A%Y%j.%H%M")


def main():
    import argparse
    from datetime import date
    global REGION, PERIODO, SALIDA
    parser = argparse.ArgumentParser(description='Prepara manifiesto Aqua/SNPP sin modificar el experimento V1')
    parser.add_argument('--bbox', required=True, help='oeste,sur,este,norte')
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    west,south,east,north = map(float,args.bbox.split(','))
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90): parser.error('bbox invalido')
    first,last=date.fromisoformat(args.start),date.fromisoformat(args.end)
    if first>last: parser.error('Rango invertido')
    if args.output.exists(): parser.error('El manifiesto de salida ya existe; usa otro nombre')
    REGION=(west,south,east,north)
    PERIODO=((datetime.fromisoformat(str(first))-timedelta(minutes=15)).isoformat(),(datetime.fromisoformat(str(last))+timedelta(days=1,minutes=15)).isoformat())
    SALIDA=args.output
    SALIDA.parent.mkdir(parents=True,exist_ok=True)

    print("FIRESIGHT - PREPARACION AUTOMATICA DE LOTES")
    print("=" * 55)

    registros = []

    for sensor, (fuego, geo, version) in PRODUCTOS.items():
        print(f"\nBuscando {fuego}...")

        granulos = buscar(
            short_name=fuego,
            version=version,
            temporal=PERIODO,
            bounding_box=REGION,
            count=-1,
        )

        print(f"Granulos de fuego encontrados: {len(granulos)}")

        for granulo in granulos:
            try:
                nombre_fuego = obtener_nombre(granulo, fuego)

                patron = rf"{re.escape(fuego)}\.(A\d{{7}}\.\d{{4}})\."
                coincidencia = re.search(patron, nombre_fuego)

                if not coincidencia:
                    raise ValueError("Fecha/hora no reconocida")

                clave = coincidencia.group(1)

                # La geolocalizacion se busca por nombre
                # exacto de periodo, sin filtro geoespacial.
                resultado_geo = buscar(
                    short_name=geo,
                    granule_name=f"{geo}.{clave}.{version}.*",
                    count=10,
                )

                if len(resultado_geo) != 1:
                    print(
                        f"AVISO: {geo} {clave}: "
                        f"{len(resultado_geo)} resultados"
                    )
                    continue

                nombre_geo = obtener_nombre(
                    resultado_geo[0], geo
                )

                registros.append({
                    "sensor": sensor,
                    "fecha_hora": clave,
                    "archivo_fuego": nombre_fuego,
                    "archivo_geo": nombre_geo,
                })

                print(f"  OK {clave}")

            except (ValueError, IndexError) as error:
                print(f"  Omitido: {error}")

    # Guardar pares de fuego/geolocalizacion.
    campos = [
        "sensor", "fecha_hora",
        "archivo_fuego", "archivo_geo"
    ]

    with SALIDA.open(
        "w", newline="", encoding="utf-8-sig"
    ) as archivo:
        escritor = csv.DictWriter(
            archivo, fieldnames=campos
        )
        escritor.writeheader()
        escritor.writerows(registros)

    modis = [r for r in registros if r["sensor"] == "MODIS"]
    viirs = [r for r in registros if r["sensor"] == "VIIRS"]

    print("\n===== PAREJAS CANDIDATAS =====")
    candidatas = 0

    for m in modis:
        for v in viirs:
            diferencia = abs(
                fecha_hora(m["fecha_hora"])
                - fecha_hora(v["fecha_hora"])
            ).total_seconds() / 60

            if diferencia <= 30:
                candidatas += 1
                print(
                    f"MODIS {m['fecha_hora']} | "
                    f"VIIRS {v['fecha_hora']} | "
                    f"Diferencia: {diferencia:.0f} min"
                )

    print(f"\nRegistros completos: {len(registros)}")
    print(f"Parejas candidatas: {candidatas}")
    print(f"Manifiesto: {SALIDA}")
    print("No se descargaron archivos.")


if __name__ == "__main__":
    main()
