# Generated by Django 4.1.7 on 2023-04-13 13:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workforce', '0020_auto_20230413_1328'),
    ]

    operations = [
        migrations.AlterField(
            model_name='networknode',
            name='slug',
            field=models.SlugField(max_length=255, unique=True),
        ),
    ]
