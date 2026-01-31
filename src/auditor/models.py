from django.db import models
from django.contrib.sites.models import Site

### Model for OIDC audit logging
class OIDC(models.Model):
    iss=models.URLField()
    aud=models.CharField(max_length=255)
    sub=models.CharField(max_length=255)
    iat=models.BigIntegerField()
    email=models.CharField(max_length=255)
    email_verified=models.BooleanField()
    name=models.CharField(max_length=255)
    picture=models.URLField()
    given_name=models.CharField(max_length=255)
    family_name=models.CharField(max_length=255)
    locale=models.CharField(max_length=10)
    site=models.ForeignKey(Site, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.email} ({self.sub})"