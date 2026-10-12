from django.core.management.base import BaseCommand

from parking import services
from parking.models import Admin, Entrance, Level


class Command(BaseCommand):
    help = 'First-time setup: starter layout (3 entrances x 3 levels x 50 slots) and the first admin. Safe to run twice.'

    def handle(self, *args, **options):
        if not Entrance.objects.exists() and not Level.objects.exists():
            total = services.build_layout(['South', 'East', 'North'], 3, 50)
            self.stdout.write(f'Created starter layout with {total} slots (editable from Slot Management).')
        if not Admin.objects.exists():
            Admin.objects.create_user('ADM001', 'Main Admin', 'admin123', is_staff=True, is_superuser=True)
            self.stdout.write('Created admin ADM001 / admin123 (change it under Admin Accounts).')
