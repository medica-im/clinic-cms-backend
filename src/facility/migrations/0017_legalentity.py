# Generated by Django 4.1.9 on 2023-06-13 15:38

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('facility', '0016_organization_website_description'),
    ]

    operations = [
        migrations.CreateModel(
            name='LegalEntity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('SISA', 'société interprofessionnelle de soins ambulatoires'), ('ASSO', 'association loi 1901')], default='SISA', max_length=4)),
                ('name', models.CharField(max_length=255, unique=True)),
                ('RNA', models.CharField(max_length=10, unique=True)),
                ('SIREN', models.CharField(max_length=9, unique=True)),
                ('SIRET', models.CharField(max_length=14, unique=True)),
                ('RCS', models.CharField(max_length=255, unique=True)),
                ('SHARE_CAPITAL', models.PositiveIntegerField()),
                ('VAT', models.CharField(help_text='VAT identification number', max_length=255, unique=True)),
                ('organization', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='legal_entity', to='facility.organization')),
            ],
        ),
    ]
