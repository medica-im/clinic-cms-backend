# Generated by Django 4.1.10 on 2023-09-05 12:17

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('facility', '0019_alter_legalentity_rcs_and_more'),
        ('addressbook', '0028_alter_historicalprofile_organization_and_more'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='profile',
            unique_together={('contact', 'organization')},
        ),
    ]
