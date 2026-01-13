from django.core.management.base import BaseCommand, CommandError
from accounts.models import User
from workforce.models import NetworkNode, NodeSet
from django.db import DatabaseError, IntegrityError
from django.contrib.sites.models import Site
from directory.models import Slug
from addressbook.models import Contact
from accounts.models import GrammaticalGender, Role as AccountsRole
from access.models import Role as AccessRole

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
    
def validate_username(username):
    if len(username)>255:
        return False
    else:
        return True
    
def list_sites():
    return [site.name for site in Site.objects.all()]

def access_roles():
    return [role.name for role in AccessRole.objects.all()]

def list_genders():
    return [gg.code for gg in GrammaticalGender.objects.all()]


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
        parser.add_argument('--entry', type=str, help="Entry node UID")
        parser.add_argument('--full_name', type=str)
        parser.add_argument(
            '--role',
            type=str,
            choices=access_roles(),
            help=(
            f"access role ({access_roles()})"
            )
        )
        parser.add_argument(
            '--gender',
            type=str,
            choices=list_genders(),
            help=f"grammatical gender among {list_genders()}"
        )

    def handle(self, *args, **options):
        email: str = options['email']
        if not email:
            raise CommandError('You must provide an email.')
            return
        if not validateEmail(email):
            raise CommandError('Email "%s" is not valid' % email)
        site=options['site']
        if site and site not in list_sites():
            raise CommandError('site "%s" is not valid' % site)
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
        if site:
            try:
                site = Site.objects.get(name=options['site'])
            except Site.DoesNotExist as e:
                raise CommandError(
                    f'Site with domain {site} does not exist.'
                )
        entry = options['entry']
        if entry:
            user.effector=entry
        full_name = options['full_name']
        user.full_name=full_name
        gender = options['gender']
        if gender:
            try:
                gg=GrammaticalGender.objects.get(code=gender)
            except GrammaticalGender.DoesNotExist as e:
                raise CommandError(
                    f'GrammaticalGender with code {gender} does not exist.'
                )
        user.grammatical_gender=gg
        user.save()
        role_name=options["role"]
        if role_name:
            try:
                role = AccessRole.objects.get(name=role_name)
            except AccessRole.DoesNotExist:
                raise CommandError(f'Role {role_name} does not exist.')
        if role and site:
            try:
                role = AccountsRole(user=user,site=site,role=role)
            except DatabaseError as e:
                raise CommandError(f'Error during Accounts.Role creation: {e}')
        user.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f'{user} successfully created!\n'
                f'{[(role.name,role.site,) for role in user.roles.all()]}'
            )
        )