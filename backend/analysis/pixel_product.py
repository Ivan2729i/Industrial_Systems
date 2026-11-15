"""Transactional import of conserved Level-2 pixels and association memberships."""
from datetime import datetime
from django.db import transaction,connection
from .models import Level2FirePixel,HarmonizedDetection,HarmonizedDetectionMember

class AssociationScopeConflict(ValueError):
    pass

def persist_pixel_product(payload,pair,version):
    from hashlib import sha256
    import json
    import math,h3
    pixels={p['id']:p for p in payload['pixels']}
    if len(pixels)!=len(payload['pixels']):raise ValueError('Repeated source pixel identity')
    for pixel in pixels.values():
        if pixel['sensor'] not in ('MODIS','VIIRS') or pixel['fire_class'] not in (7,8,9):raise ValueError('Invalid Level-2 fire pixel')
        if not(math.isfinite(pixel['latitude']) and math.isfinite(pixel['longitude']) and -90<=pixel['latitude']<=90 and -180<=pixel['longitude']<=180):raise ValueError('Invalid original geolocation')
    for group in payload['detections']:
        if not group['members'] or group['representative'] not in group['members']:raise ValueError('Representative must be an original member')
        m=sum(pixels[i]['sensor']=='MODIS' for i in group['members']);v=len(group['members'])-m
        if not ((group['status']=='ASOCIADA' and m==1 and v>=1) or (group['status']=='SOLO_MODIS' and m==1 and v==0) or (group['status']=='SOLO_VIIRS' and m==0 and v==1) or (group['status']=='SIN_COMPARABILIDAD' and m+v==1)):raise ValueError('Association membership inconsistent with status')
        rep=pixels[group['representative']]
        if not h3.is_valid_cell(group['h3']) or h3.latlng_to_cell(rep['latitude'],rep['longitude'],h3.get_resolution(group['h3']))!=group['h3']:raise ValueError('Invalid representative H3')
    ids=[p for group in payload['detections'] for p in group['members']]
    if len(ids)!=len(set(ids)) or set(ids)!=set(pixels):raise ValueError('Positive pixel conservation violated')
    with transaction.atomic():
        lock_id=int.from_bytes(sha256(json.dumps([pair.modis_sobrevuelo,pair.viirs_sobrevuelo,payload['method']]).encode()).digest()[:8],byteorder='big',signed=True)
        with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_xact_lock(%s)',[lock_id])
        for identity,p in pixels.items():
            values={k:v for k,v in p.items() if k!='id'};values.setdefault('h3_r7',__import__('h3').latlng_to_cell(p['latitude'],p['longitude'],7));values['observed_at']=datetime.fromisoformat(values['observed_at'])
            obj,created=Level2FirePixel.objects.get_or_create(pk=identity,defaults=values)
            if not created and any(getattr(obj,k)!=v for k,v in values.items()):raise ValueError('Immutable source pixel differs')
        for group in payload['detections']:
            representative=pixels[group['representative']]
            identity=sha256(json.dumps([pair.pk,version,payload['method'],sorted(group['members'])]).encode()).hexdigest()
            canonical=sha256(json.dumps([pair.modis_sobrevuelo,pair.viirs_sobrevuelo,payload['method'],group['status'],sorted(group['members'])]).encode()).hexdigest()
            conflicts=HarmonizedDetectionMember.objects.filter(pixel_id__in=group['members'],pair__modis_sobrevuelo=pair.modis_sobrevuelo,pair__viirs_sobrevuelo=pair.viirs_sobrevuelo,detection__method=payload['method']).exclude(detection__canonical_key=canonical)
            if conflicts.exists():raise AssociationScopeConflict('Incompatible overlapping pixel associations: process a coherent combined scope with an explicit new method revision')
            values={'canonical_key':canonical,'pair':pair,'version':version,'method':payload['method'],'status':group['status'],'representative_id':representative['id'],'observed_at':datetime.fromisoformat(representative['observed_at']),'latitude':representative['latitude'],'longitude':representative['longitude'],'h3':group['h3'],'modis_count':sum(pixels[i]['sensor']=='MODIS' for i in group['members']),'viirs_count':sum(pixels[i]['sensor']=='VIIRS' for i in group['members']),'assessment':group['assessment']}
            result,created=HarmonizedDetection.objects.get_or_create(pk=identity,defaults=values)
            def equivalent(key,value):
                old=getattr(result,key)
                if key=='assessment':
                    old=dict(old);value=dict(value)
                    old.pop('h3_source_version',None);value.pop('h3_source_version',None)
                return old==value
            if not created and any(not equivalent(k,v) for k,v in values.items()):raise ValueError('Product changed; use a new scientific version')
            for member in group['members']:
                link,created=HarmonizedDetectionMember.objects.get_or_create(pixel_id=member,pair=pair,version=version,defaults={'detection':result})
                if link.detection_id!=identity:raise ValueError('Pixel assigned twice; use a new scientific version')
    return len(payload['detections'])
