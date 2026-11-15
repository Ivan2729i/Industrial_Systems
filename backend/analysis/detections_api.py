from datetime import timedelta, datetime, time, timezone
from django.db.models import Count, Min, Max, Avg, FloatField, Value
from django.db.models.functions import Floor, TruncDate
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from .models import FireDetection, DetectionImport, SatelliteSource
from .nasa import bounding_box

class Query(serializers.Serializer):
    start_date=serializers.DateField()
    end_date=serializers.DateField()
    sensor=serializers.ChoiceField(choices=['modis','viirs'])
    bbox=serializers.CharField(default='world')
    satellite=serializers.CharField(required=False)
    limit=serializers.IntegerField(default=2000,min_value=1,max_value=5000)
    aggregate=serializers.BooleanField(default=False)
    cell_degrees=serializers.FloatField(default=2,min_value=.05,max_value=10)
    offset=serializers.IntegerField(default=0,min_value=0)

@api_view(['GET'])
def detections(request):
    form=Query(data=request.query_params);form.is_valid(raise_exception=True);f=form.validated_data
    if not 0<=(f['end_date']-f['start_date']).days<=30:raise ValidationError('Rango maximo: 31 dias')
    try:area=bounding_box(f['bbox'])
    except ValueError as e:raise ValidationError(str(e))
    qs=FireDetection.objects.filter(source__sensor=f['sensor'],observed_at__gte=datetime.combine(f['start_date'],time.min,tzinfo=timezone.utc),observed_at__lt=datetime.combine(f['end_date']+timedelta(days=1),time.min,tzinfo=timezone.utc)).select_related('source')
    if area!='world':
        w,s,e,n=map(float,area.split(','));qs=qs.filter(longitude__gte=w,longitude__lte=e,latitude__gte=s,latitude__lte=n)
    if 'satellite' in f:
        names={'aqua':'Aqua','terra':'Terra','snpp':'N','noaa20':'N20','noaa21':'N21'}
        qs=qs.filter(satellite__iexact=names.get(f['satellite'].lower(),f['satellite']))
    count=qs.count();offset=f['offset'];limit=f['limit']
    imported=DetectionImport.objects.filter(source__sensor=f['sensor'],date__range=(f['start_date'],f['end_date']),status='DATOS_DISPONIBLES')
    # Coverage is reported as import provenance, never inferred from an empty point list.
    coverage=list(imported.values('source_id','date','area','records'))
    if f['aggregate'] or count>5000:
        size=f['cell_degrees']
        while True:
            grouped=qs.order_by().annotate(gx=Floor((__import__('django.db.models',fromlist=['F']).F('longitude')+Value(180.0))/Value(size)),gy=Floor((__import__('django.db.models',fromlist=['F']).F('latitude')+Value(90.0))/Value(size))).values('gx','gy').annotate(count=Count('id'),longitude=Avg('longitude'),latitude=Avg('latitude'))
            clusters=list(grouped[:2001])
            if len(clusters)<=2000:break
            size*=2
        return Response({'status':'DATOS_DISPONIBLES' if count else 'DATOS_NO_IMPORTADOS','count':count,'mode':'aggregated','cell_degrees':size,'results':clusters,'imports':coverage})
    rows=[{'id':o.pk,'latitude':o.latitude,'longitude':o.longitude,'observed_at':o.observed_at,'satellite':o.satellite,'source':o.source_id,'original':o.original} for o in qs.order_by('pk')[offset:offset+limit]]
    return Response({'status':'DATOS_DISPONIBLES' if count else 'DATOS_NO_IMPORTADOS' if not coverage else 'SIN_DETECCIONES_EN_DATOS_IMPORTADOS','count':count,'results':rows,'next_offset':offset+limit if offset+limit<count else None,'imports':coverage,'note':'Una lista FIRMS vacia no acredita cobertura ni ausencia de incendios.'})

@api_view(['GET'])
def sensors(request):
    return Response(list(SatelliteSource.objects.values('id','sensor','platform')))

@api_view(['GET'])
def dates(request):
    qs=FireDetection.objects.all()
    sensor=request.query_params.get('sensor')
    if sensor:
        if sensor not in ('modis','viirs'):raise ValidationError('Sensor invalido')
        qs=qs.filter(source__sensor=sensor)
    return Response({'dates':list(qs.annotate(day=TruncDate('observed_at',tzinfo=timezone.utc)).order_by('day').values_list('day',flat=True).distinct())})
