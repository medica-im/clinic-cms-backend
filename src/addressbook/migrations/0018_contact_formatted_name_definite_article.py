# Generated by Django 4.1.1 on 2022-09-26 20:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('addressbook', '0017_socialnetwork_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='formatted_name_definite_article',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
