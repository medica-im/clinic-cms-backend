from django.db import models
from django.contrib.sites.models import Site
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from survey.email import send_email_alert
import logging

logger=logging.getLogger(__name__)

User=get_user_model()

class Survey(models.Model):
    name = models.CharField(max_length=255)
    label = models.CharField(max_length=255, blank=True, default="")
    presentation = models.TextField(blank=True)
    moderators = models.ManyToManyField(User)
    is_active = models.BooleanField(default=True)
    start = models.DateTimeField(null=True, blank=True)
    end = models.DateTimeField(null=True, blank=True)
    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name="surveys",
    )
    created = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name


class Response(models.Model):
    
    class Moderation(models.TextChoices):
        UNMODERATED = "UN", _("Unmoderated")
        PUBLIC = "PU", _("Public")
        PRIVATE = "PR", _("Private")
        SPAM = "SP", _("Spam")

    moderation = models.CharField(
        max_length=2,
        choices=Moderation.choices,
        default=Moderation.UNMODERATED,
    )
    survey = models.ForeignKey(
        "Survey",
        on_delete=models.CASCADE,
    )
    created = models.DateTimeField(auto_now_add=True)
    content = models.TextField()
    
    def __str__(self):
        return f'{self.id} {self.survey} {self.content[:140]}'
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        ok = send_email_alert(self.survey, self)
        logger.debug(f'send_email_alert {ok=}')


    class Meta:
        ordering = ['created']
