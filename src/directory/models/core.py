from django.db import models
from django.contrib.sites.models import Site
from django.conf import settings
from the_big_username_blacklist import validate
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

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
        return "Slug %s %s %s" % (self.id, self.slug, self.site.domain)

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
        return "RejectSlug %s %s" % (self.id, self.slug)


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
        return f"Asset {self.id} {self.neomodel_uid}"