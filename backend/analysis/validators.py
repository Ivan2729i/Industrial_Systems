
from datetime import date
import math

import h3


PIXEL_FIELDS = (
    "modis_pixeles",
    "modis_utiles",
    "modis_nubes",
    "modis_otros",
    "modis_fuego",
    "viirs_pixeles",
    "viirs_utiles",
    "viirs_nubes",
    "viirs_reflejo_solar",
    "viirs_otros",
    "viirs_fuego",
)

PERCENTAGE_FIELDS = (
    "modis_util_pct",
    "viirs_util_pct",
    "viirs_reflejo_solar_pct",
)


def validate_cell(cell):
    """
    Valida la estructura de una celda H3 procesada.

    Devuelve una lista de errores.
    Una lista vacía indica que pasó estas validaciones.
    """
    errors = []

    # 1. Validar identificador H3
    cell_id = cell.get("celda_h3")

    if not isinstance(cell_id, str) or not h3.is_valid_cell(cell_id):
        errors.append("Identificador H3 invalido")
    elif h3.get_resolution(cell_id) != 7:
        errors.append("La celda no tiene resolucion H3 7")

    # 2. Validar resolución declarada
    if cell.get("resolucion_h3") != 7:
        errors.append("Resolucion H3 declarada incorrecta")

    # 3. Validar fecha
    value = cell.get("fecha")

    try:
        parsed_date = date.fromisoformat(value)

        if parsed_date.isoformat() != value:
            errors.append("Formato de fecha incorrecto")

    except (ValueError, TypeError):
        errors.append("Fecha invalida")

    # 4. Validar conteos de píxeles
    for field in PIXEL_FIELDS:
        value = cell.get(field)

        if type(value) is not int or value < 0:
            errors.append(f"Conteo invalido: {field}")

    # 5. Validar porcentajes
    for field in PERCENTAGE_FIELDS:
        value = cell.get(field)

        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= 100
        ):
            errors.append(f"Porcentaje invalido: {field}")

    # 6. Validar coherencia básica
    for sensor in ("modis", "viirs"):
        total = cell.get(f"{sensor}_pixeles")
        useful = cell.get(f"{sensor}_utiles")
        fire = cell.get(f"{sensor}_fuego")

        if all(
            type(value) is int and value >= 0
            for value in (total, useful, fire)
        ):
            if useful > total:
                errors.append(
                    f"Pixeles utiles exceden total: {sensor}"
                )

            if fire > total:
                errors.append(
                    f"Pixeles de fuego exceden total: {sensor}"
                )

    return errors


def validate_cells(cells):
    """
    Valida múltiples celdas y genera un reporte.
    """
    invalid_rows = []

    for index, cell in enumerate(cells, start=1):
        errors = validate_cell(cell)

        if errors:
            invalid_rows.append({
                "row": index,
                "h3_cell": cell.get("celda_h3"),
                "errors": errors,
            })

    return {
        "total": len(cells),
        "valid": len(cells) - len(invalid_rows),
        "invalid": len(invalid_rows),
        "errors": invalid_rows,
    }
