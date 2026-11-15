"""Bounded world planner; unrequested tiles remain explicitly pending."""
import json
from pathlib import Path
from datetime import date
from django.core.management.base import BaseCommand
from analysis.scientific_jobs import JobQuery, enqueue

class Command(BaseCommand):
    help='Encola particiones de medio grado de una grilla mundial progresiva (no declara cobertura total).'
    def add_arguments(self,p):
        p.add_argument('--date',required=True)
        p.add_argument('--science-version',dest='science_version',required=True)
        p.add_argument('--start-index',type=int,default=0)
        p.add_argument('--limit',type=int,default=1)
        p.add_argument('--manifest',type=Path,required=True)
    def handle(self,*args,**o):
        date.fromisoformat(o['date'])
        total=720*340
        if not 1<=o['limit']<=16 or not 0<=o['start_index']<total:raise ValueError('Planificador acotado a 16 particiones por invocacion')
        path=o['manifest'];config={'date':o['date'],'version':o['science_version'],'grid_degrees':.5,'total_tiles':total,'latitude_limits':[-85,85]}
        previous=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'config':config,'requested':{}}
        if previous['config']!=config:raise ValueError('Manifiesto pertenece a otra configuracion')
        for index in range(o['start_index'],min(total,o['start_index']+o['limit'])):
            row,col=divmod(index,720);w=-180+col*.5;s=-85+row*.5
            bbox=f'{max(w,-179.999999)},{max(s,-84.999999)},{min(w+.5,179.999999)},{min(s+.5,84.999999)}'
            form=JobQuery(data={'date':o['date'],'bbox':bbox,'version':o['science_version']});form.is_valid(raise_exception=True)
            run,_=enqueue(form.validated_data);previous['requested'][str(index)]=run.pk
        previous['not_requested_tiles']=total-len(previous['requested']);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(previous,indent=2),encoding='utf-8')
        self.stdout.write(f'Particiones solicitadas: {len(previous["requested"])}; no solicitadas: {previous["not_requested_tiles"]}. Los polos quedan fuera de este metodo experimental.')
