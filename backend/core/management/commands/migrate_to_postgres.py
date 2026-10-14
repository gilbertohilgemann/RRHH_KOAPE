from django.core.management.base import BaseCommand, CommandError

from core import db_migration


class Command(BaseCommand):
    help = (
        "Migra la base de datos actual (SQLite u otra) a PostgreSQL: crea la base "
        "y el usuario si hace falta, arma toda la estructura de tablas (migraciones) "
        "y copia los datos existentes."
    )

    def add_arguments(self, parser):
        parser.add_argument('--host', default='localhost', help='Host de PostgreSQL (por defecto: localhost)')
        parser.add_argument('--port', default='5432', help='Puerto de PostgreSQL (por defecto: 5432)')
        parser.add_argument('--dbname', required=True, help='Nombre de la base de datos destino')
        parser.add_argument('--user', required=True, help='Usuario de la app para conectarse a la base destino')
        parser.add_argument('--password', required=True, help='Contraseña de ese usuario')
        parser.add_argument(
            '--admin-user', default=None,
            help='Usuario administrador de Postgres (ej: postgres). Si se indica junto con '
                 '--admin-password, el comando crea la base y el usuario si todavía no existen.'
        )
        parser.add_argument('--admin-password', default=None, help='Contraseña del usuario administrador')
        parser.add_argument(
            '--skip-data', action='store_true',
            help='Solo crear la base y la estructura de tablas, sin copiar los datos existentes.'
        )

    def handle(self, *args, **options):
        host = options['host']
        port = options['port']
        dbname = options['dbname']
        user = options['user']
        password = options['password']

        def log(msg):
            self.stdout.write(msg)

        if options['admin_user'] and options['admin_password']:
            try:
                db_migration.ensure_postgres_database_and_user(
                    host, port, dbname, user, password,
                    options['admin_user'], options['admin_password'], log,
                )
            except Exception as e:
                raise CommandError(f'No se pudo crear la base/usuario: {e}')
        else:
            self.stdout.write('Sin credenciales de administrador: asumo que la base y el usuario ya existen.')

        db_migration.register_postgres_connection('postgres_target', host, port, dbname, user, password)

        self.stdout.write('Probando la conexión a la base destino...')
        try:
            db_migration.test_connection('postgres_target')
        except Exception as e:
            raise CommandError(f'No se pudo conectar a la base destino: {e}')
        self.stdout.write(self.style.SUCCESS('Conexión OK.'))

        db_migration.build_schema('postgres_target', log)
        self.stdout.write(self.style.SUCCESS('Estructura de tablas creada.'))

        if not options['skip_data']:
            db_migration.copy_data('default', 'postgres_target', log)
            db_migration.reset_sequences('postgres_target', log)
            diferencias = db_migration.verify_copy('default', 'postgres_target', log)
            if diferencias:
                for d in diferencias:
                    self.stderr.write(f'  · {d}')
                raise CommandError('La copia no coincide con el origen: no cambies la configuración (seguí con la base actual).')
            self.stdout.write(self.style.SUCCESS('Datos migrados y verificados correctamente.'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('¡Listo! Para que el sistema use esta base de datos, poné esto en backend/.env:'))
        self.stdout.write('')
        self.stdout.write('DB_ENGINE=postgres')
        self.stdout.write(f'DB_NAME={dbname}')
        self.stdout.write(f'DB_USER={user}')
        self.stdout.write(f'DB_PASSWORD={password}')
        self.stdout.write(f'DB_HOST={host}')
        self.stdout.write(f'DB_PORT={port}')
        self.stdout.write('')
        self.stdout.write('Y reiniciá el servidor (start.sh restart / start.bat restart).')
        self.stdout.write('Para volver a SQLite en cualquier momento, poné DB_ENGINE=sqlite (o borrá esa línea).')
