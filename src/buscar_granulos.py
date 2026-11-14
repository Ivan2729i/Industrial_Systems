
import time
import earthaccess

# FireSight: archivos científicos ya verificados
FECHA = "A2024097"

PRODUCTOS = {
    "MYD14": ("061", "2020"),
    "MYD03": ("061", "2020"),
    "VNP14IMG": ("002", "2030"),
    "VNP03IMG": ("002", "2030"),
}

MAX_INTENTOS = 3


def buscar(producto, version, hora):
    patron = f"{producto}.{FECHA}.{hora}.{version}.*"

    print(f"\nBuscando: {patron}", flush=True)

    for intento in range(1, MAX_INTENTOS + 1):
        try:
            resultados = earthaccess.search_data(
                short_name=producto,
                granule_name=patron,
                count=10,
            )

            print(f"Encontrados: {len(resultados)}")

            for granulo in resultados:
                nombre = (
                    granulo.get("umm", {}).get("GranuleUR")
                    or granulo.get("meta", {}).get("native-id")
                    or "Nombre no disponible"
                )

                print(f"  {nombre}")

            return resultados, False

        except Exception as error:
            print(
                f"Intento {intento}/{MAX_INTENTOS} "
                f"fallido: {type(error).__name__}"
            )
            print(f"Detalle: {error}")

            if intento < MAX_INTENTOS:
                time.sleep(2 * intento)

    print(f"ERROR: No se pudo consultar {producto}")
    return [], True


def main():
    print("FIRESIGHT - PRUEBA DE API NASA")
    print("=" * 55)

    encontrados = {}
    fallidos = []

    for producto, (version, hora) in PRODUCTOS.items():
        resultados, error = buscar(
            producto, version, hora
        )

        encontrados[producto] = resultados

        if error:
            fallidos.append(producto)

    print("\n" + "=" * 55)
    print("RESUMEN DE CONSULTAS")

    for producto, resultados in encontrados.items():
        print(
            f"{producto}: {len(resultados)} archivos"
        )

    if fallidos:
        print(
            "\nConsultas fallidas por conexion u otro error:",
            ", ".join(fallidos)
        )
    elif all(encontrados.values()):
        print("\nTODOS LOS PRODUCTOS LOCALIZADOS")
    else:
        print(
            "\nHay productos sin resultados. "
            "Revisar filtros, version o catalogo."
        )

    print("\nNo se descargaron archivos.")


if __name__ == "__main__":
    main()
