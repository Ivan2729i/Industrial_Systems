"""Bounded read-through FIRMS imports; viewport requests never trigger downloads."""
from datetime import timedelta
import hashlib
from django.db import connection
from io import StringIO
from django.core.cache import cache
from django.utils import timezone
from django.core.management import call_command
from django.core.management.base import CommandError
from .models import DetectionImport
from .nasa import FIRMSClient, NASAError


def ensure_day(sensor, day, area):
    prefix = 'MODIS' if sensor == 'modis' else 'VIIRS_SNPP'
    sources = [prefix + '_SP', prefix + '_NRT']
    completed = DetectionImport.objects.filter(source_id__in=sources, date=day, status='DATOS_DISPONIBLES')
    for run in completed:
        if str(run.source_id).endswith('_NRT') and (not run.finished_at or (timezone.now()-run.finished_at).total_seconds()>1800):continue
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
    held=[]
    try:
        with connection.cursor() as cursor:
            identity=int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],'big',signed=True)
            cursor.execute('SELECT pg_try_advisory_lock(%s)',[identity])
            if not cursor.fetchone()[0]:return 'CONSULTA_EN_CURSO'
            held.append(identity)
            for slot in (7241721,7241722):
                cursor.execute('SELECT pg_try_advisory_lock(%s)',[slot])
                if cursor.fetchone()[0]:held.append(slot);break
            if len(held)<2:return 'CONSULTA_EN_CURSO'
        client = FIRMSClient()
        for source in sources:
            availability_key = 'availability:' + source
            available = cache.get(availability_key)
            if available is None:
                available = client.availability(source)
                cache.set(availability_key, available, 3600)
            if any(r.get('min_date','9999') <= day.isoformat() <= r.get('max_date','') for r in available):
                call_command('import_firms', source=source, start=day.isoformat(), end=day.isoformat(), bbox=area, refresh=source.endswith('_NRT'), stdout=StringIO())
                cache.set(key, 'NASA_RECUPERADO', 300)
                return 'NASA_RECUPERADO'
        result = 'DATOS_NO_DISPONIBLES_EN_NASA'
    except (NASAError, CommandError):
        result = 'ERROR_NASA_O_CREDENCIAL_NO_CONFIGURADA'
    finally:
        with connection.cursor() as cursor:
            for lock in reversed(held):cursor.execute('SELECT pg_advisory_unlock(%s)',[lock])
        cache.delete(key + ':lock')
    cache.set(key, result, 60)
    return result
