from datetime import datetime,timezone
from unittest.mock import patch
from django.test import TestCase
from django.core.management import call_command
from io import StringIO
from rest_framework.test import APIClient
from .models import SatelliteSource,DetectionImport,FireDetection

class MapContractTests(TestCase):
    def test_sp_and_nrt_are_not_counted_twice(self):
        from django.utils.timezone import now
        for source_id in ['MODIS_SP','MODIS_NRT']:
            source=SatelliteSource.objects.create(id=source_id,sensor='modis')
            run=DetectionImport.objects.create(source=source,date='2024-04-16',area='world',status='DATOS_DISPONIBLES',finished_at=now())
            FireDetection.objects.create(fingerprint=source_id,source=source,data_import=run,observed_at=datetime(2024,4,16,12,tzinfo=timezone.utc),latitude=0,longitude=0,satellite='Aqua',original={})
        result=APIClient().get('/api/v1/detections/',{'sensor':'modis','start_date':'2024-04-16','end_date':'2024-04-16','detail':'true'}).data
        self.assertEqual(result['count'],1)
        self.assertEqual(result['results'][0]['source'],'MODIS_SP')

    def test_expired_nrt_is_not_reported_as_complete(self):
        from datetime import timedelta
        from django.utils.timezone import now
        source=SatelliteSource.objects.create(id='MODIS_NRT',sensor='modis')
        DetectionImport.objects.create(source=source,date='2024-04-16',area='world',status='DATOS_DISPONIBLES',finished_at=now()-timedelta(minutes=31))
        result=APIClient().get('/api/v1/detections/',{'sensor':'modis','start_date':'2024-04-16','end_date':'2024-04-16'}).data
        self.assertEqual(result['status'],'DATOS_NO_IMPORTADOS')
        self.assertEqual(len(result['missing_dates']),1)

    def test_compact_preserves_identity_utc_and_deferred_detail(self):
        source=SatelliteSource.objects.create(id='MODIS_SP',sensor='modis')
        run=DetectionImport.objects.create(source=source,date='2024-04-16',area='world',status='DATOS_DISPONIBLES')
        for i,stamp in enumerate(['2024-04-16T00:00:00+00:00','2024-04-16T23:59:59+00:00','2024-04-17T00:00:00+00:00']):
            FireDetection.objects.create(fingerprint=str(i),source=source,data_import=run,observed_at=datetime.fromisoformat(stamp),latitude=0,longitude=0,satellite='Aqua',original={'confidence':'83','frp':'12.5','scan':'1.2','track':'1.1'})
        client=APIClient();params={'sensor':'modis','start_date':'2024-04-16','end_date':'2024-04-16','compact':'true','detail':'true','limit':1}
        first=client.get('/api/v1/detections/',params).data
        self.assertEqual(first['count'],2);self.assertEqual(first['next_offset'],1)
        self.assertNotIn('scan',first['results'][0]['original'])
        detail=client.get('/api/v1/detections/'+str(first['results'][0]['id'])+'/').data
        self.assertEqual(detail['original']['scan'],'1.2')
        params['offset']=1;second=client.get('/api/v1/detections/',params).data
        self.assertNotEqual(first['results'][0]['id'],second['results'][0]['id'])
    @patch('analysis.management.commands.import_firms.FIRMSClient')
    def test_nrt_refresh_keeps_old_rows_without_active_duplicates(self, nasa):
        nasa.return_value.availability.return_value=[{'min_date':'2024-01-01','max_date':'2024-12-31'}]
        row={'latitude':'17','longitude':'-99','acq_date':'2024-04-16','acq_time':'1230','satellite':'Aqua','frp':'10'}
        nasa.return_value.rows.return_value=[row]
        args=dict(source='MODIS_NRT',start='2024-04-16',end='2024-04-16',bbox='world',stdout=StringIO())
        call_command('import_firms',**args)
        nasa.return_value.rows.return_value=[dict(row,frp='11')]
        call_command('import_firms',**args,refresh=True)
        self.assertEqual(FireDetection.objects.count(),2)
        self.assertEqual(FireDetection.objects.filter(is_current=True).count(),1)
