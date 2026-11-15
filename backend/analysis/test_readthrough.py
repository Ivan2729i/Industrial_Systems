from unittest.mock import patch, MagicMock
from datetime import date
from django.test import SimpleTestCase,TestCase
from django.core.cache import cache
from analysis.firms_service import ensure_day
from analysis.nasa import NASAError

class ReadThroughTests(SimpleTestCase):
    def setUp(self): cache.clear()

    @patch('analysis.firms_service.DetectionImport')
    @patch('analysis.firms_service.FIRMSClient')
    def test_excessive_region_does_not_download(self, client, imports):
        imports.objects.filter.return_value=[]
        self.assertEqual(ensure_day('modis',date(2024,4,16),'-100,0,100,60'),'REGION_DEMASIADO_GRANDE')
        client.assert_not_called()

    @patch('analysis.firms_service.DetectionImport')
    @patch('analysis.firms_service.FIRMSClient')
    def test_persisted_coverage_prevents_download(self, client, imports):
        imports.objects.filter.return_value=[MagicMock(area='world')]
        self.assertEqual(ensure_day('modis',date(2024,4,16),'-103,16,-98,19'),'CACHE_POSTGRESQL')
        client.assert_not_called()

    @patch('analysis.firms_service.call_command')
    @patch('analysis.firms_service.FIRMSClient')
    @patch('analysis.firms_service.DetectionImport')
    def test_success_and_repeated_request(self, imports, client, command):
        imports.objects.filter.return_value=[]
        client.return_value.availability.return_value=[{'min_date':'2024-01-01','max_date':'2024-12-31'}]
        for _ in range(2): self.assertEqual(ensure_day('viirs',date(2024,4,16),'-103,16,-98,19'),'NASA_RECUPERADO')
        command.assert_called_once()
        self.assertEqual(command.call_args.kwargs['source'],'VIIRS_SNPP_SP')

    @patch('analysis.firms_service.FIRMSClient',side_effect=NASAError('private'))
    @patch('analysis.firms_service.DetectionImport')
    def test_external_failure_is_bounded_and_sanitized(self, imports, client):
        imports.objects.filter.return_value=[]
        for _ in range(2): self.assertEqual(ensure_day('modis',date(2024,4,16),'-103,16,-98,19'),'ERROR_NASA_O_CREDENCIAL_NO_CONFIGURADA')
        client.assert_called_once()


class WorldValidationTests(TestCase):
    def test_world_large_interval_rejected_before_database(self):
        from analysis.detections_api import detections
        from rest_framework.test import APIRequestFactory
        r=detections(APIRequestFactory().get('/',{'sensor':'viirs','start_date':'2024-04-01','end_date':'2024-04-07','bbox':'world','retrieve':'true'}))
        self.assertEqual(r.status_code,400)
        self.assertIn('mundial',str(r.data))

    def test_antimeridian_split(self):
        from analysis.nasa import split_bounding_box
        self.assertEqual(len(split_bounding_box('170,-10,-170,10')),2)
