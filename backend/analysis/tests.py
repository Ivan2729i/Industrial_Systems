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
