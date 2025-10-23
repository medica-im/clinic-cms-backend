from django.db import models
from django.contrib.sites.models import Site
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from the_big_username_blacklist import validate
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from accounts.models import GrammaticalGender
import logging

logger=logging.getLogger(__name__)

class Endpoint(models.Model):
    name = models.CharField(
        max_length=255,
        unique=True
    )

    def __str__(self):
        return "Endpoint %s %s" % (self.pk, self.name)


class TTL(models.Model):
    endpoint = models.ForeignKey(
        Endpoint,
        on_delete=models.CASCADE,
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
    )
    ttl = models.PositiveIntegerField(default=60)

    def __str__(self):
        return "TTL %s %s %s %s seconds" % (self.pk, self.site.domain, self.endpoint, self.ttl)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['endpoint', 'site'],
                name='unique_endpoint_ttl_per_site'
            )
        ]
