from datetime import date
from unittest.mock import patch
from django.test import SimpleTestCase,TestCase
from rest_framework.test import APIRequestFactory
from analysis.scientific_jobs import JobQuery,enqueue,submit

class JobValidationTests(SimpleTestCase):
    def test_costly_requests_rejected(self):
        for bbox in ['world','0,0,10,10','170,-1,-170,1']:
            f=JobQuery(data={'date':'2024-04-16','bbox':bbox,'version':'v2'});self.assertFalse(f.is_valid())
    @patch.dict('os.environ',{'SCIENTIFIC_ADMIN_KEY':'test-only'})
    def test_requires_admin_key(self):
        self.assertEqual(submit(APIRequestFactory().post('/',{},format='json')).status_code,403)

class JobPersistenceTests(TestCase):
    def test_idempotent_queue(self):
        q=JobQuery(data={'date':'2024-04-16','bbox':'31,-15,31.2,-14.8','version':'test_v2'});q.is_valid(raise_exception=True)
        a,created=enqueue(q.validated_data);b,again=enqueue(q.validated_data)
        self.assertTrue(created);self.assertFalse(again);self.assertEqual(a.pk,b.pk)

    @patch.dict('os.environ',{'SCIENTIFIC_ADMIN_KEY':'test-only-key'})
    def test_authorized_submission_is_idempotent(self):
        payload={'date':'2024-04-16','bbox':'31,-15,31.2,-14.8','version':'api_v2'}
        factory=APIRequestFactory()
        first=submit(factory.post('/',payload,format='json',HTTP_X_SCIENTIFIC_KEY='test-only-key'))
        second=submit(factory.post('/',payload,format='json',HTTP_X_SCIENTIFIC_KEY='test-only-key'))
        self.assertEqual(first.status_code,202);self.assertEqual(first.data['id'],second.data['id'])

class TimeConversionTests(SimpleTestCase):
    def test_historical_offsets(self):
        import sys
        from pathlib import Path
        from datetime import datetime,timezone
        from django.conf import settings
        sys.path.insert(0,str(settings.BASE_DIR.parent/'src'))
        from omparar_tiempos import convertir_utc,EPOCA_TAI93
        for year,offset in [(2005,5),(2013,8),(2024,10)]:
            utc=datetime(year,4,16,12,tzinfo=timezone.utc)
            self.assertEqual(convertir_utc((utc-EPOCA_TAI93).total_seconds()+offset),utc)
