# Generated by Django 4.1.10 on 2023-07-26 11:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('addressbook', '0023_alter_contact_groups'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='neomodel_uid',
            field=models.UUIDField(blank=True, null=True),
        ),
    ]