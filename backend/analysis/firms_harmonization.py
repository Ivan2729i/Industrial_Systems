"""Operational FIRMS integration, deliberately separate from Level-2 science.

Exploratory proximity associations: <=1500 m and <=15 minutes within one UTC
day. One VIIRS to at most one MODIS; one MODIS can anchor multiple VIIRS.
No claim of confirmed events, calibrated sensitivity, QA or shared coverage.
"""
import hashlib
import math
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
import h3
from django.db import connection, transaction
from .models import DetectionImport, FireDetection, FIRMSHarmonizationJob, FIRMSUnifiedDetection
from .firms_service import ensure_day

VERSION = 'firms_operational_v1'
METHOD = 'FIRMS_PROXIMITY_1500M_15MIN_ONE_TO_MANY_V1'


def distance(a, b):
    p, q = math.radians(a.latitude), math.radians(b.latitude)
    dp = q-p
    dl = math.radians(b.longitude-a.longitude)
    value = math.sin(dp/2)**2 + math.cos(p)*math.cos(q)*math.sin(dl/2)**2
    return 6371008.8*2*math.asin(math.sqrt(min(1, max(0, value))))


def associate(modis, viirs):
    # H3 r5 is only a candidate index. A metric distance check is mandatory.
    index = defaultdict(list)
    for m in modis:
        index[h3.latlng_to_cell(m.latitude, m.longitude, 5)].append(m)
    assigned = defaultdict(list)
    singles = []
    for v in sorted(viirs, key=lambda p: p.fingerprint):
        options = []
        for cell in h3.grid_disk(h3.latlng_to_cell(v.latitude, v.longitude, 5), 2):
            for m in index.get(cell, []):
                dt = abs((m.observed_at-v.observed_at).total_seconds())
                if dt > 900:
                    continue
                metres = distance(m, v)
                if metres <= 1500:
                    options.append((metres, dt, m.fingerprint, m))
        if options:
            best = min(options, key=lambda p: p[:3])
            assigned[best[3].pk].append((v, best[0], best[1]))
        else:
            singles.append((v, [], 'SOLO_VIIRS'))
    return [(m, assigned[m.pk], 'ASOCIADA' if assigned[m.pk] else 'SOLO_MODIS') for m in modis] + singles


def sources_for(day):
    result = []
    for prefix in ('MODIS', 'VIIRS_SNPP'):
        available = list(DetectionImport.objects.filter(date=day, area='world', status='DATOS_DISPONIBLES', source_id__in=[prefix+'_SP', prefix+'_NRT']).values_list('source_id', flat=True))
        if not available:
            raise ValueError('WORLD_IMPORT_INCOMPLETE_'+prefix)
        result.append(prefix+'_SP' if prefix+'_SP' in available else prefix+'_NRT')
    return result


def process_day(day, retrieve=False):
    # Global lock serializes the small local worker, with no transaction held over NASA.
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(7241703)')
        if not cursor.fetchone()[0]:
            raise ValueError('WORKER_BUSY')
    job, _ = FIRMSHarmonizationJob.objects.get_or_create(date=day, version=VERSION)
    try:
        if job.status == 'COMPLETADO':
            return job
        job.status='PROCESANDO'; job.error=''; job.save()
        if retrieve:
            for sensor in ('modis','viirs'):
                outcome=ensure_day(sensor, day, 'world')
                if outcome not in ('CACHE_POSTGRESQL','NASA_RECUPERADO'):
                    raise ValueError(outcome)
        sources = sources_for(day)
        start=datetime.combine(day,time.min,tzinfo=timezone.utc)
        # Prefer SP. The same daily product is never mixed with its NRT revision.
        original=list(FireDetection.objects.filter(source_id__in=sources,observed_at__gte=start,observed_at__lt=start+timedelta(days=1)).select_related('source').order_by('fingerprint'))
        # Exact observation identity across repeated source rows. Retain references to
        # all duplicate records, without counting them as distinct measurements.
        unique={}; aliases=defaultdict(list)
        for p in original:
            identity=(p.source.sensor,p.satellite,p.observed_at,p.latitude,p.longitude)
            anchor=unique.setdefault(identity,p)
            aliases[anchor.pk].append(p.pk)
        modis=[p for p in unique.values() if p.source.sensor=='modis']
        viirs=[p for p in unique.values() if p.source.sensor=='viirs']
        groups=associate(modis,viirs)
        with transaction.atomic():
            products=[]; links=[]
            through=FIRMSUnifiedDetection.members.through
            for anchor, matches, status in groups:
                members=[anchor]+[v for v,_,_ in matches]
                identity=hashlib.sha256((VERSION+'|'+str(day)+'|'+','.join(sorted(p.fingerprint for p in members))).encode()).hexdigest()
                products.append(FIRMSUnifiedDetection(id=identity,job=job,representative=anchor,latitude=anchor.latitude,longitude=anchor.longitude,observed_at=anchor.observed_at,status=status,modis_count=int(anchor.source.sensor=='modis'),viirs_count=len(matches) if anchor.source.sensor=='modis' else 1,metadata={'method':METHOD,'max_distance_m':1500,'max_delta_seconds':900,'shared_coverage_evaluated':False,'level2_qa_evaluated':False,'association_exploratory':True,'day_boundary_policy':'same_UTC_day_only','matches':[{'source_id':v.pk,'distance_m':d,'delta_seconds':t} for v,d,t in matches]}))
                for p in members:
                    for original_id in aliases[p.pk]:
                        links.append(through(firmsunifieddetection_id=identity,firedetection_id=original_id))
            FIRMSUnifiedDetection.objects.bulk_create(products,batch_size=1000)
            through.objects.bulk_create(links,batch_size=2000)
            if len(links)!=len(original):
                raise ValueError('SOURCE_CONSERVATION_FAILED')
            job.status='COMPLETADO';job.modis_count=len(modis);job.viirs_count=len(viirs);job.records=len(products)
            job.metadata={'product':'FIRMS_OPERATIONAL','method':METHOD,'sources':sources,'area':'world','source_rows':len(original),'unique_observations':len(unique),'exact_duplicates':len(original)-len(unique),'source_members':len(links),'coverage':'NASA_world_query_completed; not proof of complete satellite coverage','association_scope':'same UTC day; geographic 1500 m / temporal 15 min; exploratory','counts':{status:sum(p.status==status for p in products) for status in ['ASOCIADA','SOLO_MODIS','SOLO_VIIRS']}}
            job.save()
        return job
    except Exception as exc:
        job.status='ERROR';job.error=type(exc).__name__+':'+str(exc) if isinstance(exc,ValueError) else type(exc).__name__;job.save()
        raise
    finally:
        with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_unlock(7241703)')
