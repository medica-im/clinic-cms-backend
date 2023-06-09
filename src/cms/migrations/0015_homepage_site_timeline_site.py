# Generated by Django 4.1.5 on 2023-01-14 01:58

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sites', '0002_alter_domain_unique'),
        ('cms', '0014_alter_timeline_content'),
    ]

    operations = [
        migrations.AddField(
            model_name='homepage',
            name='site',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='sites.site'),
        ),
        migrations.AddField(
            model_name='timeline',
            name='site',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='sites.site'),
        ),
    ]
