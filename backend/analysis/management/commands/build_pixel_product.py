import json,sys
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from analysis.models import HarmonizationRun,OverpassPair,H3Observation
from analysis.pixel_product import persist_pixel_product

class Command(BaseCommand):
    help='Genera producto georreferenciado desde archivos Level 2 y contexto H3 persistido; no modifica V1.'
    def add_arguments(self,p):
        p.add_argument('--run-id',type=int,required=True)
        p.add_argument('--folder',type=Path,default=settings.BASE_DIR.parent/'src/datos/cache_level2')
    def handle(self,*args,**o):
        sys.path.insert(0,str(settings.BASE_DIR.parent/'src'))
        import pandas as pd
        from pixel_harmonization import generate
        run=HarmonizationRun.objects.get(pk=o['run_id']);params=run.parameters
        if run.status!='COMPLETADO' or not params.get('modis'):raise CommandError('Selecciona una ejecucion por pareja completada')
        pair=OverpassPair.objects.get(region=run.region,date=run.date,modis_sobrevuelo=params['modis'],viirs_sobrevuelo=params['viirs'])
        frame=pd.DataFrame(list(H3Observation.objects.filter(pair=pair,version_armonizacion=run.version).values('celda_h3','estrato_temporal','cobertura_compartida_pct','coincidencia_qa')))
        region={'oeste':run.region.west,'este':run.region.east,'sur':run.region.south,'norte':run.region.north}
        payload=generate(o['folder'],params['modis'],params['viirs'],region,frame,run.resolution)
        payload['h3_source_version']=run.version
        for d in payload['detections']:d['assessment']['h3_source_version']=run.version
        version='pixel_assoc_v1__'+run.version
        n=persist_pixel_product(payload,pair,version)
        run.parameters={**run.parameters,'pixel_product':payload['conservation']};run.save(update_fields=['parameters','updated_at'])
        target=settings.BASE_DIR.parent/'src/resultados_lotes/pixel_products'/f'run-{run.pk}.json';target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(payload,indent=2,allow_nan=False),encoding='utf-8')
        self.stdout.write(f'run={run.pk} version={version} source_pixels={len(payload["pixels"])} unified={n} states='+str(__import__('collections').Counter(g['status'] for g in payload['detections'])))
