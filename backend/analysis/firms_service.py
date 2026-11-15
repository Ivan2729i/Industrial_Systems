"""Bounded read-through FIRMS imports; viewport requests never trigger downloads."""
from datetime import timedelta
from io import StringIO
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from .models import DetectionImport
from .nasa import FIRMSClient, NASAError


def ensure_day(sensor, day, area):
    prefix = 'MODIS' if sensor == 'modis' else 'VIIRS_SNPP'
    sources = [prefix + '_SP', prefix + '_NRT']
    completed = DetectionImport.objects.filter(source_id__in=sources, date=day, status='DATOS_DISPONIBLES')
    for run in completed:
        if run.area == 'world' or run.area == area:
            return 'CACHE_POSTGRESQL'
        w,s,e,n = map(float, run.area.split(','))
        if area != 'world':
            a,b,c,d = map(float, area.split(','))
            if w <= a <= c <= e and s <= b <= d <= n:
                return 'CACHE_POSTGRESQL'
    key = f'firms:{sensor}:{day}:{area}'
    previous = cache.get(key)
    if previous:
        return previous
    if area != 'world':
        w,s,e,n = map(float, area.split(','))
    if area != 'world' and (e-w)*(n-s) > 1000:
        return 'REGION_DEMASIADO_GRANDE'
    if not cache.add(key + ':lock', True, 180):
        return 'CONSULTA_EN_CURSO'
    try:
        client = FIRMSClient()
        for source in sources:
            availability_key = 'availability:' + source
            available = cache.get(availability_key)
            if available is None:
                available = client.availability(source)
                cache.set(availability_key, available, 3600)
            if any(r.get('min_date','9999') <= day.isoformat() <= r.get('max_date','') for r in available):
                call_command('import_firms', source=source, start=day.isoformat(), end=day.isoformat(), bbox=area, stdout=StringIO())
                cache.set(key, 'NASA_RECUPERADO', 300)
                return 'NASA_RECUPERADO'
        result = 'DATOS_NO_DISPONIBLES_EN_NASA'
    except (NASAError, CommandError):
        result = 'ERROR_NASA_O_CREDENCIAL_NO_CONFIGURADA'
    finally:
        cache.delete(key + ':lock')
    cache.set(key, result, 60)
    return result
