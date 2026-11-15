"""One sequential worker, serialized across processes using a PostgreSQL advisory lock."""
import csv,subprocess,sys,json,time
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from analysis.models import HarmonizationRun

class Command(BaseCommand):
    help='Procesa como maximo N solicitudes cientificas pendientes fuera de HTTP.'
    def add_arguments(self,p):
        p.add_argument('--limit',type=int,default=1)
        p.add_argument('--watch',action='store_true')
        p.add_argument('--retry-errors',action='store_true')
        p.add_argument('--recover-interrupted',action='store_true')
    def handle(self,*args,**options):
        if not 1<=options['limit']<=16: raise ValueError('limit debe estar entre 1 y 16')
        with connection.cursor() as c:
            c.execute('SELECT pg_try_advisory_lock(7241701)')
            if not c.fetchone()[0]: self.stdout.write('Otro worker esta activo.');return
        try:
            if options['recover_interrupted']: HarmonizationRun.objects.filter(status__in=['BUSCANDO_PRODUCTOS','PROCESANDO'],parameters__kind='regional_request').update(status='PROCESAMIENTO_PENDIENTE')
            if options['retry_errors']: HarmonizationRun.objects.filter(status='ERROR_PROCESAMIENTO',parameters__kind='regional_request').update(status='PROCESAMIENTO_PENDIENTE')
            while True:
                for run in HarmonizationRun.objects.filter(status='PROCESAMIENTO_PENDIENTE',parameters__kind='regional_request').order_by('id')[:options['limit']]: self.process(run)
                if not options['watch']:break
                time.sleep(3)
        finally:
            with connection.cursor() as c:c.execute('SELECT pg_advisory_unlock(7241701)')
    def process(self,run):
        root=settings.BASE_DIR.parent; work=root/'src'/'resultados_lotes'/'jobs'/run.key
        work.mkdir(parents=True,exist_ok=True)
        params=run.parameters;run.status='BUSCANDO_PRODUCTOS';run.save()
        try:
            manifest=work/'discovery.csv'
            if not manifest.exists():
                with (work/'discovery.log').open('w',encoding='utf-8') as output:
                    subprocess.run([sys.executable,str(root/'src/preparar_lotes.py'),'--bbox='+params['bbox'],'--start',str(run.date),'--end',str(run.date),'--output',str(manifest)],stdout=output,stderr=subprocess.STDOUT,check=True,timeout=300)
            with manifest.open(encoding='utf-8-sig') as stream: rows=list(csv.DictReader(stream))
            pairs=[]
            for m in [r for r in rows if r['sensor']=='MODIS' and datetime.strptime(r['fecha_hora'],'A%Y%j.%H%M').date()==run.date]:
                for v in [r for r in rows if r['sensor']=='VIIRS']:
                    delta=abs((datetime.strptime(m['fecha_hora'],'A%Y%j.%H%M')-datetime.strptime(v['fecha_hora'],'A%Y%j.%H%M')).total_seconds())/60
                    if delta<=15:pairs.append((delta,m,v))
            if not pairs:run.status='SIN_PAREJA_COMPATIBLE';run.save();return
            run.parameters={**params,'pairs_total':len(pairs),'pairs_completed':0,'pixel_detections_completed':0};run.status='PROCESANDO';run.records=0;run.save()
            for i,(_,m,v) in enumerate(sorted(pairs,key=lambda r:r[0])):
                target=work/f'pair-{i:03d}'
                command=[sys.executable,str(root/'src/run_harmonization.py'),'--bbox='+params['bbox'],'--date',str(run.date),'--region',run.region_id,'--modis',m['fecha_hora'],'--viirs',v['fecha_hora'],'--version',run.version,'--resolution',str(run.resolution),'--workdir',str(target)]
                with (work/f'pair-{i:03d}.log').open('a',encoding='utf-8') as output:
                    subprocess.run(command,stdout=output,stderr=subprocess.STDOUT,check=True,timeout=7200)
                state=json.loads((target/'run.json').read_text(encoding='utf-8'))
                run.records+=state.get('records',0);run.parameters['pixel_detections_completed']+=state.get('pixel_detections',0);run.parameters['pairs_completed']=i+1;run.save()
            run.status='COMPLETADO';run.save()
        except Exception as exc:
            run.status='ERROR_PROCESAMIENTO';run.error_type=type(exc).__name__;run.save()
            self.stderr.write(f'Trabajo {run.pk}: {type(exc).__name__}; consulta registro local, sin credenciales en API.')
