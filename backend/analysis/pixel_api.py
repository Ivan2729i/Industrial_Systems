from datetime import datetime,time,timedelta,timezone
from django.db.models import Q
from rest_framework import serializers,generics
from .models import HarmonizedDetection,HarmonizedDetectionMember,Level2FirePixel,HarmonizationRun
from .api import Pagination
from .nasa import split_bounding_box

class PixelSerializer(serializers.ModelSerializer):
    observed_at=serializers.DateTimeField(default_timezone=timezone.utc)
    class Meta:
        model=Level2FirePixel
        fields='__all__'
class MemberSerializer(serializers.ModelSerializer):
    pixel=PixelSerializer(read_only=True)
    class Meta:
        model=HarmonizedDetectionMember
        fields=['pixel']
class ProductSerializer(serializers.ModelSerializer):
    h3_source_version=serializers.SerializerMethodField()
    def get_h3_source_version(self,obj):return obj.version.split('__',1)[1] if '__' in obj.version else obj.assessment.get('h3_source_version')
    geolocation_uncertainty_m=serializers.SerializerMethodField()
    def get_geolocation_uncertainty_m(self,obj): return None
    observed_at=serializers.DateTimeField(default_timezone=timezone.utc)
    members=MemberSerializer(many=True,read_only=True)
    region_id=serializers.CharField(source='pair.region_id',read_only=True)
    modis_granule=serializers.CharField(source='pair.modis_sobrevuelo',read_only=True)
    viirs_granule=serializers.CharField(source='pair.viirs_sobrevuelo',read_only=True)
    class Meta:
        model=HarmonizedDetection
        fields='__all__'
class Filters(serializers.Serializer):
    date=serializers.DateField(required=False)
    start=serializers.DateField(required=False)
    end=serializers.DateField(required=False)
    bbox=serializers.CharField(required=False)
    version=serializers.CharField(required=False)
    status=serializers.ChoiceField(choices=['ASOCIADA','SOLO_MODIS','SOLO_VIIRS','SIN_COMPARABILIDAD'],required=False)
    def validate(self,data):
        if data.get('date'):
            data.setdefault('start',data['date']);data.setdefault('end',data['date'])
        if 'start' not in data or 'end' not in data:raise serializers.ValidationError('Indica date o start/end UTC')
        if not 0<=(data['end']-data['start']).days<=30:raise serializers.ValidationError('Selecciona hasta 31 dias UTC')
        if data.get('bbox'):
            try:data['areas']=split_bounding_box(data['bbox'])
            except ValueError:raise serializers.ValidationError('BBox WGS84 invalido')
        return data
class Detections(generics.ListAPIView):
    serializer_class=ProductSerializer
    pagination_class=Pagination
    def get_queryset(self):
        form=Filters(data=self.request.query_params);form.is_valid(raise_exception=True);f=form.validated_data
        qs=HarmonizedDetection.objects.filter(observed_at__gte=datetime.combine(f['start'],time.min,tzinfo=timezone.utc),observed_at__lt=datetime.combine(f['end']+timedelta(days=1),time.min,tzinfo=timezone.utc)).select_related('pair','representative').prefetch_related('members__pixel').order_by('observed_at','id')
        for field in ['version','status']:
            if field in f:qs=qs.filter(**{field:f[field]})
        if f.get('areas') and 'world' not in f['areas']:
            spatial=Q()
            for area in f['areas']:
                w,s,e,n=map(float,area.split(','));spatial|=Q(longitude__gte=w,longitude__lte=e,latitude__gte=s,latitude__lte=n)
            qs=qs.filter(spatial)
        return qs.order_by('canonical_key','-version','id').distinct('canonical_key')


from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Count
from django.db.models.functions import TruncDate
@api_view(['GET'])
def catalog(request):
    qs=HarmonizedDetection.objects.all()
    scopes=[]
    for run in HarmonizationRun.objects.filter(status='COMPLETADO',parameters__has_key='pixel_product').select_related('region').order_by('-id')[:200]:
        scopes.append({'date':run.date,'bbox':[run.region.west,run.region.south,run.region.east,run.region.north],'h3_source_version':run.version,'positive_source_pixels':run.parameters['pixel_product']['input_positive_pixels'],'unified_detections':run.parameters['pixel_product']['output_detections']})
    dates=set(qs.annotate(day=TruncDate('observed_at',tzinfo=timezone.utc)).values_list('day',flat=True))|{scope['date'] for scope in scopes}
    return Response({'versions':list(qs.values('version').annotate(count=Count('canonical_key',distinct=True)).order_by('version')),'dates':sorted(dates),'processed_scopes':scopes,'global_coverage_complete':False})

class Detail(generics.RetrieveAPIView):
    serializer_class=ProductSerializer
    queryset=HarmonizedDetection.objects.select_related('pair','representative').prefetch_related('members__pixel')
class SourcePixels(generics.ListAPIView):
    serializer_class=PixelSerializer
    pagination_class=Pagination
    def get_queryset(self):
        form=Filters(data=self.request.query_params);form.is_valid(raise_exception=True);f=form.validated_data
        qs=Level2FirePixel.objects.filter(observed_at__gte=datetime.combine(f['start'],time.min,tzinfo=timezone.utc),observed_at__lt=datetime.combine(f['end']+timedelta(days=1),time.min,tzinfo=timezone.utc)).order_by('id')
        membership={}
        if f.get('version'):membership['harmonizeddetectionmember__version']=f['version']
        if f.get('status'):membership['harmonizeddetectionmember__detection__status']=f['status']
        if membership:qs=qs.filter(**membership).distinct()
        sensor=self.request.query_params.get('sensor','').upper()
        if sensor:
            if sensor not in ('MODIS','VIIRS'):raise serializers.ValidationError('Sensor Level 2 invalido')
            qs=qs.filter(sensor=sensor)
        if f.get('areas') and 'world' not in f['areas']:
            spatial=Q()
            for a in f['areas']:
                w,s,e,n=map(float,a.split(','));spatial|=Q(longitude__gte=w,longitude__lte=e,latitude__gte=s,latitude__lte=n)
            qs=qs.filter(spatial)
        return qs
