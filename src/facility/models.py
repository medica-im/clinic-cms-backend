from datetime import timedelta
from django.db import models
from django.contrib.sites.models import Site
from workforce.models import NodeSet
import logging
from django.conf import settings
#import reversion
from django.core.exceptions import ValidationError

from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class OrganizationManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class Organization(models.Model):
    name = models.CharField(
        max_length=255,
        unique=True
    )
    company_name = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )
    formatted_name = models.CharField(
        max_length=255,
        blank=True,
    )
    formatted_name_definite_article = models.CharField(
        max_length=255,
        blank=True,
    )
    website_title = models.CharField(
        max_length=255,
        blank=True,
    )
    website_description = models.TextField(
        blank=True,
    )
    active = models.BooleanField(default=False)
    contact = models.OneToOneField(
        'addressbook.Contact',
        on_delete=models.CASCADE,
        related_name='organisation',
        null=True,
        blank=True,
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    site = models.OneToOneField(
        Site,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="organization",
    )
    google_site_verification = models.CharField(
        max_length=255,
        blank=True,
        help_text="Google site verification meta tag",
    )
    language = models.CharField(
        max_length=3,
        blank=True,
        help_text="ISO language code",
    )
    category = models.ForeignKey(
        'facility.Category',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="organization",
    )
    node = models.ForeignKey(
        "workforce.NetworkNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    registration = models.BooleanField(default=False)
    city= models.ForeignKey(
        "nlp.City",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    objects = OrganizationManager()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Organizations"


    def natural_key(self):
        return (self.name,)


class CategoryManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class Category(models.Model):
    name = models.CharField(
        max_length=255,
        unique=True
    )
    formatted_name = models.CharField(
        max_length=255,
        unique=True
    )
    definition = models.TextField()

    slug = models.SlugField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
    )

    objects = CategoryManager()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"

    def natural_key(self):
        return (self.name,)


class FacilityManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)
 
    
class Facility(models.Model):
    name = models.CharField(
        max_length=255,
        unique=True
    )
    active = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    contact = models.OneToOneField(
        'addressbook.Contact',
        on_delete=models.CASCADE,
        related_name='facility',
        null=True,
        blank=True,
    )
    node = models.ForeignKey(
        "workforce.NetworkNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    organization = models.ForeignKey(
        'facility.Organization',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="facility",
    )

    objects = FacilityManager()

    def occupation_set(self):
        occupations: set = set() 
        edges = self.networkedge_set.all()
        try:
            occupation_nodeset = NodeSet.objects.get(name="occupation")
        except NodeSet.DoesNotExist as e:
            logger.error(f"{e}: you must create an occupation NodeSet")
            return
        for edge in edges:
            parent = edge.parent
            if parent.node_set==occupation_nodeset:
                occupations.add(parent)
            else:
                for node in parent.ancestors():
                    if node.node_set==occupation_nodeset:
                        occupations.add(node)
        logger.debug(f"Facility {self.name} occupation set: {occupations}")
        return occupations

    def __str__(self):
        return self.name


    class Meta:
        verbose_name_plural = "Facilities"


    def natural_key(self):
        return (self.name,)


class LegalEntity(models.Model):
    class Type(models.TextChoices):
        SISA = "SISA", "société interprofessionnelle de soins ambulatoires"
        ASSO = "ASSO", "association loi 1901"

    type = models.CharField(
        max_length=4,
        choices=Type.choices,
        default=Type.SISA,
    )
    name = models.CharField(
        max_length=255,
        unique=True
    )
    RNA = models.CharField(
        max_length=10,
        unique=True,
        null=True,
        blank=True,
    )
    SIREN = models.CharField(
        max_length=9,
        unique=True
    )
    SIRET = models.CharField(
        max_length=14,
        unique=True
    )
    RCS = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )
    SHARE_CAPITAL = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    VAT = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text="VAT identification number"
    )
    organization = models.OneToOneField(
        'facility.Organization',
        on_delete=models.CASCADE,
        related_name='legal_entity',
    )

    class Meta:
        verbose_name_plural = "Legal entities"