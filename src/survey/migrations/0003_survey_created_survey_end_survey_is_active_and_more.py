# Generated by Django 4.2.13 on 2024-06-10 16:33

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('survey', '0002_alter_survey_presentation'),
    ]

    operations = [
        migrations.AddField(
            model_name='survey',
            name='created',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='survey',
            name='end',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='survey',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='survey',
            name='start',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]