# Generated by Django 4.1.10 on 2023-09-05 11:40

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('addressbook', '0026_remove_profile_organization'),
    ]

    operations = [
        migrations.RenameField(
            model_name='historicalprofile',
            old_name='org',
            new_name='organization',
        ),
        migrations.RenameField(
            model_name='profile',
            old_name='org',
            new_name='organization',
        ),
    ]
