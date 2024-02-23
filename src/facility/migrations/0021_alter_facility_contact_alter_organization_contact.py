# Generated by Django 4.2.10 on 2024-02-23 02:22

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('addressbook', '0032_alter_phonenumber_options'),
        ('facility', '0020_organization_neomodel_uid'),
    ]

    operations = [
        migrations.AlterField(
            model_name='facility',
            name='contact',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='facility', to='addressbook.contact'),
        ),
        migrations.AlterField(
            model_name='organization',
            name='contact',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='organisation', to='addressbook.contact'),
        ),
    ]
