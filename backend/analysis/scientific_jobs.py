"""Bounded administrative queue. Scientific work is performed by management worker."""
import hashlib, json, os, secrets
from datetime import date
from django.db import transaction, connection
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Region, HarmonizationRun
from .nasa import bounding_box

class JobQuery(serializers.Serializer):
    date=serializers.DateField()
    bbox=serializers.CharField()
    version=serializers.RegexField(r'^[a-zA-Z0-9_-]{1,80}$')
    resolution=serializers.IntegerField(default=7,min_value=5,max_value=8)
    def validate(self, attrs):
        try: attrs['bbox']=bounding_box(attrs['bbox'])
        except ValueError: raise serializers.ValidationError('BBox WGS84 invalido')
        if attrs['bbox']=='world': raise serializers.ValidationError('Divide el mundo en particiones regionales mediante el planificador CLI.')
        w,s,e,n=map(float,attrs['bbox'].split(','))
        if not (-180<w<e<180 and -85<s<n<85) or (e-w)*(n-s)>.25:
            raise serializers.ValidationError('Procesamiento local: area maxima 0.25 grados cuadrados, sin polos; particiona areas mayores.')
        if attrs['version']=='v1_experimental': raise serializers.ValidationError('El piloto V1 es inmutable; usa otra version.')
        return attrs

def enqueue(params):
    public={**params,'date':str(params['date']),'kind':'regional_request'}
    identity=hashlib.sha256(json.dumps(public,sort_keys=True).encode()).hexdigest()
    w,s,e,n=map(float,public['bbox'].split(','))
    with transaction.atomic():
        with connection.cursor() as cursor: cursor.execute('SELECT pg_advisory_xact_lock(7241702)')
        existing=HarmonizationRun.objects.filter(key=identity).first()
        if existing:return existing,False
        if HarmonizationRun.objects.filter(status='PROCESAMIENTO_PENDIENTE',parameters__kind='regional_request').count()>=16:
            from rest_framework.exceptions import Throttled
            raise Throttled(detail='Cola local completa')
        # Lock a stable region row to serialize bounded queue admission.
        region,_=Region.objects.get_or_create(id='area-'+identity[:20],defaults={'name':'Area '+public['bbox'],'west':w,'south':s,'east':e,'north':n})
        Region.objects.select_for_update().get(pk=region.pk)
        run,created=HarmonizationRun.objects.get_or_create(key=identity,defaults={'region':region,'date':public['date'],'version':public['version'],'resolution':public['resolution'],'status':'PROCESAMIENTO_PENDIENTE','parameters':public})
    return run,created

@api_view(['POST'])
def submit(request):
    expected=os.getenv('SCIENTIFIC_ADMIN_KEY','')
    if not expected: return Response({'detail':'Administracion cientifica no configurada.'},status=503)
    if not secrets.compare_digest(request.headers.get('X-Scientific-Key',''),expected):
        return Response({'detail':'Autorizacion cientifica requerida.'},status=403)
    form=JobQuery(data=request.data);form.is_valid(raise_exception=True)
    if HarmonizationRun.objects.filter(status='PROCESAMIENTO_PENDIENTE',parameters__kind='regional_request').count()>=16:
        return Response({'detail':'Cola local completa.'},status=429)
    run,created=enqueue(form.validated_data)
    return Response({'id':run.pk,'status':run.status,'created':created},status=202)
