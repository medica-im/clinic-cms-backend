from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from accounts.models import User
from workforce.models import NetworkNode, NodeSet
from facility.models import Organization, Facility
from django.db import DatabaseError, IntegrityError
from django.contrib.sites.models import Site
from directory.models import Slug
from addressbook.models import Contact
from accounts.models import GrammaticalGender
from access.models import Role

import logging

logger = logging.getLogger(__name__)

def validateEmail( email ):
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    try:
        validate_email( email )
        return True
    except ValidationError:
        return False
    
def list_sites():
    return [site.name for site in Site.objects.all()]


class Command(BaseCommand):
    help = 'Create a passwordless account using email'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str)
        parser.add_argument(
            '--site',
            type=str,
            choices=list_sites(),
            help=f"site name among {list_sites()}"
            )
        parser.add_argument('--effector', type=str, help="Effector node UID")
        parser.add_argument('--formatted_name', type=str)
        parser.add_argument(
            '--role',
            type=str,
            choices=['superuser', 'administrator', 'staff', 'registered', 'anonymous'],
            help=(
            "minimal access role allowed ('superuser', 'administrator',"
            "'staff', 'registered', 'anonymous')"
            )
        )

    def handle(self, *args, **options):
        email: str = options['email']
        if not email:
            raise CommandError('You must provide an email.')
            return
        if not validateEmail(email):
            raise CommandError('Email "%s" is not valid' % email)
        try:
            user, created = User.objects.get_or_create(
                email=email
            )
            user.save()
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        'Passwordless Django user %s successfully created' % user
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        'Passwordless Django user %s already exists' % user
                    )
                )
        except Exception as e:
            raise CommandError('User creation failed. %s' % e)

        # create Slug
        site=options['site']
        if site:
            try:
                site = Site.objects.get(name=options['site'])
            except Site.DoesNotExist as e:
                raise CommandError(
                    f'Site with domain {site} does not exist.'
                )
            user.site=site

        # create Contact
        formatted_name = options['formatted_name']
        effector = options['effector']
        if formatted_name:
            person_type=Contact.PersonType.NATURAL
            try:
                Contact.objects.get_or_create(
                    person_type=person_type,
                    user=user,
                    formatted_name=formatted_name,
                    neomodel_uid=effector
                )
            except Exception as e:
                raise CommandError(
                    f'Error during creation of Contact object: $s' % e
                )
        user.effector=effector
        user.full_name=formatted_name
        role_name=options["role"]
        if role_name:
            try:
                role = Role.objects.get(name=role_name)
                user.role=role
            except Role.DoesNotExist:
                raise CommandError(f'Role {role_name} does not exist.')
        user.save()
        self.stdout.write(
            self.style.SUCCESS(
                f'{user} successfully created!'
            )
        )