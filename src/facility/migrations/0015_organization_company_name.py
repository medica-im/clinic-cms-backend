# Generated by Django 4.1.8 on 2023-04-19 15:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facility', '0014_organization_city'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='company_name',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
    ]
