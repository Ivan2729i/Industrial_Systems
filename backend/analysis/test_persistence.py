import csv
import io
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient
from .management.commands.import_observations import parse_row
from .models import H3Observation, DataImport
from .serializers import ObservationSerializer

SOURCE = settings.BASE_DIR.parent / 'src/resultados_lotes/observaciones_h3_armonizadas_v1.csv'

def source_rows():
    with SOURCE.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))

class SourceValidationTests(SimpleTestCase):
    def test_real_dataset_and_nulls(self):
        rows = source_rows()
        self.assertEqual(len(rows),2179)
        values = [parse_row(r)[1] for r in rows]
        self.assertEqual(sum(v['diferencia_min'] is None for v in values),266)
        self.assertEqual(sum(v['viirs_fuego_qa_nominal'] is None for v in values),585)
        self.assertEqual(sum(v['cobertura_compartida_pct'] is None for v in values),197)
    def test_reject_invalid_counts_boolean_h3(self):
        row = source_rows()[0]
        for field, value in [('modis_fuego','1.5'),('viirs_utiles','-1'),('viirs_pixeles','nan'),('qa_viirs_disponible','yes'),('celda_h3','invalid')]:
            with self.subTest(field=field), self.assertRaises(ValueError): parse_row({**row,field:value})

class PersistenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('import_observations',file=str(SOURCE),stdout=io.StringIO())
    def setUp(self): self.client = APIClient()
    def test_source_totals_and_nulls(self):
        self.assertEqual(H3Observation.objects.count(),2179)
        for region,count in [('michoacan_piloto',585),('guerrero',775),('tabasco_chiapas',819)]:
            self.assertEqual(H3Observation.objects.filter(pair__region_id=region).count(),count)
        self.assertEqual(H3Observation.objects.filter(diferencia_min__isnull=True).count(),266)
        self.assertEqual(H3Observation.objects.filter(viirs_fuego_qa_nominal__isnull=True).count(),585)
    def test_idempotence(self):
        call_command('import_observations',file=str(SOURCE),stdout=io.StringIO())
        self.assertEqual(H3Observation.objects.count(),2179)
        run=DataImport.objects.latest('pk')
        self.assertEqual((run.inserted,run.unchanged),(0,2179))
    def test_uniqueness(self):
        row=H3Observation.objects.first()
        row.pk=None
        with self.assertRaises(IntegrityError),transaction.atomic(): row.save()
    def test_serializer_null_and_no_private_source(self):
        row=H3Observation.objects.filter(diferencia_min__isnull=True).select_related('pair','pair__region').first()
        data=ObservationSerializer(row).data
        self.assertIsNone(data['diferencia_min'])
        self.assertNotIn('data_import',data)
        self.assertEqual(data['region_id'],row.pair.region_id)
    def test_filters_and_summary(self):
        for region,day,modis,viirs,both in [('guerrero','2024-04-16',16,10,4),('tabasco_chiapas','2024-04-19',8,32,5)]:
            response=self.client.get('/api/v1/summary/',{'region':region,'date':day})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.data['modis_fire_original'],modis)
            self.assertEqual(response.data['viirs_fire_original'],viirs)
            self.assertEqual(next(v['count'] for v in response.data['original'] if v['coincidencia_original']=='AMBOS'),both)
        response=self.client.get('/api/v1/observations/',{'region':'guerrero','sensor':'viirs','fire_only':'true','limit':2})
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.data['results']),2)
        self.assertTrue(response.data['next'])
        self.assertTrue(all(r['viirs_fuego']>0 for r in response.data['results']))
    def test_invalid_parameters_and_read_only(self):
        for query in [{'date':'bad'},{'sensor':'unknown'},{'limit':'-1'},{'offset':'x'},{'limit':'1001'},{'fire_only':'unknown'},{'bbox':'a,b'},{'region':'unknown'}]:
            with self.subTest(query=query): self.assertEqual(self.client.get('/api/v1/observations/',query).status_code,400)
        self.assertEqual(self.client.post('/api/v1/observations/',{}).status_code,405)
        self.assertEqual(self.client.get('/api/v1/observations/999999/').status_code,404)
    def test_geojson_and_scope(self):
        self.assertEqual(self.client.get('/api/v1/map/').status_code,400)
        response=self.client.get('/api/v1/map/',{'region':'guerrero','limit':2})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['count'],775)
        self.assertEqual(len(response.data['features']),2)
        ring=response.data['features'][0]['geometry']['coordinates'][0]
        self.assertEqual(ring[0],ring[-1])
        self.assertTrue(response.data['next'])
    def test_transaction_rollback_and_version_policy(self):
        rows=source_rows()[:2]
        rows[0]['modis_fuego']='1'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'revision.csv'
            def save():
                with path.open('w',encoding='utf-8',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
            save()
            with self.assertRaises(CommandError): call_command('import_observations',file=str(path),stdout=io.StringIO())
            self.assertEqual(H3Observation.objects.count(),2179)
            for row in rows: row['version_armonizacion']='v2_test'
            rows[1]['viirs_fuego']='bad'
            save()
            with self.assertRaises(CommandError): call_command('import_observations',file=str(path),stdout=io.StringIO())
            self.assertFalse(H3Observation.objects.filter(version_armonizacion='v2_test').exists())
            rows[1]['viirs_fuego']='0';save()
            call_command('import_observations',file=str(path),stdout=io.StringIO())
            self.assertEqual(H3Observation.objects.filter(version_armonizacion='v2_test').count(),2)
            self.assertEqual(H3Observation.objects.filter(version_armonizacion='v1_experimental').count(),2179)

class APIValidationWithoutDatabaseTests(SimpleTestCase):
    def test_invalid_filters_without_database_queries(self):
        client=APIClient()
        for params in [{'date':'2024-99-01'},{'sensor':'x'},{'start':'2024-04-20','end':'2024-04-01'},{'bbox':'nan,1,2,3'},{'fire_only':'invalid'}]:
            with self.subTest(params=params): self.assertEqual(client.get('/api/v1/observations/',params).status_code,400)
        self.assertEqual(client.post('/api/v1/observations/',{}).status_code,405)
    def test_database_outage_health_is_safe(self):
        from django.db import OperationalError
        client=APIClient()
        with patch('analysis.api.connection') as database:
            database.cursor.side_effect=OperationalError('sensitive driver diagnostic')
            response=client.get('/api/health/')
        self.assertEqual(response.status_code,503)
        self.assertNotIn('sensitive',str(response.data))
