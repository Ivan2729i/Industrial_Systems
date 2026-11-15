import hashlib
import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.timezone import now
from analysis.nasa import FIRMSClient, SOURCES, NASAError, bounding_box
from analysis.models import SatelliteSource, DetectionImport, FireDetection

class Command(BaseCommand):
    help='Importacion FIRMS diaria, transaccional y reanudable. No modifica observaciones Level-2.'
    def add_arguments(self,p):
        p.add_argument('--source',required=True,choices=SOURCES)
        p.add_argument('--start',required=True)
        p.add_argument('--end',required=True)
        p.add_argument('--bbox',default='world')
    def handle(self,*args,**o):
        try:
            first,last=date.fromisoformat(o['start']),date.fromisoformat(o['end'])
            if first>last or (last-first).days>365: raise ValueError('Rango requerido: 1 a 366 dias')
            area=bounding_box(o['bbox']);client=FIRMSClient()
            availability=client.availability(o['source'])
            if not availability or not all(k in availability[0] for k in ['min_date','max_date']): raise NASAError('Disponibilidad NASA no verificable')
        except (ValueError,NASAError) as e: raise CommandError(str(e)) from None
        source,_=SatelliteSource.objects.get_or_create(id=o['source'],defaults={'sensor':'modis' if o['source'].startswith('MODIS') else 'viirs','platform':None if o['source'].startswith('MODIS') else o['source'].split('_')[1].lower()})
        day=first
        while day<=last:
            run,_=DetectionImport.objects.get_or_create(source=source,date=day,area=area)
            if run.status=='DATOS_DISPONIBLES':
                self.stdout.write(f'{day}: ya importado ({run.records})');day+=timedelta(days=1);continue
            if not availability[0]['min_date']<=day.isoformat()<=availability[0]['max_date']:
                run.status='DATOS_NO_DISPONIBLES_EN_NASA';run.save();day+=timedelta(days=1);continue
            try:
                with transaction.atomic():
                    run=DetectionImport.objects.select_for_update().get(pk=run.pk)
                    if run.status=='DATOS_DISPONIBLES': day+=timedelta(days=1);continue
                    batch=[];count=0
                    for row in client.rows(source.id,day.isoformat(),area):
                        lat,lon=float(row['latitude']),float(row['longitude'])
                        if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180: raise ValueError('Coordenadas invalidas')
                        stamp=datetime.strptime(row['acq_date']+row['acq_time'].zfill(4),'%Y-%m-%d%H%M').replace(tzinfo=timezone.utc)
                        if stamp.date()!=day: raise ValueError('NASA devolvio fecha diferente')
                        identity=json.dumps([source.id,row],sort_keys=True,separators=(',',':'))
                        batch.append(FireDetection(fingerprint=hashlib.sha256(identity.encode()).hexdigest(),source=source,data_import=run,observed_at=stamp,latitude=lat,longitude=lon,satellite=row['satellite'],original=row))
                        count+=1
                        if len(batch)==1000: FireDetection.objects.bulk_create(batch,ignore_conflicts=True);batch=[]
                    FireDetection.objects.bulk_create(batch,ignore_conflicts=True)
                    run.records=count;run.status='DATOS_DISPONIBLES';run.finished_at=now();run.error='';run.save()
                self.stdout.write(f'{source.id} {day}: {count} registros recibidos; importacion completa')
            except Exception as e:
                run.status='ERROR_PROCESAMIENTO';run.error=type(e).__name__;run.save()
                raise CommandError('Importacion revertida; puedes reanudar el mismo comando. Error: '+type(e).__name__) from None
            day+=timedelta(days=1)
            if day<=last:time.sleep(2)
