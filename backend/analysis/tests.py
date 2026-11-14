from django.test import TestCase
from .pilot_comparisons import load_pilot_comparisons
from unittest.mock import patch
from .comparison import build_comparison
from django.test import SimpleTestCase
from rest_framework.test import APIClient
import h3
from .pilot_comparisons import (
    convert_value,
    filter_pilot_comparisons,
    summarize_pilot,
)
from .geojson import cell_to_feature
from .services import load_cells
from .validators import validate_cell, validate_cells


class CellsAPITests(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()

    @patch("analysis.views.load_cells")
    def test_cells_returns_data(self, mock_load):
        mock_load.return_value = [
            {
                "celda_h3": "874985003ffffff",
                "modis_fuego": 0,
                "viirs_fuego": 0,
            }
        ]

        response = self.client.get(
            "/api/cells/",
            {"date": "2024-04-19"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(len(response.data["data"]), 1)

    def test_cells_requires_date(self):
        response = self.client.get("/api/cells/")

        self.assertEqual(response.status_code, 400)

    def test_cells_rejects_invalid_date(self):
        response = self.client.get(
            "/api/cells/",
            {"date": "fecha-invalida"},
        )

        self.assertEqual(response.status_code, 400)

    @patch("analysis.views.load_cells")
    def test_cells_returns_404_if_missing(
        self, mock_load
    ):
        mock_load.side_effect = FileNotFoundError

        response = self.client.get(
            "/api/cells/",
            {"date": "2024-05-01"},
        )

        self.assertEqual(response.status_code, 404)

class GeoJSONTests(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()

    @patch("analysis.views.load_cells")
    def test_geojson_endpoint_empty(self, mock_load):
        mock_load.return_value = []

        response = self.client.get(
            "/api/geojson/",
            {"date": "2024-04-19"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["type"],
            "FeatureCollection"
        )
        self.assertEqual(
            response.data["features"],
            []
        )

    def test_geojson_polygon(self):
        cell_id = h3.latlng_to_cell(
            19.5, -101.2, 7
        )

        cell = {
            "fecha": "2024-04-19",
            "celda_h3": cell_id,
            "resolucion_h3": 7,
            "modis_pixeles": 5,
            "modis_utiles": 5,
            "modis_nubes": 0,
            "modis_otros": 0,
            "modis_fuego": 0,
            "viirs_pixeles": 10,
            "viirs_utiles": 10,
            "viirs_nubes": 0,
            "viirs_reflejo_solar": 0,
            "viirs_otros": 0,
            "viirs_fuego": 0,
            "modis_util_pct": 100.0,
            "viirs_util_pct": 100.0,
            "viirs_reflejo_solar_pct": 0.0,
            "observacion_util_ambos": True,
        }

        feature = cell_to_feature(cell)

        self.assertEqual(
            feature["geometry"]["type"],
            "Polygon"
        )

        coordinates = feature[
            "geometry"
        ]["coordinates"][0]

        self.assertEqual(
            coordinates[0],
            coordinates[-1]
        )


from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient


class StatisticsAPITests(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()

    @patch("analysis.views.load_cells")
    def test_statistics_returns_data(self, mock_load):
        mock_load.return_value = [
            {
                "modis_pixeles": 5,
                "viirs_pixeles": 10,
                "observacion_util_ambos": True,
                "modis_fuego": 0,
                "viirs_fuego": 0,
                "fuego_ambos": False,
                "deteccion_solo_modis": False,
                "deteccion_solo_viirs": False,
            }
        ]

        response = self.client.get(
            "/api/statistics/",
            {"date": "2024-04-19"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["statistics"]["total_cells"],
            1
        )
        self.assertEqual(
            response.data["statistics"]["both_observed_cells"],
            1
        )

    def test_statistics_requires_date(self):
        response = self.client.get(
            "/api/statistics/"
        )

        self.assertEqual(response.status_code, 400)

    def test_statistics_rejects_invalid_date(self):
        response = self.client.get(
            "/api/statistics/",
            {"date": "incorrecta"}
        )

        self.assertEqual(response.status_code, 400)


class AvailableDatesTests(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()

    @patch("analysis.views.get_available_dates")
    def test_available_dates_success(self, mock_dates):
        mock_dates.return_value = [
            "2024-04-08",
            "2024-04-19",
        ]

        response = self.client.get(
            "/api/available-dates/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(
            response.data["available_dates"],
            ["2024-04-08", "2024-04-19"],
        )

    def test_available_dates_service(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch as mock_patch
        from .services import get_available_dates

        with TemporaryDirectory() as directory:
            root = Path(directory)

            (root / "analisis_celdas_2024-04-19.csv").touch()
            (root / "analisis_celdas_2024-04-08.csv").touch()
            (root / "analisis_celdas_2024-99-99.csv").touch()

            with mock_patch(
                "analysis.services.CSV_DIRECTORY",
                root,
            ):
                dates = get_available_dates()

        self.assertEqual(
            dates,
            ["2024-04-08", "2024-04-19"],
        )


from .coverage import calculate_coverage


class CoverageTests(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()

    def test_calculate_coverage(self):
        cells = [
            {
                "modis_pixeles": 5,
                "viirs_pixeles": 10,
                "observacion_util_ambos": True,
                "modis_fuego": 0,
                "viirs_fuego": 1,
            },
            {
                "modis_pixeles": 0,
                "viirs_pixeles": 8,
                "observacion_util_ambos": False,
                "modis_fuego": 0,
                "viirs_fuego": 0,
            },
        ]

        result = calculate_coverage(cells)

        self.assertEqual(result["total_cells"], 2)
        self.assertEqual(
            result["coverage"]["modis_observed_cells"],
            1,
        )
        self.assertEqual(
            result["coverage"]["viirs_observed_cells"],
            2,
        )
        self.assertEqual(
            result["coverage"]["both_usable_cells"],
            1,
        )
        self.assertEqual(
            result["fire"]["viirs_fire_cells"],
            1,
        )
        self.assertEqual(
            result["temporal_comparability"]["status"],
            "not_evaluated",
        )

    @patch("analysis.views.load_cells")
    def test_coverage_endpoint(self, mock_load):
        mock_load.return_value = []

        response = self.client.get(
            "/api/coverage/",
            {"date": "2024-04-19"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_cells"], 0)

    def test_coverage_requires_date(self):
        response = self.client.get("/api/coverage/")
        self.assertEqual(response.status_code, 400)

    def test_coverage_invalid_date(self):
        response = self.client.get(
            "/api/coverage/",
            {"date": "incorrecta"},
        )
        self.assertEqual(response.status_code, 400)


from .temporal import calculate_temporal_summary


class TemporalAPITests(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()

    def test_temporal_summary(self):
        records = [
            {"diferencia_min": 7.686},
            {"diferencia_min": 7.715},
            {"diferencia_min": 7.750},
        ]

        result = calculate_temporal_summary(records)

        self.assertEqual(result["total_cells"], 3)
        self.assertEqual(
            result["median_difference_min"], 7.715
        )

    @patch("analysis.views.load_temporal_data")
    def test_temporal_endpoint(self, mock_load):
        mock_load.return_value = [
            {"diferencia_min": 7.715}
        ]

        response = self.client.get(
            "/api/temporal/",
            {"date": "2024-04-19"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["summary"]["total_cells"], 1
        )

    def test_temporal_requires_date(self):
        response = self.client.get("/api/temporal/")
        self.assertEqual(response.status_code, 400)

    def test_temporal_invalid_date(self):
        response = self.client.get(
            "/api/temporal/",
            {"date": "incorrecta"},
        )
        self.assertEqual(response.status_code, 400)


from .audit import audit_consistency


class AuditTests(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()

    def test_consistent_cells(self):
        cell_id = h3.latlng_to_cell(
            19.5, -101.2, 7
        )

        spatial = [
            {"celda_h3": cell_id}
        ]

        temporal = [
            {
                "celda_h3": cell_id,
                "modis_utc": "2024-04-19 08:30:00.000 UTC",
                "viirs_utc": "2024-04-19 08:37:42.900 UTC",
                "diferencia_min": 7.715,
            }
        ]

        report = audit_consistency(
            spatial,
            temporal
        )

        self.assertEqual(
            report["shared_cells"], 1
        )

        self.assertEqual(
            report["issues_count"], 0,
            report["issues"]
        )

        self.assertEqual(
            report["structural_status"],
            "passed"
        )

    def test_invalid_temporal_difference(self):
        cell_id = h3.latlng_to_cell(19.5, -101.2, 7)

        report = audit_consistency(
            [{"celda_h3": cell_id}],
            [{
                "celda_h3": cell_id,
                "diferencia_min": -5,
            }],
        )

        self.assertEqual(
            report["structural_status"], "failed"
        )

    @patch("analysis.views.load_cells")
    @patch("analysis.views.load_temporal_data")
    def test_audit_endpoint(
        self,
        mock_temporal,
        mock_spatial,
    ):
        mock_spatial.return_value = []
        mock_temporal.return_value = []

        response = self.client.get(
            "/api/audit/",
            {"date": "2024-04-19"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["structural_status"],
            "passed",
        )
        self.assertEqual(
            response.data["scientific_validation"],
            "pending",
        )

        def test_detect_time_difference_mismatch(self):
            cell_id = h3.latlng_to_cell(
                19.5, -101.2, 7
            )

            spatial = [
                {"celda_h3": cell_id}
            ]

            temporal = [
                {
                    "celda_h3": cell_id,
                    "modis_utc": "2024-04-19 08:30:00.000 UTC",
                    "viirs_utc": "2024-04-19 08:40:00.000 UTC",
                    "diferencia_min": 5.0,
                }
            ]

            report = audit_consistency(spatial, temporal)

            issue_types = [
                issue["type"]
                for issue in report["issues"]
            ]

            self.assertIn(
                "time_difference_mismatch",
                issue_types
            )

    def test_detect_time_difference_mismatch(self):
        cell_id = h3.latlng_to_cell(
            19.5, -101.2, 7
        )

        report = audit_consistency(
            [{"celda_h3": cell_id}],
            [{
                "celda_h3": cell_id,
                "modis_utc": "2024-04-19 08:30:00.000 UTC",
                "viirs_utc": "2024-04-19 08:40:00.000 UTC",
                "diferencia_min": 5.0,
            }]
        )

        issue_types = [
            issue["type"]
            for issue in report["issues"]
        ]

        self.assertIn(
            "time_difference_mismatch",
            issue_types
        )

class ComparisonTests(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()
        self.cell_id = h3.latlng_to_cell(
            19.5, -101.2, 7
        )

    def test_comparison_with_temporal_data(self):
        spatial = [{
            "celda_h3": self.cell_id,
            "modis_pixeles": 5,
            "viirs_pixeles": 10,
            "modis_fuego": 0,
            "viirs_fuego": 0,
            "observacion_util_ambos": True,
        }]

        temporal = [{
            "celda_h3": self.cell_id,
            "diferencia_min": 7.715,
            "modis_utc": "2024-04-19 08:30:00.000 UTC",
            "viirs_utc": "2024-04-19 08:37:42.900 UTC",
        }]

        result = build_comparison(spatial, temporal)
        cell = result["cells"][0]

        self.assertTrue(cell["has_temporal_data"])
        self.assertEqual(
            cell["temporal_difference_min"], 7.715
        )
        self.assertIsNone(cell["comparable"])

    def test_comparison_without_temporal_data(self):
        spatial = [{
            "celda_h3": self.cell_id,
            "modis_pixeles": 0,
            "viirs_pixeles": 8,
            "modis_fuego": 0,
            "viirs_fuego": 0,
            "observacion_util_ambos": False,
        }]

        result = build_comparison(spatial, [])
        cell = result["cells"][0]

        self.assertFalse(cell["has_temporal_data"])
        self.assertIsNone(
            cell["temporal_difference_min"]
        )
        self.assertEqual(
            cell["temporal_validation"],
            "not_available"
        )
        self.assertIsNone(cell["comparable"])

    def test_duplicate_spatial_cell(self):
        spatial = [{
            "celda_h3": self.cell_id,
            "modis_pixeles": 5,
            "viirs_pixeles": 10,
            "modis_fuego": 0,
            "viirs_fuego": 0,
            "observacion_util_ambos": True,
        }]

        with self.assertRaises(ValueError):
            build_comparison(spatial * 2, [])

    @patch("analysis.views.load_cells")
    @patch("analysis.views.load_temporal_data")
    def test_comparison_endpoint(
        self,
        mock_temporal,
        mock_spatial,
    ):
        mock_spatial.return_value = []
        mock_temporal.return_value = []

        response = self.client.get(
            "/api/comparison/",
            {"date": "2024-04-19"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["scientific_validation"],
            "pending"
        )
        self.assertEqual(
            response.data["summary"]["total_cells"],
            0
        )

    def test_comparison_requires_date(self):
        response = self.client.get(
            "/api/comparison/"
        )
        self.assertEqual(response.status_code, 400)

    def test_comparison_invalid_date(self):
        response = self.client.get(
            "/api/comparison/",
            {"date": "incorrecta"},
        )
        self.assertEqual(response.status_code, 400)


class PilotComparisonsTests(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()

        self.records = [
            {
                "fecha": "2024-04-06",
                "modis_sobrevuelo": "A2024097.0925",
                "viirs_sobrevuelo": "A2024097.0918",
                "celda_h3": "example-1",
                "estado_comparacion": "candidata_experimental",
                "comparacion_candidata": True,
                "metodologia_validada": False,
                "modis_fuego": 0,
                "viirs_fuego": 1,
            },
            {
                "fecha": "2024-04-08",
                "modis_sobrevuelo": "A2024099.2000",
                "viirs_sobrevuelo": "A2024099.1954",
                "celda_h3": "example-2",
                "estado_comparacion": "fuera_de_umbrales",
                "comparacion_candidata": False,
                "metodologia_validada": False,
                "modis_fuego": 0,
                "viirs_fuego": 0,
            },
        ]

    def test_missing_values_are_null(self):
        self.assertIsNone(
            convert_value("diferencia_min", "")
        )
        self.assertIsNone(
            convert_value("qa_originales", "")
        )
        self.assertIsNone(
            convert_value("viirs_detecta_sin_bowtie", "")
        )

    def test_filter_by_date_and_status(self):
        result = filter_pilot_comparisons(
            self.records,
            date="2024-04-06",
            status="candidata_experimental",
        )

        self.assertEqual(len(result), 1)

    def test_summary(self):
        summary = summarize_pilot(self.records)

        self.assertEqual(summary["total_records"], 2)
        self.assertEqual(
            summary["experimental_candidates"], 1
        )
        self.assertEqual(
            summary["validated_records"], 0
        )

    @patch("analysis.views.load_pilot_comparisons")
    def test_endpoint(self, mock_load):
        mock_load.return_value = self.records

        response = self.client.get(
            "/api/pilot-comparisons/",
            {"date": "2024-04-06"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["summary"]["total_records"], 1
        )
        self.assertEqual(len(response.data["data"]), 1)

    def test_invalid_status(self):
        response = self.client.get(
            "/api/pilot-comparisons/",
            {"status": "validada"},
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_pagination(self):
        response = self.client.get(
            "/api/pilot-comparisons/",
            {"limit": "-10"},
        )

        self.assertEqual(response.status_code, 400)


class PilotRealDataTests(SimpleTestCase):

    def test_real_pilot_data(self):
        records = load_pilot_comparisons()

        self.assertEqual(len(records), 585)

        keys = [
            (
                row["modis_sobrevuelo"],
                row["viirs_sobrevuelo"],
                row["celda_h3"],
            )
            for row in records
        ]

        self.assertEqual(len(keys), len(set(keys)))

        candidates = sum(
            row["comparacion_candidata"] is True
            for row in records
        )

        self.assertEqual(candidates, 180)

        self.assertTrue(
            all(
                row["metodologia_validada"] is False
                for row in records
            )
        )
