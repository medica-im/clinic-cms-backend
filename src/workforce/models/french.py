from django.db import models
from django_postgresql_dag.models import node_factory, edge_factory
from django.utils.translation import gettext_lazy as _
from accounts.models import GrammaticalGender
from django.core.exceptions import ValidationError
from django.db.models import UniqueConstraint
from workforce.models import NodeSet
from workforce.models.limit_choices import limit_to_occupations, limit_to_users

import logging

logger = logging.getLogger(__name__)

def validate_isdigit(value):
    if not value.isdigit():
        raise ValidationError(
            _('%(value)s is not a number'),
            params={'value': value},
        )

def validate_rpps_length(value):
    if (len(value) < 10) or (len(value) > 11):
        raise ValidationError(
            '%(rpps)s must be 10 or 11 digits',
            params={'rpps': value},
        )


class RPPS(models.Model):
    node = models.OneToOneField(
        "workforce.NetworkNode",
        on_delete=models.CASCADE,
        related_name="rpps",
        null=True,
        blank=True,
    )
    effector_uid = models.UUIDField(
        null=True,
        blank=True,
        help_text=(
            "uid of neo4j Effector node"
        )
    )
    identifier = models.CharField(
        verbose_name=_("RPPS number"),
        max_length=11,  
        validators=[validate_isdigit, validate_rpps_length],
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.identifier


    class Meta:
        models.UniqueConstraint(
            fields=['identifier'],
            name='unique_rpps_identifier'
        )

def validate_adeli_length(value):
    if (len(value) != 9):
        raise ValidationError(
            '%(adeli)s must be 9 digits',
            params={'adeli': value},
        )

class ADELI(models.Model):
    node = models.OneToOneField(
        "workforce.NetworkNode",
        on_delete=models.CASCADE,
        related_name="adeli",
        null=True,
        blank=True,
    )
    effector_uid = models.UUIDField(
        null=True,
        blank=True,
        help_text=(
            "uid of neo4j Effector node"
        )
    )
    identifier = models.CharField(
        verbose_name=_("ADELI number"),
        max_length=9,
        validators=[validate_isdigit, validate_adeli_length],
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.identifier


    class Meta:
        models.UniqueConstraint(
            fields=['identifier'],
            name='unique_adeli_identifier'
        )


class CarteVitale(models.Model):
    node = models.ForeignKey(
        "workforce.NetworkNode",
        on_delete=models.CASCADE,
        related_name="carte_vitale",
        null=True,
        blank=True,
    )
    effector_facility_uid = models.UUIDField(
        null=True,
        blank=True,
        help_text=(
            "uid of neo4j LOCATION relationship between Effector and Facility"
        )
    )
    organization = models.ForeignKey(
        "facility.Organization",
        models.DO_NOTHING,
    )
    is_accepted = models.BooleanField(
        verbose_name=_("Is Carte Vitale accepted?"),
        null=True,
    )

    def __str__(self):
        return f'{self.is_accepted} {self.organization}'


class ConventionManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class Convention(models.Model):
    objects = ConventionManager()

    name = models.CharField(
        max_length=255,  
        null=True,
        blank=True,
    )
    label = models.CharField(
        max_length=255,  
        null=True,
        blank=True,
    )
    definition = models.TextField(
        null=True,
        blank=True,
    )
    profession = models.ManyToManyField(
        "workforce.NetworkNode",
        limit_choices_to = limit_to_occupations,
    )

    def __str__(self):
        return f'{self.name}'

    def natural_key(self):
        return (self.name,)

    natural_key.dependencies = ['workforce.NetworkNode']


    class Meta:
        constraints = [
            UniqueConstraint(
                name='unique_name',
                fields=['name'],
            )
        ]


class Conventionnement(models.Model):
    convention = models.ForeignKey(
        "workforce.Convention",
        on_delete=models.PROTECT,
    )
    node = models.ForeignKey(
        "workforce.NetworkNode",
        on_delete=models.CASCADE,
        limit_choices_to = limit_to_users,
        null=True,
        blank=True,
    )
    effector_facility_uid = models.UUIDField(
        null=True,
        blank=True,
        help_text=(
            "uid of neo4j LOCATION relationship between Effector and Facility"
        )
    )
    organization = models.ForeignKey(
        "facility.Organization",
        models.PROTECT,
    )

    def __str__(self):
        return f'{self.node} {self.convention} {self.organization}'

    class Meta:
        constraints = [
            UniqueConstraint(
                name='unique_node_organization',
                fields=['node', 'organization'],
            )
        ]