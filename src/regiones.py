
# FIRESIGHT - CONFIGURACION GEOGRAFICA
#
# Coordenadas en grados decimales WGS84.
# Cada region tiene un identificador estable.
# Resolucion H3 inicial: 7.

RESOLUCION_H3 = 7

REGIONES = {
    "michoacan_piloto": {
        "nombre": "Michoacan - piloto inicial",
        "sur": 19.35,
        "norte": 19.60,
        "oeste": -102.15,
        "este": -101.80,
    },

    "guerrero": {
        "nombre": "Guerrero - zona de prueba",
        "sur": 16.95,
        "norte": 17.55,
        "oeste": -100.05,
        "este": -99.45,
    },

    "tabasco_chiapas": {
        "nombre": "Tabasco-Chiapas - zona de prueba",
        "sur": 17.45,
        "norte": 18.05,
        "oeste": -93.55,
        "este": -92.95,
    },
}


def obtener_region(identificador: str) -> dict:
    if identificador not in REGIONES:
        disponibles = ", ".join(REGIONES)

        raise ValueError(
            f"Region desconocida: {identificador}. "
            f"Disponibles: {disponibles}"
        )

    return REGIONES[identificador].copy()


def obtener_bbox(identificador: str) -> tuple:
    region = obtener_region(identificador)

    return (
        region["oeste"],
        region["sur"],
        region["este"],
        region["norte"],
    )
