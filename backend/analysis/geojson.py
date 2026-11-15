
import h3

from .validators import validate_cell


def cell_to_feature(cell):
    """
    Convierte una celda H3 validada
    en una entidad GeoJSON.
    """
    errors = validate_cell(cell)

    if errors:
        raise ValueError(
            f"Celda invalida: {errors}"
        )

    cell_id = cell["celda_h3"]

    # H3 devuelve (latitud, longitud)
    boundary = h3.cell_to_boundary(cell_id)

    # GeoJSON necesita [longitud, latitud]
    coordinates = [
        [longitude, latitude]
        for latitude, longitude in boundary
    ]

    # Los anillos GeoJSON deben cerrarse
    coordinates.append(coordinates[0])

    return {
        "type": "Feature",
        "id": cell_id,
        "geometry": {
            "type": "Polygon",
            "coordinates": [coordinates],
        },
        "properties": {
            "celda_h3": cell_id,
            "resolucion_h3": cell["resolucion_h3"],
            "modis_pixeles": cell["modis_pixeles"],
            "viirs_pixeles": cell["viirs_pixeles"],
            "modis_fuego": cell["modis_fuego"],
            "viirs_fuego": cell["viirs_fuego"],
            "observacion_util_ambos": cell[
                "observacion_util_ambos"
            ],
        },
    }


def cells_to_geojson(cells):
    """
    Construye una colección GeoJSON.
    """
    features = [
        cell_to_feature(cell)
        for cell in cells
    ]

    return {
        "type": "FeatureCollection",
        "features": features,
    }
