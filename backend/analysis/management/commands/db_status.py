from django.core.management.base import BaseCommand, CommandError
from django.db import connection, DatabaseError
class Command(BaseCommand):
    help = 'Comprueba PostgreSQL, tablas y disponibilidad opcional de PostGIS sin revelar credenciales.'
    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), version()")
                database, version = cursor.fetchone()
                cursor.execute("SELECT name, installed_version FROM pg_available_extensions WHERE name='postgis'")
                postgis = cursor.fetchone()
                self.stdout.write(f'PostgreSQL conectado: {database}; {version.split(",")[0]}')
                self.stdout.write(f'PostGIS disponible/instalado: {postgis}')
                self.stdout.write('Tablas analysis: ' + ', '.join(t for t in connection.introspection.table_names() if t.startswith('analysis_')))
        except DatabaseError:
            raise CommandError('No se pudo conectar a PostgreSQL. Revisa backend/.env y el servicio; no se utiliza SQLite.') from None
