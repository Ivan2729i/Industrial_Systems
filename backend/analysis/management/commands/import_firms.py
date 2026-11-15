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
        p.add_argument('--refresh',action='store_true')
    def handle(self,*args,**o):
        if o['refresh'] and not o['source'].endswith('_NRT'):raise CommandError('Solo NRT permite refresco de instantánea')
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
            if run.status=='DATOS_DISPONIBLES' and not o['refresh']:
                self.stdout.write(f'{day}: ya importado ({run.records})');day+=timedelta(days=1);continue
            if not availability[0]['min_date']<=day.isoformat()<=availability[0]['max_date']:
                run.status='DATOS_NO_DISPONIBLES_EN_NASA';run.save();day+=timedelta(days=1);continue
            try:
                with transaction.atomic():
                    run=DetectionImport.objects.select_for_update().get(pk=run.pk)
                    if run.status=='DATOS_DISPONIBLES' and not o['refresh']: day+=timedelta(days=1);continue
                    if o['refresh']:
                        if not source.id.endswith('_NRT'):raise ValueError('Solo NRT permite refresco')
                        old=FireDetection.objects.filter(source=source,observed_at__gte=datetime.combine(day,datetime.min.time(),tzinfo=timezone.utc),observed_at__lt=datetime.combine(day+timedelta(days=1),datetime.min.time(),tzinfo=timezone.utc))
                        if area!='world':
                            w,s,e,n=map(float,area.split(','));old=old.filter(longitude__gte=w,longitude__lte=e,latitude__gte=s,latitude__lte=n)
                        old.update(is_current=False)
                    batch=[];count=0
                    for row in client.rows(source.id,day.isoformat(),area):
                        lat,lon=float(row['latitude']),float(row['longitude'])
                        if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180: raise ValueError('Coordenadas invalidas')
                        stamp=datetime.strptime(row['acq_date']+row['acq_time'].zfill(4),'%Y-%m-%d%H%M').replace(tzinfo=timezone.utc)
                        if stamp.date()!=day: raise ValueError('NASA devolvio fecha diferente')
                        identity=json.dumps([source.id,row],sort_keys=True,separators=(',',':'))
                        batch.append(FireDetection(fingerprint=hashlib.sha256(identity.encode()).hexdigest(),source=source,data_import=run,observed_at=stamp,latitude=lat,longitude=lon,satellite=row['satellite'],original=row))
                        count+=1
                        if len(batch)==1000:
                            FireDetection.objects.bulk_create(batch,ignore_conflicts=True)
                            if o['refresh']:FireDetection.objects.filter(fingerprint__in=[r.fingerprint for r in batch]).update(is_current=True)
                            batch=[]
                    FireDetection.objects.bulk_create(batch,ignore_conflicts=True)
                    if o['refresh']:FireDetection.objects.filter(fingerprint__in=[r.fingerprint for r in batch]).update(is_current=True)
                    run.records=count;run.status='DATOS_DISPONIBLES';run.finished_at=now();run.error='';run.save()
                self.stdout.write(f'{source.id} {day}: {count} registros recibidos; importacion completa')
            except Exception as e:
                run.status='ERROR_PROCESAMIENTO';run.error=type(e).__name__;run.save()
                raise CommandError('Importacion revertida; puedes reanudar el mismo comando. Error: '+type(e).__name__) from None
            day+=timedelta(days=1)
            if day<=last:time.sleep(2)
