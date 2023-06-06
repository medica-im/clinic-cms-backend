# Generated by Django 4.0.4 on 2022-04-27 21:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facility', '0003_facility_node'),
        ('workforce', '0003_alter_networknode_name'),
    ]

    operations = [
        #migrations.AddField(
        #    model_name='networkedge',
        #    name='facilities',
        #    field=models.ManyToManyField(related_name='workforce_edges', to='facility.facility'),
        #),
        migrations.CreateModel(
            name='WorkforceNetworkedgeFacilities',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('facility', models.ForeignKey(on_delete=models.deletion.DO_NOTHING, to='facility.facility')),
                ('networkedge', models.ForeignKey(on_delete=models.deletion.DO_NOTHING, to='workforce.networkedge')),

            ],
            options={
                'db_table': 'workforce_networkedge_facilities',
                'managed': True,
            },
        ),
        migrations.AddField(
            model_name='networkedge',
            name='facilities',
            field=models.ManyToManyField(through='workforce.WorkforceNetworkedgeFacilities', to='facility.facility'),
        ),
        migrations.AlterUniqueTogether(
            name='workforcenetworkedgefacilities',
            unique_together={('networkedge', 'facility')},
        ),
    ]
