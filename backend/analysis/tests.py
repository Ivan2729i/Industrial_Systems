from django.test import TestCase

from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient


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
