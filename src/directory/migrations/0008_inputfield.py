# Generated by Django 4.2.10 on 2024-02-23 02:22

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0007_directory_postal_codes'),
    ]

    operations = [
        migrations.CreateModel(
            name='InputField',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('geocoder', models.BooleanField(default=True)),
                ('situation', models.BooleanField(default=True)),
                ('commune', models.BooleanField(default=True)),
                ('category', models.BooleanField(default=True)),
                ('facility', models.BooleanField(default=True)),
                ('search', models.BooleanField(default=True)),
                ('directory', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='directory.directory')),
            ],
        ),
    ]
