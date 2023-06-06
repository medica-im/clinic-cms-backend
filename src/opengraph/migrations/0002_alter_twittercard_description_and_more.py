# Generated by Django 4.1.1 on 2022-10-21 03:07

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('opengraph', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='twittercard',
            name='description',
            field=models.TextField(max_length=200, validators=[django.core.validators.MaxLengthValidator(200, message='200 characters max!')]),
        ),
        migrations.AlterField(
            model_name='twittercard',
            name='image_alt',
            field=models.TextField(blank=True, max_length=420, validators=[django.core.validators.MaxLengthValidator(420, message='420 characters max!')]),
        ),
    ]
