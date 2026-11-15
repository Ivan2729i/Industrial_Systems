import sys,json,copy
from pathlib import Path
from datetime import datetime,timezone
from django.conf import settings
from django.test import SimpleTestCase,TestCase
sys.path.insert(0,str(settings.BASE_DIR.parent/'src'))
from pixel_harmonization import associate
from shapely.geometry import box
from analysis.pixel_product import persist_pixel_product
from analysis.models import Region,OverpassPair,Level2FirePixel,HarmonizedDetection,HarmonizedDetectionMember

class IdentityProjection:
    def transform(self,x,y):return x,y

def sample(identity,sensor,shape,cell='one',minutes=0,bad=False):
    return {'id':identity,'sensor':sensor,'_shape':shape,'h3':cell,'observed_at':f'2024-04-16T12:{minutes:02d}:00+00:00','latitude':0,'longitude':0,'qa':{'bowtie_residual':bad,'geo_non_nominal':False}}

class AssociationTests(SimpleTestCase):
    def run_product(self,pixels):
        return associate(pixels,{p['h3']:{'estrato_temporal':'A_0_A_5_MIN'} for p in pixels},IdentityProjection())
    def test_same_h3_is_not_spatial_match(self):
        rows=self.run_product([sample('m','MODIS',box(0,0,1,1)),sample('v','VIIRS',box(4,4,5,5))])
        self.assertEqual({r['status'] for r in rows},{'SOLO_MODIS','SOLO_VIIRS'})
    def test_one_modis_many_viirs_and_original_anchor(self):
        pixels=[sample('m','MODIS',box(0,0,2,2)),sample('v1','VIIRS',box(.1,.1,.5,.5),'different'),sample('v2','VIIRS',box(1,1,1.5,1.5))]
        rows=self.run_product(pixels)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['representative'],'m');self.assertEqual(set(rows[0]['members']),{'m','v1','v2'})
    def test_viirs_cannot_belong_to_two_modis(self):
        rows=self.run_product([sample('m1','MODIS',box(0,0,2,2)),sample('m2','MODIS',box(0,0,2,2)),sample('v','VIIRS',box(.1,.1,.5,.5))])
        self.assertEqual(sum('v' in r['members'] for r in rows),1)
    def test_bad_qa_and_time_are_not_silently_removed(self):
        pixels=[sample('m','MODIS',box(0,0,2,2)),sample('v','VIIRS',box(.1,.1,.5,.5),bad=True),sample('late','VIIRS',box(.1,.1,.5,.5),minutes=30)]
        rows=self.run_product(pixels)
        self.assertEqual(sum(len(r['members']) for r in rows),3)
        self.assertFalse(any(r['status']=='ASOCIADA' for r in rows))
        self.assertEqual(next(r['status'] for r in rows if r['representative']=='v'),'SIN_COMPARABILIDAD')

class PixelPersistenceTests(TestCase):
    def test_real_payload_import_conservation_and_idempotence(self):
        payload=json.loads((settings.BASE_DIR/'analysis/fixtures/real_zambia_pixel_product.json').read_text(encoding='utf-8'))
        region=Region.objects.create(id='test-pixels',name='test')
        pair=OverpassPair.objects.create(region=region,date='2024-04-16',modis_sobrevuelo='A2024107.1210',viirs_sobrevuelo='A2024107.1206')
        persist_pixel_product(payload,pair,'test-pixel-v1');persist_pixel_product(payload,pair,'test-pixel-v1')
        self.assertEqual(Level2FirePixel.objects.count(),6);self.assertEqual(HarmonizedDetection.objects.count(),4);self.assertEqual(HarmonizedDetectionMember.objects.count(),6)
        persist_pixel_product(payload,pair,'test-pixel-v2')
        self.assertEqual(HarmonizedDetection.objects.count(),8)
        from rest_framework.test import APIClient
        response=APIClient().get('/api/v1/harmonization/detections/',{'start':'2024-04-16','end':'2024-04-16'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.data['count'],4)
        self.assertEqual(sum(len(r['members']) for r in response.data['results']),6)
        self.assertTrue(all(r['observed_at'].endswith('Z') for r in response.data['results']))
        invalid=copy.deepcopy(payload);invalid['detections'][0]['representative']='not-an-original-member'
        with self.assertRaises(ValueError):persist_pixel_product(invalid,pair,'invalid-representative')
        changed=copy.deepcopy(payload);changed['detections'][0]['status']='SIN_COMPARABILIDAD'
        with self.assertRaises(ValueError):persist_pixel_product(changed,pair,'incompatible-revision')
        self.assertEqual(HarmonizedDetection.objects.count(),8)

    def test_identical_scope_reprocessing_does_not_multiply_api_points(self):
        payload=json.loads((settings.BASE_DIR/'analysis/fixtures/real_zambia_pixel_product.json').read_text(encoding='utf-8'))
        for name in ['scope-a','scope-b']:
            region=Region.objects.create(id=name,name=name)
            pair=OverpassPair.objects.create(region=region,date='2024-04-16',modis_sobrevuelo='A2024107.1210',viirs_sobrevuelo='A2024107.1206')
            persist_pixel_product(payload,pair,'same-version')
        from rest_framework.test import APIClient
        response=APIClient().get('/api/v1/harmonization/detections/',{'date':'2024-04-16','version':'same-version'})
        self.assertEqual(HarmonizedDetection.objects.count(),8)
        self.assertEqual(response.data['count'],4)
