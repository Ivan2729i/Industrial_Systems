
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from analysis import firms_detections


class FirmsCacheTests(SimpleTestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.directory = Path(self.temp_dir.name)

        self.modis_file = self.directory / "modis.csv"
        self.viirs_file = self.directory / "viirs.csv"
        self.cache_file = self.directory / "cache.json"

        self.modis_file.write_text("test", encoding="utf-8")
        self.viirs_file.write_text("test", encoding="utf-8")

        self.files_patch = patch.dict(
            firms_detections.FILES,
            {
                "MODIS": self.modis_file,
                "VIIRS": self.viirs_file,
            },
        )
        self.cache_patch = patch.object(
            firms_detections,
            "CACHE_FILE",
            self.cache_file,
        )

        self.files_patch.start()
        self.cache_patch.start()

        self.addCleanup(self.files_patch.stop)
        self.addCleanup(self.cache_patch.stop)

    @patch(
        "analysis.firms_detections.read_source_detections"
    )
    def test_build_cache(self, mock_read):
        mock_read.return_value = [
            {
                "id": "test-1",
                "sensor": "VIIRS",
                "acq_date": "2024-04-06",
                "satellite": "SNPP",
            }
        ]

        total = firms_detections.build_detections_cache()

        self.assertEqual(total, 1)
        self.assertTrue(self.cache_file.exists())

        payload = json.loads(
            self.cache_file.read_text(encoding="utf-8")
        )

        self.assertEqual(len(payload["records"]), 1)

    def test_missing_cache(self):
        with self.assertRaises(FileNotFoundError):
            firms_detections.read_detections()

    @patch(
        "analysis.firms_detections.read_source_detections"
    )
    def test_read_cache_with_filters(self, mock_read):
        mock_read.return_value = [
            {
                "id": "modis-1",
                "sensor": "MODIS",
                "acq_date": "2024-04-06",
                "satellite": "Aqua",
            },
            {
                "id": "viirs-1",
                "sensor": "VIIRS",
                "acq_date": "2024-04-06",
                "satellite": "SNPP",
            },
        ]

        firms_detections.build_detections_cache()

        result = firms_detections.read_detections(
            sensor="VIIRS",
            requested_date="2024-04-06",
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sensor"], "VIIRS")

    @patch(
        "analysis.firms_detections.read_source_detections"
    )
    def test_stale_cache(self, mock_read):
        mock_read.return_value = []

        firms_detections.build_detections_cache()

        self.modis_file.write_text(
            "datos modificados",
            encoding="utf-8",
        )

        with self.assertRaises(ValueError):
            firms_detections.read_detections()