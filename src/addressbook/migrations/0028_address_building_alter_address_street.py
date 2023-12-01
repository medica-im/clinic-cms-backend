# Generated by Django 4.1.10 on 2023-08-12 15:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('addressbook', '0027_alter_address_contact'),
    ]

    operations = [
        migrations.AddField(
            model_name='address',
            name='building',
            field=models.CharField(blank=True, help_text='Address line for building name', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='address',
            name='street',
            field=models.CharField(blank=True, help_text='Address line for street name and house number', max_length=255, null=True),
        ),
    ]