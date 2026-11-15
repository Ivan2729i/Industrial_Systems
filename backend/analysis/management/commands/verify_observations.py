import csv
from collections import Counter
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from analysis.models import H3Observation
from analysis.management.commands.import_observations import parse_row

class Command(BaseCommand):
    help = 'Compara PostgreSQL con todas las columnas cientificas del CSV importado.'
    def add_arguments(self, parser): parser.add_argument('--file',required=True)
    def handle(self,*args,**options):
        with Path(options['file']).open(encoding='utf-8-sig',newline='') as stream: rows=list(csv.DictReader(stream))
        if not rows: raise CommandError('CSV vacio')
        versions={r['version_armonizacion'] for r in rows}
        stored={ (o.pair.region_id,o.pair.date.isoformat(),o.pair.modis_sobrevuelo,o.pair.viirs_sobrevuelo,o.celda_h3,o.version_armonizacion):o for o in H3Observation.objects.filter(version_armonizacion__in=versions).select_related('pair') }
        for line,row in enumerate(rows,2):
            key=tuple(row[f] for f in ['region_id','fecha','modis_sobrevuelo','viirs_sobrevuelo','celda_h3','version_armonizacion'])
            observation=stored.get(key)
            if observation is None: raise CommandError(f'Linea {line}: observacion ausente')
            _,values=parse_row(row)
            if any(getattr(observation,f)!=value for f,value in values.items()): raise CommandError(f'Linea {line}: valores diferentes')
        self.stdout.write(self.style.SUCCESS(f'{len(rows)} observaciones verificadas campo por campo en PostgreSQL.'))
        self.stdout.write(str(dict(Counter(row['region_id'] for row in rows))))
        for region in sorted({row['region_id'] for row in rows}):
            selected=[row for row in rows if row['region_id']==region]
            self.stdout.write(f'{region}: originales={dict(Counter(row["coincidencia_original"] for row in selected))}; QA={dict(Counter(row["coincidencia_qa"] for row in selected))}')
