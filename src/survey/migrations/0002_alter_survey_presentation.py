# Generated by Django 4.2.13 on 2024-06-10 14:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('survey', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='survey',
            name='presentation',
            field=models.TextField(blank=True),
        ),
    ]
