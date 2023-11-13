from django.utils.text import slugify

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from facility.models import Organization
from directory.models import Effector, EffectorType, Commune
from django.db import DatabaseError, IntegrityError

import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Create slugs for Commune, EffectorType and Effector'

    def add_arguments(self, parser):
        parser.add_argument('language', type=str)        

    def handle(self, *args, **options):
        language: str = options['language']
        for model in [Commune, Effector, EffectorType]:
            for o in model.nodes.all():
                name=getattr(o, f'name_{language}')
                slug=slugify(name)
                setattr(o, f'slug_{language}', slug)
                o.save()
                slug=getattr(o, f'slug_{language}')
                self.stdout.write(
                    self.style.WARNING(
                        f'name: {name}\n'
                        f'slug:{slug}\n'
                    )
                )