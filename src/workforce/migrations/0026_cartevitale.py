# Generated by Django 4.1.9 on 2023-05-05 23:13

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('facility', '0015_organization_company_name'),
        ('workforce', '0025_alter_rpps_options_alter_rpps_node'),
    ]

    operations = [
        migrations.CreateModel(
            name='CarteVitale',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_accepted', models.BooleanField(null=True, verbose_name='Is Carte Vitale accepted?')),
                ('node', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='carte_vitale', to='workforce.networknode')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='facility.organization')),
            ],
        ),
    ]
