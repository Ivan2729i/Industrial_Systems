from unittest.mock import patch
from urllib.error import HTTPError
from django.test import SimpleTestCase
from analysis.nasa import bounding_box, open_nasa, NASAError, SOURCES

class NASAConnectorTests(SimpleTestCase):
    def test_bbox(self):
        self.assertEqual(bounding_box('world'),'world')
        self.assertEqual(bounding_box('-180,-90,180,90'),'-180.0,-90.0,180.0,90.0')
        for invalid in ['nan,0,1,2','180,0,-180,10','0,0,1,91','a']:
            with self.assertRaises(ValueError):bounding_box(invalid)
    def test_no_secret_in_errors(self):
        for code in [401,403,429,500,503]:
            with patch('analysis.nasa.urlopen',side_effect=HTTPError('https://example/SECRET',code,'SECRET',{},None)):
                with self.assertRaises(NASAError) as context:open_nasa('https://example/SECRET')
                self.assertNotIn('SECRET',str(context.exception))
                self.assertIn(str(code),str(context.exception))
    def test_sources(self):
        self.assertEqual(len(SOURCES),8)
        self.assertIn('VIIRS_NOAA21_SP',SOURCES)


class DetectionAPIValidationTests(SimpleTestCase):
    def test_parameters_rejected_before_query(self):
        from rest_framework.test import APIRequestFactory
        from analysis.detections_api import detections
        for params in [{},{'sensor':'bad','start_date':'2024-04-16','end_date':'2024-04-16'},{'sensor':'modis','start_date':'2024-04-17','end_date':'2024-04-16'}]:
            response=detections(APIRequestFactory().get('/api/v1/detections/',params))
            self.assertEqual(response.status_code,400)


from django.test import TestCase
from datetime import datetime, timezone
from analysis.models import SatelliteSource, DetectionImport, FireDetection
from rest_framework.test import APIClient

class GlobalDetectionTests(TestCase):
    def setUp(self):
        source=SatelliteSource.objects.create(id='MODIS_SP',sensor='modis')
        run=DetectionImport.objects.create(source=source,date='2024-04-16',area='world',status='DATOS_DISPONIBLES',records=3)
        for i,(lon,lat) in enumerate([(20,-5),(100,20),(-55,-15)]):
            FireDetection.objects.create(fingerprint=str(i),source=source,data_import=run,observed_at=datetime(2024,4,16,0,30,tzinfo=timezone.utc),latitude=lat,longitude=lon,satellite='Aqua',original={'confidence':'80'})
        self.client=APIClient()
        self.params={'sensor':'modis','start_date':'2024-04-16','end_date':'2024-04-16'}
    def test_utc_and_aggregation(self):
        r=self.client.get('/api/v1/detections/',{**self.params,'aggregate':'true'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.data['count'],3)
        self.assertEqual(sum(g['count'] for g in r.data['results']),3)
    def test_bbox_sensor_satellite(self):
        r=self.client.get('/api/v1/detections/',{**self.params,'bbox':'10,-15,35,10','satellite':'aqua'})
        self.assertEqual(r.data['count'],1)
        self.assertEqual(r.data['results'][0]['longitude'],20)
        self.assertEqual(self.client.get('/api/v1/detections/',{**self.params,'sensor':'viirs'}).data['count'],0)
        self.assertEqual(self.client.post('/api/v1/detections/',{}).status_code,405)
    def test_dates_and_pagination(self):
        self.assertEqual(str(self.client.get('/api/v1/detections/dates/').data['dates'][0]),'2024-04-16')
        r=self.client.get('/api/v1/detections/',{**self.params,'limit':1})
        self.assertEqual(len(r.data['results']),1)
        self.assertEqual(r.data['next_offset'],1)
