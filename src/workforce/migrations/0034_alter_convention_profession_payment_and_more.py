# Generated by Django 4.1.9 on 2023-05-08 20:06

from django.db import migrations, models
import django.db.models.deletion
import workforce.models.limit_choices


class Migration(migrations.Migration):

    dependencies = [
        ('facility', '0015_organization_company_name'),
        ('workforce', '0033_rename_payment_paymentmethod_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='convention',
            name='profession',
            field=models.ManyToManyField(limit_choices_to=workforce.models.limit_choices.limit_to_occupations, to='workforce.networknode'),
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('method', models.ManyToManyField(to='workforce.paymentmethod')),
                ('node', models.ForeignKey(limit_choices_to=workforce.models.limit_choices.limit_to_users, on_delete=django.db.models.deletion.CASCADE, to='workforce.networknode')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='facility.organization')),
            ],
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.UniqueConstraint(fields=('node', 'organization'), name='unique_payment_node_organization'),
        ),
    ]
