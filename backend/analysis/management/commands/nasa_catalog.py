import json
from django.core.management.base import BaseCommand, CommandError
from analysis.nasa import CMRClient, NASAError

class Command(BaseCommand):
    help='Consulta colecciones oficiales CMR sin descargar productos ni alterar V1.'
    def add_arguments(self,parser):
        parser.add_argument('--product',required=True,choices=['MYD14','MYD03','VNP14IMG','VNP03IMG'])
    def handle(self,*args,**options):
        try:
            for item in CMRClient().collections(options['product']):
                self.stdout.write(json.dumps({key:item.get(key) for key in ['id','short_name','version_id','dataset_id','time_start','time_end']},ensure_ascii=True))
        except NASAError as exc: raise CommandError(str(exc)) from None
