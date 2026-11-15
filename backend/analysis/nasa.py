"""Official NASA connectors. Never include authenticated URLs in errors."""
import csv
import io
import json
import math
import os
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

SOURCES = tuple(prefix + suffix for prefix in ('MODIS', 'VIIRS_SNPP', 'VIIRS_NOAA20', 'VIIRS_NOAA21') for suffix in ('_NRT', '_SP'))

class NASAError(Exception):
    pass

def bounding_box(value):
    if value == 'world':
        return value
    try:
        west, south, east, north = map(float, value.split(','))
        if not all(math.isfinite(v) for v in (west,south,east,north)) or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError
    except (ValueError, AttributeError):
        raise ValueError('bbox debe ser world u oeste,sur,este,norte; divide consultas que crucen el antimeridiano.') from None
    return ','.join(map(str,(west,south,east,north)))

def open_nasa(url):
    try:
        return urlopen(Request(url,headers={'User-Agent':'FireSight/1.0','Accept':'application/json,text/csv'}),timeout=60)
    except HTTPError as exc:
        code=exc.code
        message={401:'Credenciales NASA invalidas',403:'Acceso NASA denegado',429:'Limite NASA alcanzado; reanuda mas tarde'}.get(code,'Servicio NASA no disponible')
        raise NASAError(f'{message} (HTTP {code}).') from None
    except (URLError, TimeoutError):
        raise NASAError('No fue posible conectar con NASA.') from None

class FIRMSClient:
    def __init__(self):
        self.key=os.getenv('FIRMS_MAP_KEY','').strip()
        if not self.key:
            raise NASAError('Configura FIRMS_MAP_KEY en backend/.env.')
    def availability(self, source):
        if source not in SOURCES: raise ValueError('Fuente FIRMS desconocida')
        with open_nasa(f'https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/{quote(self.key,safe="")}/{source}') as response:
            return list(csv.DictReader(io.TextIOWrapper(response,encoding='utf-8-sig')))
    def rows(self, source, day, area='world'):
        if source not in SOURCES: raise ValueError('Fuente FIRMS desconocida')
        day=date.fromisoformat(day).isoformat()
        area=bounding_box(area)
        # One day per request: resumable units below the documented five-day maximum.
        url=f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{quote(self.key,safe="")}/{source}/{area}/1/{day}'
        with open_nasa(url) as response:
            reader=csv.DictReader(io.TextIOWrapper(response,encoding='utf-8-sig'))
            if not {'latitude','longitude','acq_date','acq_time','satellite'}.issubset(reader.fieldnames or []):
                raise NASAError('FIRMS devolvio una respuesta sin el esquema esperado; no se considera ausencia de detecciones.')
            yield from reader

class CMRClient:
    base='https://cmr.earthdata.nasa.gov/search/'
    def search(self, kind, **params):
        if kind not in ('collections','granules'): raise ValueError('Recurso CMR invalido')
        page=1
        while True:
            query=urlencode({**params,'page_size':200,'page_num':page})
            with open_nasa(self.base+kind+'.json?'+query) as response:
                entries=json.load(response)['feed']['entry']
            yield from entries
            if len(entries)<200: break
            page+=1
    def collections(self, product):
        return self.search('collections',short_name=product)
    def granules(self, collection_id, start, end, bbox):
        start=date.fromisoformat(start);end=date.fromisoformat(end)
        if start>end: raise ValueError('Rango temporal invertido')
        area=bounding_box(bbox)
        params={'collection_concept_id':collection_id,'temporal':f'{start}T00:00:00Z,{end}T23:59:59Z'}
        if area!='world': params['bounding_box']=area
        return self.search('granules',**params)
