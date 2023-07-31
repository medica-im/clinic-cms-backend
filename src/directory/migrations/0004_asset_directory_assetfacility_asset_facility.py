# Generated by Django 4.1.10 on 2023-07-19 13:39

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('facility', '0019_alter_legalentity_rcs_and_more'),
        ('directory', '0003_slug_unique_directory_slug_per_site_per_user'),
    ]

    operations = [
        migrations.CreateModel(
            name='Asset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('neomodel_uid', models.UUIDField(blank=True, null=True)),
                ('name', models.CharField(max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='Directory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('display_name', models.CharField(max_length=255, unique=True)),
                ('presentation', models.TextField()),
                ('slug', models.SlugField(blank=True, max_length=255, null=True, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='AssetFacility',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='directory.asset')),
                ('directory', models.ManyToManyField(blank=True, to='directory.directory')),
                ('facility', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='facility.facility')),
            ],
            options={
                'db_table': 'asset_facility',
                'managed': True,
                'unique_together': {('asset', 'facility')},
            },
        ),
        migrations.AddField(
            model_name='asset',
            name='facility',
            field=models.ManyToManyField(through='directory.AssetFacility', to='facility.facility'),
        ),
    ]
