import time
from datetime import date,timedelta
from django.core.management.base import BaseCommand,CommandError
from analysis.firms_harmonization import process_day,VERSION
from analysis.models import FIRMSHarmonizationJob

class Command(BaseCommand):
    help='Integra FIRMS mundial fuera de HTTP. Producto operativo distinto de Level 2.'
    def add_arguments(self,p):
        p.add_argument('--start');p.add_argument('--end');p.add_argument('--retrieve',action='store_true')
        p.add_argument('--watch',action='store_true');p.add_argument('--limit',type=int,default=3)
    def handle(self,*args,**o):
        if o['start']:
            try:
                first=date.fromisoformat(o['start']);last=date.fromisoformat(o['end'] or o['start'])
                if not 0<=(last-first).days<=30:raise ValueError
            except ValueError:raise CommandError('Selecciona 1–31 días ISO UTC')
            for i in range((last-first).days+1):
                day=first+timedelta(days=i)
                try:job=process_day(day,o['retrieve'])
                except Exception as exc:raise CommandError('No completado: '+type(exc).__name__) from None
                self.stdout.write(f'{day}: {job.status}; MODIS={job.modis_count}; VIIRS={job.viirs_count}; unificadas={job.records}; {job.metadata.get("counts")}')
            return
        if not o['watch']:raise CommandError('Usa --start YYYY-MM-DD o --watch')
        while True:
            for job in FIRMSHarmonizationJob.objects.filter(status__in=['PENDIENTE','PROCESANDO'],version=VERSION).order_by('date')[:max(1,min(o['limit'],3))]:
                try:
                    result=process_day(job.date,True);self.stdout.write(f'{result.date}: {result.status} {result.records}')
                except Exception as exc:self.stderr.write(type(exc).__name__)
            time.sleep(5)
