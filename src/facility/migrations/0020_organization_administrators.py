# Generated by Django 4.1.11 on 2023-09-12 22:39

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('facility', '0019_alter_legalentity_rcs_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='administrators',
            field=models.ManyToManyField(blank=True, to=settings.AUTH_USER_MODEL),
        ),
    ]
