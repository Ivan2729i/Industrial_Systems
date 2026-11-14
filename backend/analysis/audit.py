
import math
from datetime import datetime
import h3


def audit_consistency(spatial_cells, temporal_cells):
    """
    Audita la consistencia estructural entre
    resultados espaciales y temporales.

    No determina comparabilidad cientifica.
    """

    issues = []

    def index_cells(records, source):
        indexed = {}

        for row_number, cell in enumerate(records, start=1):
            cell_id = cell.get("celda_h3")

            if (
                not isinstance(cell_id, str)
                or not h3.is_valid_cell(cell_id)
            ):
                issues.append({
                    "source": source,
                    "row": row_number,
                    "type": "invalid_h3",
                    "cell": cell_id,
                })
                continue

            if h3.get_resolution(cell_id) != 7:
                issues.append({
                    "source": source,
                    "row": row_number,
                    "type": "invalid_resolution",
                    "cell": cell_id,
                })

            if cell_id in indexed:
                issues.append({
                    "source": source,
                    "row": row_number,
                    "type": "duplicate_h3",
                    "cell": cell_id,
                })
            else:
                indexed[cell_id] = cell

        return indexed

    spatial = index_cells(spatial_cells, "spatial")
    temporal = index_cells(temporal_cells, "temporal")

    spatial_ids = set(spatial)
    temporal_ids = set(temporal)

    missing_in_spatial = sorted(
        temporal_ids - spatial_ids
    )

    without_temporal = sorted(
        spatial_ids - temporal_ids
    )

    for cell_id, cell in temporal.items():
        difference = cell.get("diferencia_min")

        try:
            modis_time = datetime.strptime(
                cell["modis_utc"],
                "%Y-%m-%d %H:%M:%S.%f UTC"
            )

            viirs_time = datetime.strptime(
                cell["viirs_utc"],
                "%Y-%m-%d %H:%M:%S.%f UTC"
            )

            calculated_difference = (
                abs((viirs_time - modis_time).total_seconds())
                / 60
            )

            if (
                type(difference) in (int, float)
                and math.isfinite(difference)
                and difference >= 0
                and abs(calculated_difference - difference) > 0.001
            ):
                issues.append({
                    "source": "temporal",
                    "type": "time_difference_mismatch",
                    "cell": cell_id,
                    "reported_difference": difference,
                    "calculated_difference": round(
                        calculated_difference, 6
                    ),
                })

        except (ValueError, TypeError, KeyError):
            issues.append({
                "source": "temporal",
                "type": "invalid_timestamp",
                "cell": cell_id,
            })


        if (
            type(difference) not in (float, int)
            or not math.isfinite(difference)
            or difference < 0
        ):
            issues.append({
                "source": "temporal",
                "type": "invalid_time_difference",
                "cell": cell_id,
            })

    for cell_id in missing_in_spatial:
        issues.append({
            "source": "temporal",
            "type": "missing_in_spatial",
            "cell": cell_id,
        })

    return {
        "spatial_cells": len(spatial_cells),
        "temporal_cells": len(temporal_cells),
        "shared_cells": len(spatial_ids & temporal_ids),
        "temporal_cells_missing_in_spatial": len(
            missing_in_spatial
        ),
        "spatial_cells_without_temporal": len(
            without_temporal
        ),
        "issues_count": len(issues),
        "issues": issues,
        "structural_status": (
            "passed" if not issues else "failed"
        ),
        "scientific_validation": "pending",
    }
