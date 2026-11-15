import math
import h3
from django.db import connection, DatabaseError
from django.db.models import Count, Sum, Q
from rest_framework import generics, serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from .models import H3Observation, Region, OverpassPair
from .serializers import ObservationSerializer, RegionSerializer
from .schema import CLASSES, STRATA

class Filters(serializers.Serializer):
    region = serializers.SlugField(required=False)
    date = serializers.DateField(required=False)
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    sensor = serializers.ChoiceField(choices=['modis','viirs'], required=False)
    fire_only = serializers.BooleanField(required=False)
    version = serializers.CharField(default='v1_experimental')
    pair = serializers.IntegerField(min_value=1, required=False)
    classification = serializers.ChoiceField(choices=CLASSES, required=False)
    stratum = serializers.ChoiceField(choices=STRATA, required=False)
    bbox = serializers.CharField(required=False)
    def validate(self, attrs):
        if 'start' in attrs and 'end' in attrs and attrs['start'] > attrs['end']:
            raise serializers.ValidationError('start debe ser anterior a end')
        if 'bbox' in attrs:
            try:
                bounds = [float(v) for v in attrs['bbox'].split(',')]
                west,south,east,north = bounds
                if not all(math.isfinite(v) for v in bounds) or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                    raise ValueError
            except ValueError:
                raise serializers.ValidationError({'bbox':'Usa oeste,sur,este,norte en WGS84; sin cruzar el antimeridiano.'})
            attrs['bbox'] = bounds
        return attrs

def filtered(request, require_scope=False):
    params = Filters(data=request.query_params)
    params.is_valid(raise_exception=True)
    f = params.validated_data
    if require_scope and not any(key in f for key in ['date','region','bbox','start']):
        raise ValidationError('Especifica region, date, start o bbox para limitar la consulta.')
    if f.get('region') and not Region.objects.filter(pk=f['region']).exists():
        raise ValidationError({'region':'Region desconocida'})
    qs = H3Observation.objects.select_related('pair','pair__region').filter(version_armonizacion=f['version'])
    for key, lookup in [('region','pair__region_id'),('date','pair__date'),('start','pair__date__gte'),('end','pair__date__lte'),('pair','pair_id'),('classification','coincidencia_original'),('stratum','estrato_temporal')]:
        if key in f: qs = qs.filter(**{lookup:f[key]})
    if f.get('sensor'): qs = qs.filter(**{f['sensor']+'_pixeles__gt':0})
    if f.get('fire_only'):
        qs = qs.filter(**{f['sensor']+'_fuego__gt':0}) if f.get('sensor') else qs.filter(Q(modis_fuego__gt=0)|Q(viirs_fuego__gt=0))
    if 'bbox' in f:
        west,south,east,north = f['bbox']
        # Include H3 polygons intersecting the bounding box, not only their centers.
        shape = h3.LatLngPoly([(south,west),(south,east),(north,east),(north,west)])
        resolutions = qs.order_by().values_list('resolucion_h3',flat=True).distinct()
        cells = []
        for resolution in resolutions:
            if h3.average_hexagon_area(resolution, 'km^2') and (east-west)*(north-south)*12365 / h3.average_hexagon_area(resolution, 'km^2') > 100000:
                raise ValidationError({'bbox':'Extension excesiva para esta resolucion; reduce el area.'})
            cells.extend(h3.polygon_to_cells_experimental(shape,resolution,contain='overlap'))
        qs = qs.filter(celda_h3__in=cells)
    return qs

class Pagination(LimitOffsetPagination):
    default_limit = 100
    max_limit = 1000
    def paginate_queryset(self, queryset, request, view=None):
        for key in ['limit','offset']:
            if key in request.query_params:
                try: value = int(request.query_params[key])
                except ValueError: raise ValidationError({key:'Se requiere un entero'})
                if value < (1 if key=='limit' else 0) or (key=='limit' and value>self.max_limit):
                    raise ValidationError({key:'Valor fuera de rango'})
        return super().paginate_queryset(queryset,request,view)

class Observations(generics.ListAPIView):
    serializer_class = ObservationSerializer
    pagination_class = Pagination
    def get_queryset(self): return filtered(self.request)

class Observation(generics.RetrieveAPIView):
    serializer_class = ObservationSerializer
    queryset = H3Observation.objects.select_related('pair','pair__region')

@api_view(['GET'])
def health(request):
    try:
        with connection.cursor() as cursor: cursor.execute('SELECT 1')
        return Response({'status':'ok','database':'postgresql'})
    except DatabaseError:
        return Response({'status':'unavailable','database':'postgresql'},status=503)

@api_view(['GET'])
def regions(request):
    return Response(RegionSerializer(Region.objects.order_by('id'),many=True).data)

@api_view(['GET'])
def dates(request):
    qs = OverpassPair.objects.all()
    if request.query_params.get('region'): qs = qs.filter(region_id=request.query_params['region'])
    return Response({'dates':list(qs.order_by('date').values_list('date',flat=True).distinct())})

@api_view(['GET'])
def summary(request):
    qs = filtered(request)
    sums = qs.aggregate(total=Count('id'),modis_fire_original=Sum('modis_fuego'),viirs_fire_original=Sum('viirs_fuego'),viirs_fire_without_bowtie=Sum('viirs_fuego_sin_bowtie'),viirs_fire_qa_nominal=Sum('viirs_fuego_qa_nominal'))
    sums['original'] = list(qs.values('coincidencia_original').annotate(count=Count('id')).order_by('coincidencia_original'))
    sums['qa'] = list(qs.values('coincidencia_qa').annotate(count=Count('id')).order_by('coincidencia_qa'))
    sums['pairs'] = list(qs.values('pair_id','pair__date','pair__modis_sobrevuelo','pair__viirs_sobrevuelo').annotate(count=Count('id')).order_by('pair_id'))
    return Response({'methodology':'experimental; sin correccion estadistica validada de sensibilidad',**sums})

@api_view(['GET'])
def map_view(request):
    qs = filtered(request,require_scope=True)
    paginator = Pagination()
    page = paginator.paginate_queryset(qs,request)
    features = []
    for observation, properties in zip(page,ObservationSerializer(page,many=True).data):
        boundary = [[lng,lat] for lat,lng in h3.cell_to_boundary(observation.celda_h3)]
        boundary.append(boundary[0])
        features.append({'type':'Feature','id':observation.pk,'geometry':{'type':'Polygon','coordinates':[boundary]},'properties':properties})
    return Response({'type':'FeatureCollection','features':features,'count':paginator.count,'next':paginator.get_next_link(),'previous':paginator.get_previous_link()})

@api_view(['GET'])
def runs(request):
    from .models import DataImport
    return Response(list(DataImport.objects.filter(status='success').values('id','version','imported_at','processed','inserted','unchanged','status').order_by('-id')[:200]))

@api_view(['GET'])
def scientific_runs(request):
    from .models import HarmonizationRun
    return Response(list(HarmonizationRun.objects.order_by('-id').values('id','region_id','date','version','resolution','status','parameters','products','records','error_type')[:200]))
