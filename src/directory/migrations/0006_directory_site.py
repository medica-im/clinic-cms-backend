# Generated by Django 4.1.10 on 2023-07-30 10:36

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sites', '0002_alter_domain_unique'),
        ('directory', '0005_alter_directory_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='directory',
            name='site',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='directory', to='sites.site'),
        ),
    ]
