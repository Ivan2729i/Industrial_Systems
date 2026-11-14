
from pathlib import Path

import h5py
from pyhdf.SD import SD, SDC


BASE = Path(__file__).resolve().parent
CARPETA = BASE / "datos" / "level2"

ARCHIVOS = {
    "MODIS - Mascara de fuego": (
        "MYD14", "2020", "061"
    ),
    "MODIS - Geolocalizacion": (
        "MYD03", "2020", "061"
    ),
    "VIIRS - Mascara de fuego": (
        "VNP14IMG", "2030", "002"
    ),
    "VIIRS - Geolocalizacion": (
        "VNP03MODLL", "2030", "002"
    ),
}

PALABRAS_CLAVE = (
    "fire", "mask", "latitude", "longitude",
    "cloud", "quality", "scan", "time"
)


def buscar_archivo(producto, hora, version):
    patron = f"{producto}.A2024097.{hora}.{version}."

    encontrados = [
        archivo
        for archivo in CARPETA.iterdir()
        if archivo.is_file()
        and archivo.name.startswith(patron)
    ]

    if len(encontrados) != 1:
        raise ValueError(
            f"Se esperaba un archivo {patron}*, "
            f"pero se encontraron {len(encontrados)}"
        )

    return encontrados[0]


def mostrar_variables(variables):
    relevantes = [
        variable for variable in variables
        if any(
            palabra in variable[0].lower()
            for palabra in PALABRAS_CLAVE
        )
    ]

    print(f"Variables totales: {len(variables)}")
    print("\nVariables importantes:")

    for nombre, forma, tipo in relevantes:
        print(
            f"  {nombre}\n"
            f"    Dimensiones: {forma}\n"
            f"    Tipo: {tipo}"
        )

    if not relevantes:
        print("  No se encontraron nombres reconocidos.")

    print("\nPrimeras variables del archivo:")

    for nombre, forma, tipo in variables[:10]:
        print(f"  {nombre}: {forma} ({tipo})")


def inspeccionar_hdf4(ruta):
    archivo = SD(str(ruta), SDC.READ)

    try:
        variables = []

        for nombre, info in archivo.datasets().items():
            dimensiones = info[1]
            tipo = info[2]

            variables.append((
                nombre,
                dimensiones,
                tipo
            ))

        mostrar_variables(variables)

    finally:
        archivo.end()


def inspeccionar_hdf5(ruta):
    variables = []

    with h5py.File(ruta, "r") as archivo:

        print(
            "Grupos principales:",
            list(archivo.keys())
        )

        def visitar(nombre, objeto):
            if isinstance(objeto, h5py.Dataset):
                variables.append((
                    nombre,
                    objeto.shape,
                    str(objeto.dtype)
                ))

        archivo.visititems(visitar)

    mostrar_variables(variables)


def main():
    if not CARPETA.is_dir():
        raise FileNotFoundError(
            f"No existe la carpeta: {CARPETA}"
        )

    print("FIRESIGHT - INSPECCION LEVEL 2")
    print("=" * 55)

    errores = 0

    for descripcion, datos in ARCHIVOS.items():
        producto, hora, version = datos

        print(f"\n{'=' * 55}")
        print(descripcion)
        print("=" * 55)

        try:
            ruta = buscar_archivo(
                producto, hora, version
            )

            print(f"Archivo: {ruta.name}")
            print(
                f"Tamano: "
                f"{ruta.stat().st_size / 1024**2:.2f} MB"
            )

            if producto.startswith("MYD"):
                inspeccionar_hdf4(ruta)
            else:
                inspeccionar_hdf5(ruta)

            print("\nLECTURA CORRECTA")

        except Exception as error:
            errores += 1
            print(
                f"\nERROR: "
                f"{type(error).__name__}: {error}"
            )

    print("\n" + "=" * 55)
    print("INSPECCION TERMINADA")
    print(f"Archivos con errores: {errores}")
    print("=" * 55)


if __name__ == "__main__":
    main()
