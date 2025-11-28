import logging
from django.core.management.base import BaseCommand, CommandError
from directory.models.core import sync_clear_all_cache

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clear all API caches'

    def warn(self, message):
        self.stdout.write(
            self.style.WARNING(message)
        )

    def handle(self, *args, **options):
        sync_clear_all_cache()