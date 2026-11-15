from datetime import datetime,date,timezone
from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIClient
from .models import SatelliteSource,DetectionImport,FireDetection,FIRMSUnifiedDetection,FIRMSHarmonizationJob
from .firms_harmonization import process_day,associate,distance

class OperationalTests(TestCase):
    def setUp(self):
        self.day=date(2024,4,16)
        self.imports={}
        for name,sensor in [('MODIS_SP','modis'),('VIIRS_SNPP_SP','viirs')]:
            source=SatelliteSource.objects.create(pk=name,sensor=sensor)
            self.imports[sensor]=DetectionImport.objects.create(source=source,date=self.day,area='world',status='DATOS_DISPONIBLES')
        self.client=APIClient()
    def pixel(self,sensor,identity,lat=0,lon=0,minute=0):
        imp=self.imports[sensor]
        return FireDetection.objects.create(source=imp.source,data_import=imp,fingerprint=identity,latitude=lat,longitude=lon,satellite='Aqua' if sensor=='modis' else 'N',observed_at=datetime(2024,4,16,12,minute,tzinfo=timezone.utc),original={'confidence':'nominal','frp':'4.5'})
    def test_conservation_idempotence_and_traceability(self):
        m=self.pixel('modis','m');v=self.pixel('viirs','v',lon=.001,minute=5)
        self.pixel('viirs','v2',lon=.002,minute=5);self.pixel('modis','m2',lat=20);self.pixel('viirs','v3',lat=-20)
        first=process_day(self.day);again=process_day(self.day)
        self.assertEqual(first.pk,again.pk);self.assertEqual(first.records,3)
        self.assertEqual(first.metadata['source_members'],5)
        group=FIRMSUnifiedDetection.objects.get(status='ASOCIADA')
        self.assertEqual(group.representative_id,m.pk);self.assertEqual(group.viirs_count,2)
        self.assertIn(v,group.members.all());self.assertEqual(FIRMSUnifiedDetection.objects.count(),3)
    def test_no_same_h3_equivalence_and_temporal_gate(self):
        self.pixel('modis','m');self.pixel('viirs','distant',lon=.02)
        self.pixel('viirs','late',minute=16)
        result=process_day(self.day)
        self.assertEqual(result.records,3);self.assertEqual(result.metadata['counts']['ASOCIADA'],0)
    def test_exact_duplicates_preserve_all_source_references(self):
        self.pixel('modis','m');self.pixel('modis','m-copy');self.pixel('viirs','v')
        result=process_day(self.day)
        self.assertEqual(result.records,1);self.assertEqual(result.modis_count,1)
        self.assertEqual(result.metadata['exact_duplicates'],1)
        self.assertEqual(FIRMSUnifiedDetection.objects.get().members.count(),3)
    def test_antimeridian_and_polar_candidate_index(self):
        m=self.pixel('modis','m',lat=10,lon=179.999)
        v=self.pixel('viirs','v',lat=10,lon=-179.999)
        self.assertLess(distance(m,v),300)
        self.assertEqual(associate([m],[v])[0][2],'ASOCIADA')
        m.latitude=v.latitude=89.99;m.longitude=179.9;v.longitude=-179.9
        self.assertEqual(associate([m],[v])[0][2],'ASOCIADA')
    def test_partial_import_never_becomes_completed(self):
        self.imports['viirs'].status='ERROR_PROCESAMIENTO';self.imports['viirs'].save()
        with self.assertRaisesRegex(ValueError,'WORLD_IMPORT_INCOMPLETE'):process_day(self.day)
        self.assertEqual(FIRMSHarmonizationJob.objects.get().status,'ERROR')
        self.assertEqual(FIRMSUnifiedDetection.objects.count(),0)
    def test_api_aggregation_pagination_bbox_and_missing_days(self):
        self.pixel('modis','m');self.pixel('viirs','v',lon=.001);self.pixel('viirs','far',lat=50)
        process_day(self.day)
        path='/api/v1/harmonized-detections/'
        q={'start':str(self.day),'end':str(self.day),'aggregate':'true'}
        result=self.client.get(path,q)
        self.assertEqual(result.status_code,200)
        self.assertEqual(sum(r['represented_count'] for r in result.data['results']),2)
        q.update(aggregate='false',limit=1)
        page=self.client.get(path,q);self.assertEqual(len(page.data['results']),1);self.assertEqual(page.data['next_offset'],1)
        detail=self.client.get(path+page.data['results'][0]['id']+'/')
        self.assertTrue(detail.data['observed_at'].endswith('Z'))
        q['bbox']='-1,-1,1,1';self.assertEqual(self.client.get(path,q).data['count'],1)
        q['end']='2024-04-17';self.assertEqual(self.client.get(path,q).data['missing_dates'],['2024-04-17'])
        q['start']='2024-05-01';self.assertEqual(self.client.get(path,q).status_code,400)
    def test_valid_empty_and_admin_queue(self):
        job=process_day(self.day);self.assertEqual(job.records,0)
        result=self.client.get('/api/v1/harmonized-detections/',{'start':str(self.day),'end':str(self.day)})
        self.assertEqual(result.data['status'],'SIN_DETECCIONES')
        with patch.dict('os.environ',{'SCIENTIFIC_ADMIN_KEY':'test-only-administrative-key'}):
            url='/api/v1/harmonized-detections/jobs/'
            self.assertEqual(self.client.post(url,{'date':'2024-04-17'}).status_code,403)
            response=self.client.post(url,{'date':'2024-04-17'},HTTP_X_SCIENTIFIC_KEY='test-only-administrative-key')
            self.assertEqual(response.status_code,202);self.assertEqual(response.data['status'],'PENDIENTE')
