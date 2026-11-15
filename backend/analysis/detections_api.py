from datetime import timedelta, datetime, time, timezone
from django.db.models import Count, Min, Max, Avg, FloatField, Value
from django.db.models.functions import Floor, TruncDate
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from .models import FireDetection, DetectionImport, SatelliteSource
from .nasa import bounding_box, split_bounding_box

class Query(serializers.Serializer):
    start_date=serializers.DateField()
    end_date=serializers.DateField()
    sensor=serializers.ChoiceField(choices=['modis','viirs'])
    bbox=serializers.CharField(default='world')
    satellite=serializers.CharField(required=False)
    region=serializers.SlugField(required=False)
    retrieve=serializers.BooleanField(default=False)
    limit=serializers.IntegerField(default=2000,min_value=1,max_value=5000)
    aggregate=serializers.BooleanField(default=False)
    detail=serializers.BooleanField(default=False)
    cell_degrees=serializers.FloatField(default=2,min_value=.05,max_value=10)
    offset=serializers.IntegerField(default=0,min_value=0)

@api_view(['GET'])
def detections(request):
    form=Query(data=request.query_params);form.is_valid(raise_exception=True);f=form.validated_data
    if not 0<=(f['end_date']-f['start_date']).days<=30:raise ValidationError('Rango maximo: 31 dias')
    try:areas=split_bounding_box(f['bbox']);area=areas[0]
    except ValueError as e:raise ValidationError(str(e))
    if 'region' in f:
        from .models import Region
        region=Region.objects.filter(pk=f['region']).first()
        if not region or any(v is None for v in [region.west,region.south,region.east,region.north]): raise ValidationError('Region sin limites')
        area=bounding_box(','.join(map(str,[region.west,region.south,region.east,region.north])))
    if 'region' in f: areas=[area]
    retrieval=[]
    if f['retrieve']:
        if area=='world' and (f['end_date']-f['start_date']).days>2:
            sources=['MODIS_SP','MODIS_NRT'] if f['sensor']=='modis' else ['VIIRS_SNPP_SP','VIIRS_SNPP_NRT']
            cached_days=set(DetectionImport.objects.filter(source_id__in=sources,area='world',status='DATOS_DISPONIBLES',date__range=(f['start_date'],f['end_date'])).values_list('date',flat=True))
            if len(cached_days)!=(f['end_date']-f['start_date']).days+1:raise ValidationError('La descarga mundial de fechas nuevas admite hasta 3 días; selecciona un área o reduce el intervalo.')
        from .firms_service import ensure_day
        for i in range((f['end_date']-f['start_date']).days+1):
            for part in areas: retrieval.append(ensure_day(f['sensor'], f['start_date']+timedelta(days=i), part))
    qs=FireDetection.objects.filter(source__sensor=f['sensor'],observed_at__gte=datetime.combine(f['start_date'],time.min,tzinfo=timezone.utc),observed_at__lt=datetime.combine(f['end_date']+timedelta(days=1),time.min,tzinfo=timezone.utc)).select_related('source')
    if area!='world':
        from django.db.models import Q
        spatial=Q()
        for part in areas:
            w,s,e,n=map(float,part.split(','));spatial |= Q(longitude__gte=w,longitude__lte=e,latitude__gte=s,latitude__lte=n)
        qs=qs.filter(spatial)
    if 'satellite' in f:
        names={'aqua':'Aqua','terra':'Terra','snpp':'N','noaa20':'N20','noaa21':'N21'}
        qs=qs.filter(satellite__iexact=names.get(f['satellite'].lower(),f['satellite']))
    if f['sensor']=='viirs': qs=qs.filter(source_id__in=['VIIRS_SNPP_SP','VIIRS_SNPP_NRT'])
    count=qs.count();offset=f['offset'];limit=f['limit']
    imported=DetectionImport.objects.filter(source__sensor=f['sensor'],date__range=(f['start_date'],f['end_date']),status='DATOS_DISPONIBLES')
    if f['sensor']=='viirs': imported=imported.filter(source_id__in=['VIIRS_SNPP_SP','VIIRS_SNPP_NRT'])
    # Coverage is reported as import provenance, never inferred from an empty point list.
    coverage=list(imported.values('source_id','date','area','records'))
    def covers(stored,requested):
        if stored=='world':return True
        if requested=='world':return False
        w,s,e,n=map(float,stored.split(','));a,b,c,d=map(float,requested.split(','))
        return w<=a<=c<=e and s<=b<=d<=n
    missing_dates=[]
    for i in range((f['end_date']-f['start_date']).days+1):
        day=f['start_date']+timedelta(days=i)
        if not all(any(r['date']==day and covers(r['area'],part) for r in coverage) for part in areas):missing_dates.append(day)
    status=('DATOS_PARCIALES' if count else 'DATOS_NO_IMPORTADOS') if missing_dates else ('DATOS_DISPONIBLES' if count else 'SIN_DETECCIONES')
    if any('ERROR' in r for r in retrieval): status='ERROR_DE_CONSULTA'
    elif any('NO_DISPONIBLES' in r for r in retrieval): status='FUERA_DE_DISPONIBILIDAD'
    elif any(r in ['REGION_DEMASIADO_GRANDE','CONSULTA_EN_CURSO'] for r in retrieval): status=retrieval[-1]
    if f['aggregate'] or (count>5000 and not f['detail']):
        size=f['cell_degrees']
        while True:
            grouped=qs.order_by().annotate(gx=Floor((__import__('django.db.models',fromlist=['F']).F('longitude')+Value(180.0))/Value(size)),gy=Floor((__import__('django.db.models',fromlist=['F']).F('latitude')+Value(90.0))/Value(size))).values('gx','gy').annotate(count=Count('id'),longitude=Avg('longitude'),latitude=Avg('latitude'))
            clusters=list(grouped[:2001])
            if len(clusters)<=2000:break
            size*=2
        return Response({'status':status,'count':count,'mode':'aggregated','cell_degrees':size,'results':clusters,'retrieval':retrieval,'imports':coverage,'missing_dates':missing_dates})
    rows=[{'id':o.pk,'latitude':o.latitude,'longitude':o.longitude,'observed_at':o.observed_at,'satellite':o.satellite,'source':o.source_id,'original':o.original} for o in qs.order_by('pk')[offset:offset+limit]]
    return Response({'status':status,'count':count,'results':rows,'next_offset':offset+limit if offset+limit<count else None,'retrieval':retrieval,'imports':coverage,'missing_dates':missing_dates,'note':'Una lista FIRMS vacia no acredita cobertura ni ausencia de incendios.'})

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


@api_view(['GET'])
def availability(request):
    from django.core.cache import cache
    from .nasa import FIRMSClient, NASAError
    sensor=request.query_params.get('sensor','modis')
    if sensor not in ('modis','viirs'): raise ValidationError('Sensor invalido')
    prefix='MODIS' if sensor=='modis' else 'VIIRS_SNPP'
    try:
        products=[]
        for source in [prefix+'_SP',prefix+'_NRT']:
            rows=cache.get('availability:'+source)
            if rows is None:
                rows=FIRMSClient().availability(source)
                cache.set('availability:'+source,rows,3600)
            products.extend(dict(row,source=source) for row in rows)
        valid=[p for p in products if p.get('min_date') and p.get('max_date')]
        if not valid: raise NASAError('Disponibilidad no verificable')
        return Response({'sensor':sensor,'min_date':min(p['min_date'] for p in valid),'max_date':max(p['max_date'] for p in valid),'products':valid,'timezone':'UTC'})
    except NASAError:
        return Response({'detail':'No fue posible consultar disponibilidad NASA.'},status=502)
