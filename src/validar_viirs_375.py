
from pathlib import Path

import h3
import h5py
import numpy as np

BASE = Path(__file__).resolve().parent / "datos" / "level2"

SUR, NORTE = 19.35, 19.60
OESTE, ESTE = -102.15, -101.80


def encontrar(prefijo):
    archivos = list(BASE.glob(prefijo + "*"))

    if len(archivos) != 1:
        raise RuntimeError(
            f"{prefijo}: se esperaba un archivo, "
            f"encontrados {len(archivos)}"
        )

    return archivos[0]


def localizar_coordenadas(archivo, forma):
    candidatos = {"latitude": [], "longitude": []}

    def visitar(nombre, objeto):
        if not isinstance(objeto, h5py.Dataset):
            return

        campo = nombre.split("/")[-1].lower()

        if campo in candidatos and objeto.shape == forma:
            candidatos[campo].append(objeto)

    archivo.visititems(visitar)

    if any(len(lista) != 1 for lista in candidatos.values()):
        raise ValueError(
            "No se encontro una pareja unica de coordenadas "
            f"con dimensiones {forma}. "
            "Revisar estructura de VNP03IMG."
        )

    return (
        candidatos["latitude"][0],
        candidatos["longitude"][0],
    )


def distancia_m(lat1, lon1, lat2, lon2):
    r = 6371000.0

    a1 = np.radians(lat1)
    a2 = np.radians(lat2)
    dy = a2 - a1
    dx = np.radians(lon2 - lon1)

    a = (
        np.sin(dy / 2) ** 2
        + np.cos(a1) * np.cos(a2)
        * np.sin(dx / 2) ** 2
    )

    return 2 * r * np.arcsin(
        np.sqrt(np.clip(a, 0, 1))
    )


def main():
    fire_path = encontrar("VNP14IMG.A2024097.2030.002.")
    geo_path = encontrar("VNP03IMG.A2024097.2030.002.")

    print("FIRESIGHT - VALIDACION VIIRS 375 M")
    print("=" * 50)

    with h5py.File(fire_path, "r") as fire, \
         h5py.File(geo_path, "r") as geo:

        forma_mascara = fire["fire mask"].shape

        print("Mascara VIIRS:", forma_mascara)

        lat_ds, lon_ds = localizar_coordenadas(
            geo, forma_mascara
        )

        print("Geolocalizacion:", lat_ds.shape)
        print("Latitud dataset:", lat_ds.name)
        print("Longitud dataset:", lon_ds.name)

        filas = fire["FP_line"][:].astype(int)
        columnas = fire["FP_sample"][:].astype(int)

        lat_original = fire["FP_latitude"][:]
        lon_original = fire["FP_longitude"][:]

        if not (
            len(filas) == len(columnas)
            == len(lat_original) == len(lon_original)
        ):
            raise ValueError(
                "Las listas de detecciones son incompatibles"
            )

        if not (
            np.all((filas >= 0) & (filas < forma_mascara[0]))
            and np.all(
                (columnas >= 0)
                & (columnas < forma_mascara[1])
            )
        ):
            raise ValueError("Indices de deteccion invalidos")

        # Leer unicamente las coordenadas de los focos.
        # No cargamos las matrices mundiales completas.
        lat_375 = np.array([
            lat_ds[int(f), int(c)]
            for f, c in zip(filas, columnas)
        ])

        lon_375 = np.array([
            lon_ds[int(f), int(c)]
            for f, c in zip(filas, columnas)
        ])

    validos = (
        np.isfinite(lat_375)
        & np.isfinite(lon_375)
        & (lat_375 >= -90)
        & (lat_375 <= 90)
        & (lon_375 >= -180)
        & (lon_375 <= 180)
    )

    region = (
        validos
        & (lat_original >= SUR)
        & (lat_original <= NORTE)
        & (lon_original >= OESTE)
        & (lon_original <= ESTE)
    )

    print(f"\nDetecciones totales: {len(filas)}")
    print(f"Coordenadas validas: {validos.sum()}")
    print(f"Detecciones en Michoacan: {region.sum()}")

    for nombre, seleccion in [
        ("Segmento completo", validos),
        ("Michoacan", region),
    ]:
        indices = np.flatnonzero(seleccion)

        print(f"\n===== {nombre} =====")

        if not len(indices):
            print("Sin detecciones.")
            continue

        distancias = distancia_m(
            lat_original[indices],
            lon_original[indices],
            lat_375[indices],
            lon_375[indices]
        )

        print(f"Detecciones: {len(indices)}")
        print(f"Distancia mediana: {np.median(distancias):.2f} m")
        print(f"Percentil 95: {np.percentile(distancias, 95):.2f} m")
        print(f"Distancia maxima: {np.max(distancias):.2f} m")

        for res in [6, 7, 8]:
            cambios = 0

            for i in indices:
                celda_original = h3.latlng_to_cell(
                    float(lat_original[i]),
                    float(lon_original[i]),
                    res
                )

                celda_375 = h3.latlng_to_cell(
                    float(lat_375[i]),
                    float(lon_375[i]),
                    res
                )

                if celda_original != celda_375:
                    cambios += 1

            porcentaje = 100 * cambios / len(indices)

            print(
                f"H3 {res}: {cambios} cambios "
                f"({porcentaje:.2f}%)"
            )

    print("\nVALIDACION FINALIZADA")


if __name__ == "__main__":
    main()
