# Generated by Django 4.1.10 on 2023-09-05 11:27

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('facility', '0019_alter_legalentity_rcs_and_more'),
        ('addressbook', '0023_alter_contact_groups'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalprofile',
            name='org',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='facility.organization'),
        ),
        migrations.AddField(
            model_name='profile',
            name='org',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='profiles', to='facility.organization'),
        ),
    ]
