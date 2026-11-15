import csv
import hashlib
import math
import runpy
from datetime import date, datetime, timezone
from pathlib import Path
import h3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from analysis.models import Region, OverpassPair, H3Observation, DataImport
from analysis.schema import COUNT_FIELDS, FLOAT_FIELDS, BOOL_FIELDS, TEXT_FIELDS, CLASSES, STRATA

IDENTITY = ['fecha','region_id','region_nombre','modis_sobrevuelo','viirs_sobrevuelo','celda_h3','resolucion_h3','version_armonizacion','metodo','estrato_temporal','coincidencia_original','coincidencia_qa']
REQUIRED = IDENTITY + COUNT_FIELDS + FLOAT_FIELDS + BOOL_FIELDS + TEXT_FIELDS + ['modis_utc','viirs_utc']

def parse_row(row):
    for field in IDENTITY:
        if not row.get(field):
            raise ValueError(f'{field}: valor obligatorio')
    day = date.fromisoformat(row['fecha'])
    if day.isoformat() != row['fecha']:
        raise ValueError('fecha: usa YYYY-MM-DD')
    cell = row['celda_h3']
    resolution = int(row['resolucion_h3'])
    if not h3.is_valid_cell(cell) or h3.get_resolution(cell) != resolution:
        raise ValueError('celda_h3 o resolucion_h3 incompatible')
    values = {f: row[f] or None for f in TEXT_FIELDS}
    for f in COUNT_FIELDS + FLOAT_FIELDS:
        value = row[f]
        if value == '':
            values[f] = None
            continue
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError(f'{f}: numero negativo o no finito')
        if f in COUNT_FIELDS:
            if not number.is_integer():
                raise ValueError(f'{f}: se requiere entero')
            number = int(number)
        if f.endswith('_pct') and number > 100:
            raise ValueError(f'{f}: porcentaje fuera de rango')
        values[f] = number
    for f in BOOL_FIELDS:
        value = row[f]
        if value not in ('', 'True', 'False'):
            raise ValueError(f'{f}: booleano invalido')
        values[f] = None if value == '' else value == 'True'
    for f in ['modis_utc','viirs_utc']:
        value = row[f]
        values[f] = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f UTC').replace(tzinfo=timezone.utc) if value else None
    for f in ['metodo','estrato_temporal','coincidencia_original','coincidencia_qa']:
        values[f] = row[f]
    if values['estrato_temporal'] not in STRATA or any(values[f] not in CLASSES for f in ['coincidencia_original','coincidencia_qa']):
        raise ValueError('clasificacion o estrato desconocido')
    values['resolucion_h3'] = resolution
    return day, values

class Command(BaseCommand):
    help = 'Importa observaciones H3; las revisiones requieren una nueva version explicita.'
    def add_arguments(self, parser):
        parser.add_argument('--file', required=True)
    def handle(self, *args, **options):
        path = Path(options['file'])
        try:
            payload = path.read_bytes()
            with path.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                missing = set(REQUIRED) - set(reader.fieldnames or [])
                if missing:
                    raise ValueError('Faltan columnas: ' + ', '.join(sorted(missing)))
                rows = list(reader)
            if not rows:
                raise ValueError('Archivo vacio')
            versions = {r['version_armonizacion'] for r in rows}
            if len(versions) != 1:
                raise ValueError('Importa una unica version por archivo')
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        run = DataImport.objects.create(source=path.name, checksum=hashlib.sha256(payload).hexdigest(), version=versions.pop())
        regions = runpy.run_path(str(settings.BASE_DIR.parent / 'src' / 'regiones.py'))['REGIONES']
        inserted = unchanged = 0
        seen = set()
        try:
            with transaction.atomic():
                for line, row in enumerate(rows, 2):
                    day, values = parse_row(row)
                    key = tuple(row[f] for f in ['region_id','fecha','modis_sobrevuelo','viirs_sobrevuelo','celda_h3'])
                    if key in seen:
                        raise ValueError('Observacion duplicada dentro del archivo')
                    seen.add(key)
                    bbox = regions.get(row['region_id'], {})
                    region, _ = Region.objects.get_or_create(id=row['region_id'], defaults=dict(name=row['region_nombre'], **{en: bbox.get(es) for en, es in [('west','oeste'),('south','sur'),('east','este'),('north','norte')]}))
                    pair, _ = OverpassPair.objects.get_or_create(region=region, date=day, modis_sobrevuelo=row['modis_sobrevuelo'], viirs_sobrevuelo=row['viirs_sobrevuelo'])
                    observation, created = H3Observation.objects.get_or_create(pair=pair, celda_h3=row['celda_h3'], version_armonizacion=run.version, defaults={**values, 'data_import':run})
                    if not created and any(getattr(observation, f) != v for f, v in values.items()):
                        raise ValueError('La misma version contiene cambios. Usa una nueva version_armonizacion para preservar el historico.')
                    inserted += int(created)
                    unchanged += int(not created)
                run.processed, run.inserted, run.unchanged, run.status = len(rows), inserted, unchanged, 'success'
                run.save()
        except Exception as exc:
            detail = str(exc) if isinstance(exc, (ValueError, KeyError)) else 'Error de base de datos; revisa la configuracion y las restricciones.'
            run.status, run.error = 'failed', f'Linea {line}: {detail}'
            run.save()
            raise CommandError(f'Linea {line}: {detail}. Importacion revertida.') from None
        self.stdout.write(self.style.SUCCESS(f'Procesados={len(rows)} insertados={inserted} sin_cambios={unchanged} version={run.version}'))
