import logging
from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from directory.models.core import sync_clear_all_cache

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = (
        'Clear API caches. Targets: all (default), '
        'heatwave (both vigilance caches), '
        'vigilance_textes (text bulletins cache), '
        'vigilance_carte (carte vigilance cache)'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--target',
            choices=['all', 'heatwave', 'vigilance_textes', 'vigilance_carte'],
            default='all',
            help='Cache target to clear: all | heatwave | vigilance_textes | vigilance_carte',
        )

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def handle(self, *args, **options):
        target = options['target']
        if target == 'all':
            sync_clear_all_cache()
            cache.delete('vigilance_cdp_textes')
            cache.delete('vigilance_carte')
            self.stdout.write(self.style.SUCCESS('Cleared all caches'))
        elif target == 'heatwave':
            cache.delete('vigilance_cdp_textes')
            cache.delete('vigilance_carte')
            self.stdout.write(self.style.SUCCESS('Cleared heatwave caches'))
        elif target == 'vigilance_textes':
            cache.delete('vigilance_cdp_textes')
            self.stdout.write(self.style.SUCCESS('Cleared vigilance_textes cache'))
        elif target == 'vigilance_carte':
            cache.delete('vigilance_carte')
            self.stdout.write(self.style.SUCCESS('Cleared vigilance_carte cache'))