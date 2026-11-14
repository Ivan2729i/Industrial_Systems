
import os
from pathlib import Path
from urllib.parse import urlsplit, unquote

import earthaccess
from dotenv import load_dotenv


# ============================================
# CONFIGURACION DE FIRESIGHT
# ============================================

BASE = Path(__file__).resolve().parent
RAIZ = BASE.parent

# Archivo .env ubicado en la raiz del proyecto
ENV_PATH = RAIZ / ".env"

if not ENV_PATH.is_file():
    raise FileNotFoundError(
        f"No se encontro el archivo .env en: {ENV_PATH}"
    )

load_dotenv(dotenv_path=ENV_PATH)

# Verificar credenciales sin mostrarlas
if not os.getenv("EARTHDATA_USERNAME"):
    raise RuntimeError(
        "Falta EARTHDATA_USERNAME en el archivo .env"
    )

if not os.getenv("EARTHDATA_PASSWORD"):
    raise RuntimeError(
        "Falta EARTHDATA_PASSWORD en el archivo .env"
    )


DESTINO = BASE / "datos" / "lotes" / "2024-04-06-noche"

PRODUCTOS = [
    ("MYD14", "A2024097.0925", "061"),
    ("MYD03", "A2024097.0925", "061"),
    ("VNP14IMG", "A2024097.0918", "002"),
    ("VNP03IMG", "A2024097.0918", "002"),
]



# ============================================
# BUSQUEDA DE ARCHIVOS
# ============================================

def buscar_granulo(producto, fecha_hora, version):
    prefijo = f"{producto}.{fecha_hora}.{version}."

    print(f"\nBuscando: {prefijo}*", flush=True)

    # No filtrar version en CMR:
    # anteriormente causaba resultados vacios
    # en algunos productos de geolocalizacion.
    resultados = earthaccess.search_data(
        short_name=producto,
        granule_name=prefijo + "*",
        count=10,
    )

    coincidencias = []

    for granulo in resultados:
        enlaces = granulo.data_links(access="external")

        nombres = [
            unquote(urlsplit(url).path.rsplit("/", 1)[-1])
            for url in enlaces
        ]

        if any(
            nombre.startswith(prefijo)
            for nombre in nombres
        ):
            coincidencias.append(granulo)

    if len(coincidencias) != 1:
        raise RuntimeError(
            f"{producto}: se esperaba exactamente "
            f"un archivo, encontrados: {len(coincidencias)}"
        )

    print(f"Archivo {producto} localizado", flush=True)

    return coincidencias[0]


# ============================================
# AUTENTICACION NASA
# ============================================

def autenticar_nasa():
    print("\nAutenticando con NASA Earthdata...", flush=True)

    auth = earthaccess.login(strategy="environment")

    if not auth.authenticated:
        raise RuntimeError(
            "NASA Earthdata rechazo la autenticacion. "
            "Revisa las credenciales del archivo .env."
        )

    print("Autenticacion correcta", flush=True)


# ============================================
# DESCARGA
# ============================================

def descargar_archivos(granulos):
    DESTINO.mkdir(parents=True, exist_ok=True)

    print("\nIniciando descarga de archivos...", flush=True)

    rutas = earthaccess.download(
        granulos,
        local_path=str(DESTINO),
        threads=2,
    )

    if len(rutas) != len(PRODUCTOS):
        raise RuntimeError(
            f"Se esperaban {len(PRODUCTOS)} archivos, "
            f"pero se recibieron {len(rutas)} rutas."
        )

    print("\n===== ARCHIVOS DESCARGADOS =====")

    for ruta in rutas:
        archivo = Path(ruta)

        if not archivo.is_file():
            raise FileNotFoundError(
                f"No se encontro: {archivo}"
            )

        tamaño_bytes = archivo.stat().st_size

        if tamaño_bytes == 0:
            raise RuntimeError(
                f"El archivo esta vacio: {archivo.name}"
            )

        tamaño_mb = tamaño_bytes / (1024 ** 2)

        print(
            f"{archivo.name} | {tamaño_mb:.2f} MB",
            flush=True
        )

    print("\nDESCARGA FINALIZADA")
    print(f"Directorio: {DESTINO}")

    print(
        "\nImportante: las descargas deben validarse "
        "como archivos cientificos antes de procesarse."
    )


# ============================================
# EJECUCION PRINCIPAL
# ============================================

def main():
    print("=" * 55)
    print("FIRESIGHT - DESCARGA AUTOMATICA NASA")
    print("Fecha: 2024-04-08")
    print("=" * 55)

    print("\nArchivo .env localizado correctamente")

    granulos = []

    for producto, fecha_hora, version in PRODUCTOS:
        granulo = buscar_granulo(
            producto,
            fecha_hora,
            version
        )
        granulos.append(granulo)

    print("\nLos cuatro productos fueron localizados.")

    autenticar_nasa()
    descargar_archivos(granulos)


if __name__ == "__main__":
    main()
