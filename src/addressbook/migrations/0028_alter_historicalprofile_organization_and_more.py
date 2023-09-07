# Generated by Django 4.1.10 on 2023-09-05 12:04

import addressbook.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('facility', '0019_alter_legalentity_rcs_and_more'),
        ('addressbook', '0027_rename_org_historicalprofile_organization_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='historicalprofile',
            name='organization',
            field=models.ForeignKey(blank=True, db_constraint=False, default=addressbook.models.get_default_organization, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='facility.organization'),
        ),
        migrations.AlterField(
            model_name='profile',
            name='organization',
            field=models.ForeignKey(default=addressbook.models.get_default_organization, on_delete=django.db.models.deletion.PROTECT, related_name='profiles', to='facility.organization'),
        ),
    ]
