from django.db import models
import time
from django.contrib.sites.models import Site
from django.contrib.sites.requests import RequestSite
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from the_big_username_blacklist import validate
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from accounts.models import GrammaticalGender
from facility.models import Organization
from directory.models.api import Timestamp, Endpoint
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
from access.models import Role
import logging

logger=logging.getLogger(__name__)

def sync_set_timestamp(endpoint_name: str, site):
    # timestamp unit: millisecond
    timestamp = int(time.time_ns()/1000000)
    try:
        endpoint=Endpoint.objects.get(name=endpoint_name)
    except Endpoint.DoesNotExist as e:
        logger.error(e)
        return
    ts, _ = Timestamp.objects.get_or_create(endpoint=endpoint,site=site)
    ts.timestamp=timestamp
    ts.save()

def sync_clear_all_cache():
    endpoints = set()
    for ts in Timestamp.objects.all():
        endpoints.add(ts.endpoint.name)
    for endpoint in endpoints:
        sync_clear_cache(endpoint)

def sync_clear_cache(endpoint: str, key: str|None=None, site=None):
    sites: list[Site|RequestSite] = []
    if site:
        sites.append(site)
    else:
        for org in Organization.objects.select_related('site').filter(active=True).exclude(site__isnull=True).all():
            site = org.site
            if site:
                sites.append(site)
    if not sites:
        return
    for site in sites:
        cache_keys = [key or f"{endpoint}:{site.domain}"]
        for r in Role.objects.all():
            cache_keys.append(f"{endpoint}:{site.domain}:{r.name}")
        logger.debug(f"{cache_keys}")
        for cache_key in cache_keys:
            logger.debug(f"Processing {cache_key} ...")
            deleted = cache.delete(cache_key)
            if (deleted):
                logger.warning(f"\n*** cache {cache_key} {deleted=} ***\n")
        sync_set_timestamp(endpoint, site)

def validate_slug(value):
    if not validate(value):
        raise ValidationError(
            _('%(value)s is not allowed'),
            params={'value': value},
        )


class Slug(models.Model):
    slug = models.SlugField(
        db_index=True,
        validators=[validate_slug]    
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return "Slug %s %s %s" % (self.pk, self.slug, self.site.domain)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['slug', 'site'],
                name='unique_directory_slug_per_site'
            ),
            models.UniqueConstraint(
                fields=['slug', 'site', 'user'],
                name='unique_directory_slug_per_site_per_user'
            )
        ]


class RejectSlug(models.Model):
    """ slugs that must not be allowed
    In addition to the_big_username_blacklist, we must reject these slugs
    which are used for routes in the SvelteKit frontend
    """
    slug = models.SlugField(
        db_index=True,
        unique=True,    
    )

    def __str__(self):
        return "RejectSlug %s %s" % (self.pk, self.slug)


class Directory(models.Model):
    """A directory grouping assets."""
    
    name = models.CharField(
        max_length=255,
        unique=True
    )
    display_name = models.CharField(
        max_length=255,
        unique=True
    )
    presentation = models.TextField()
    slug = models.SlugField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
    )
    site = models.OneToOneField(
        Site,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="directory",
    )
    postal_codes = ArrayField(
        models.CharField(
            max_length=5
        ),
        blank=True,
        null=True,
        help_text=(
            "limit address search results to postal codes starting with these "
            "strings")
    )

    def __str__(self):
        return f"Directory {self.name}"

    class Meta:
        verbose_name_plural = "Directories"


class AssetFacility(models.Model):
    asset = models.ForeignKey(
        "directory.Asset",
        on_delete=models.CASCADE,
    )
    facility = models.ForeignKey(
        "facility.Facility",
        on_delete=models.CASCADE,
    )
    directory = models.ManyToManyField(
        "directory.Directory",
        blank=True,
    )

    class Meta:
        managed = True
        db_table = 'asset_facility'
        unique_together = (('asset', 'facility'),)


class Asset(models.Model):
    """An Asset can link an account, an addressbook contact (through a Facility)
    and a node in the neo4j graph (EffectorType, MESH or other categories of entities)."""

    facility = models.ManyToManyField(
        "facility.Facility",
        through = "directory.AssetFacility"  
    )
    neomodel_uid = models.UUIDField(
        null=True,
        blank=True,
    )
    name = models.CharField(
        max_length=255,
    )

    def __str__(self):
        return f"Asset {self.pk} {self.neomodel_uid}"


class InputField(models.Model):
    directory = models.OneToOneField(
        "directory.Directory",
        on_delete=models.CASCADE,
    )
    category = models.BooleanField(null=True)
    commune = models.BooleanField(null=True)
    department = models.BooleanField(null=True)
    facility = models.BooleanField(null=True)
    geocoder = models.BooleanField(null=True)
    organization = models.BooleanField(null=True)
    search = models.BooleanField(null=True)
    situation = models.BooleanField(null=True)
    tag = models.BooleanField(null=True)

    def __str__(self):
        return (
            f"InputField {self.directory.name} {self.geocoder=} "
            f"{self.situation=} {self.commune=} {self.category=} "
            f"{self.facility} {self.search=}"
        )


class Setting(models.Model):
    ALPHABETICAL = "AB"
    INVERSE_FREQUENCY = "IF"
    SORT_CATEGORY_CHOICES = [
        (ALPHABETICAL, "alphabetical"),
        (INVERSE_FREQUENCY, "inverse_frequency"),
    ]
    directory = models.OneToOneField(
        "directory.Directory",
        on_delete=models.CASCADE,
    )
    sort_category = models.CharField(
        max_length=2,
        choices=SORT_CATEGORY_CHOICES,
        default=ALPHABETICAL,
    )
    def __str__(self):
        return (
            f'Setting {self.get_sort_category_display()}'
        )


class Label(models.Model):

    class GrammaticalNumber(models.TextChoices):
        SINGULAR = 'S', _('Singular')
        PLURAL = 'P', _('Plural')

    class Languages(models.TextChoices):
        ENGLISH = 'en', _('English')
        FRENCH = 'fr', _('French')

    label = models.CharField(max_length=255)
    uid = models.UUIDField(
        help_text="uid of neo4j EffectorType node"
    )
    gender = models.ManyToManyField(
        'accounts.GrammaticalGender',
        related_name='labels',
    )
    grammatical_number = models.CharField(
        max_length=1,
        choices=GrammaticalNumber.choices,
        blank=True,
    )
    language = models.CharField(
        max_length=2,
        choices=Languages.choices,
        default=Languages.ENGLISH,
    )

    def __str__(self):
        return self.label

    def natural_key(self):
        return (self.label, self.language)
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        sync_clear_cache("v1:effector_type_labels", key="v1:effector_type_labels:fr")

    class Meta:
        models.UniqueConstraint(
            "label",
            "uid",
            "gender",
            "grammatical_number",
            "language",
            name="unique_label_uid_gender_grammatical_number_language"
        )

    @staticmethod
    def get_label(uid: str, gender_code: str, number: str, language: str) -> str|None:
        try:
            gender = GrammaticalGender.objects.get(code=gender_code)
        except GrammaticalGender.DoesNotExist:
            return
        try:
            label = Label.objects.get(
                uid=uid,
                gender=gender,
                grammatical_number=number,
                language=language
            )
            return label.label
        except Label.DoesNotExist as e:
            logger.debug(f'{e} for {uid=}, {gender=}, {number=}, {language=}')
            return

    @staticmethod
    async def async_get_label(uid: str, gender_code: str, number: str, language: str) -> str|None:
        try:
            gender = await GrammaticalGender.objects.aget(code=gender_code)
        except GrammaticalGender.DoesNotExist:
            return
        try:
            label = await Label.objects.aget(
                uid=uid,
                gender=gender,
                grammatical_number=number,
                language=language
            )
            return label.label
        except Label.DoesNotExist as e:
            logger.debug(f'{e} for {uid=}, {gender=}, {number=}, {language=}')
            return