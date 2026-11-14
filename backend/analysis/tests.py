from django.test import TestCase

from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient
import h3

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
