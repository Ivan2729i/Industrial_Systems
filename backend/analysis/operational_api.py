"""Read-only global map API; expensive synchronization runs in CLI worker."""
import os,secrets
from datetime import datetime,time,timedelta,timezone
from django.db import DatabaseError,transaction,connection
from django.db.models import Q,Count,Min,F,Value
from django.db.models.functions import Floor
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import FIRMSHarmonizationJob,FIRMSUnifiedDetection
from .firms_harmonization import VERSION,METHOD
from .nasa import split_bounding_box

class Filters(serializers.Serializer):
    start=serializers.DateField();end=serializers.DateField()
    bbox=serializers.CharField(default='world')
    status=serializers.ChoiceField(choices=['ASOCIADA','SOLO_MODIS','SOLO_VIIRS'],required=False)
    limit=serializers.IntegerField(default=1000,min_value=1,max_value=5000)
    offset=serializers.IntegerField(default=0,min_value=0,max_value=1000000)
    aggregate=serializers.BooleanField(default=False)
    compact=serializers.BooleanField(default=False)
    country=serializers.CharField(required=False,max_length=100)
    state=serializers.CharField(required=False,max_length=100)
    city=serializers.CharField(required=False,max_length=100)
    def validate(self,data):
        if not 0<=(data['end']-data['start']).days<=30:raise serializers.ValidationError('Selecciona 1–31 días UTC.')
        try:data['areas']=split_bounding_box(data['bbox'])
        except ValueError:raise serializers.ValidationError('BBox WGS84 inválido.')
        if any(data.get(k) for k in ['country','state','city']) and data['bbox']=='world':
            raise serializers.ValidationError('Resuelve la ubicación con el catálogo geográfico y envía su bbox; FIRMS no proporciona fronteras administrativas.')
        return data

def serialize(row, count=1):
    members=[]
    for p in row.members.all():
        members.append({'pixel':{'id':p.fingerprint,'sensor':p.source.sensor.upper(),'platform':p.satellite,'granule':p.source_id,'source_file':'NASA FIRMS','h3_r7':None,'row':None,'column':None,'latitude':p.latitude,'longitude':p.longitude,'observed_at':p.observed_at.isoformat().replace('+00:00','Z'),'fire_class':None,'qa':{'confidence':p.original.get('confidence'),'frp':p.original.get('frp'),'brightness':p.original.get('brightness',p.original.get('bright_ti4')),'level2_qa_evaluated':False},'provenance':p.original}})
    return {'id':row.pk,'latitude':row.latitude,'longitude':row.longitude,'observed_at':row.observed_at.isoformat().replace('+00:00','Z'),'acq_datetime_utc':row.observed_at.isoformat().replace('+00:00','Z'),'source_modis':row.modis_count>0,'source_viirs':row.viirs_count>0,'status':row.status,'version':row.job.version,'method':METHOD,'modis_count':row.modis_count,'viirs_count':row.viirs_count,'members':members,'assessment':row.metadata,'product':'FIRMS_OPERATIONAL','represented_count':count,'geometry':{'type':'Point','coordinates':[row.longitude,row.latitude]}}

def job_data(job):
    return {'id':job.pk,'date':str(job.date),'status':job.status,'version':job.version,'modis_count':job.modis_count,'viirs_count':job.viirs_count,'records':job.records,'metadata':job.metadata,'error':job.error,'updated_at':job.updated_at}

@api_view(['GET'])
def detections(request):
    form=Filters(data=request.query_params);form.is_valid(raise_exception=True);f=form.validated_data
    try:
        start=datetime.combine(f['start'],time.min,tzinfo=timezone.utc);end=datetime.combine(f['end']+timedelta(days=1),time.min,tzinfo=timezone.utc)
        qs=FIRMSUnifiedDetection.objects.filter(job__status='COMPLETADO',job__version=VERSION,observed_at__gte=start,observed_at__lt=end)
        if f['bbox']!='world':
            spatial=Q()
            for area in f['areas']:
                w,s,e,n=map(float,area.split(','));spatial|=Q(longitude__gte=w,longitude__lte=e,latitude__gte=s,latitude__lte=n)
            qs=qs.filter(spatial)
        if f.get('status'):qs=qs.filter(status=f['status'])
        count=qs.count();counts={p['status']:p['count'] for p in qs.values('status').annotate(count=Count('pk'))}
        jobs=list(FIRMSHarmonizationJob.objects.filter(date__range=(f['start'],f['end']),version=VERSION).order_by('date'))
        complete_days={j.date for j in jobs if j.status=='COMPLETADO'}
        missing=[str(f['start']+timedelta(days=i)) for i in range((f['end']-f['start']).days+1) if f['start']+timedelta(days=i) not in complete_days]
        represented={};size=1.0
        if f['aggregate']:
            while True:
                cells=list(qs.order_by().annotate(gx=Floor((F('longitude')+Value(180.0))/Value(size)),gy=Floor((F('latitude')+Value(90.0))/Value(size))).values('gx','gy').annotate(count=Count('pk'),representative=Min('pk'))[:5001])
                if len(cells)<=5000:break
                size*=2
            represented={r['representative']:r['count'] for r in cells}
            shown=qs.filter(pk__in=represented).order_by('pk');next_offset=None
        else:
            shown=qs.order_by('pk')[f['offset']:f['offset']+f['limit']]
            next_offset=f['offset']+f['limit'] if f['offset']+f['limit']<count else None
        if f['compact']:
            rows=shown.values('id','latitude','longitude','observed_at','status','modis_count','viirs_count')
            results=[dict(r,version=VERSION,method=METHOD,product='FIRMS_OPERATIONAL',members=[],assessment={},details_deferred=True,represented_count=represented.get(r['id'],1)) for r in rows]
        else:
            rows=shown.select_related('job','representative').prefetch_related('members__source')
            results=[serialize(r,represented.get(r.pk,1)) for r in rows]
        return Response({'product':'FIRMS_OPERATIONAL','method':METHOD,'count':count,'counts':counts,'mode':'aggregated' if f['aggregate'] else 'individual','cell_degrees':size if f['aggregate'] else None,'results':results,'next_offset':next_offset,'jobs':[job_data(j) for j in jobs],'missing_dates':missing,'status':'PROCESAMIENTO_PENDIENTE' if missing else 'DATOS_DISPONIBLES' if count else 'SIN_DETECCIONES','note':'Integración operativa FIRMS. Asociaciones exploratorias; sin QA Level 2 ni evaluación de cobertura compartida. Las agrupaciones usan una observación original representativa; selecciona o consulta un área menor para obtener detalle.'})
    except DatabaseError:return Response({'detail':'PostgreSQL no está disponible.'},status=503)

@api_view(['GET'])
def detail(request,pk):
    row=FIRMSUnifiedDetection.objects.select_related('job').prefetch_related('members__source').filter(pk=pk).first()
    return Response(serialize(row)) if row else Response({'detail':'Detección no encontrada.'},status=404)

@api_view(['GET','POST'])
def jobs(request):
    if request.method=='GET':return Response([job_data(j) for j in FIRMSHarmonizationJob.objects.order_by('-date')[:100]])
    key=os.getenv('SCIENTIFIC_ADMIN_KEY','')
    if not key:return Response({'detail':'Administración no configurada.'},status=503)
    if not secrets.compare_digest(key,request.headers.get('X-Scientific-Key','')):return Response({'detail':'Autorización administrativa requerida.'},status=403)
    field=serializers.DateField();day=field.run_validation(request.data.get('date'))
    with transaction.atomic():
        with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_xact_lock(7241704)')
        if FIRMSHarmonizationJob.objects.filter(status__in=['PENDIENTE','PROCESANDO']).count()>=8:return Response({'detail':'Cola operativa completa.'},status=429)
        job,_=FIRMSHarmonizationJob.objects.get_or_create(date=day,version=VERSION)
        if job.status=='ERROR':job.status='PENDIENTE';job.save()
    return Response(job_data(job),status=202)
