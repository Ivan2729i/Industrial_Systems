from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient


class FireSightAPITests(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()

    @patch("analysis.views.load_cells")
    def test_cells_success(self, mock_load):
        mock_load.return_value = [
            {
                "celda_h3": "874985003ffffff",
                "modis_fuego": 0,
                "viirs_fuego": 0
            }
        ]

        response = self.client.get(
            "/api/cells/",
            {"date": "2024-04-19"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 1)

    def test_cells_without_date(self):
        response = self.client.get("/api/cells/")
        self.assertEqual(response.status_code, 400)

    def test_cells_invalid_date(self):
        response = self.client.get(
            "/api/cells/",
            {"date": "incorrecta"}
        )
        self.assertEqual(response.status_code, 400)

    @patch("analysis.views.load_cells")
    def test_cells_missing_file(self, mock_load):
        mock_load.side_effect = FileNotFoundError

        response = self.client.get(
            "/api/cells/",
            {"date": "2024-05-01"}
        )

        self.assertEqual(response.status_code, 404)

    @patch("analysis.views.load_cells")
    def test_statistics_success(self, mock_load):
        mock_load.return_value = [
            {
                "modis_pixeles": 3,
                "viirs_pixeles": 8,
                "observacion_util_ambos": True,
                "modis_fuego": 0,
                "viirs_fuego": 0,
                "fuego_ambos": False,
                "deteccion_solo_modis": False,
                "deteccion_solo_viirs": False
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