# Generated by Django 4.2.11 on 2024-03-15 12:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_user_effector'),
        ('workforce', '0043_adeli_effector_uid_cartevitale_effector_facility_uid_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='label',
            name='gender',
            field=models.ManyToManyField(related_name='workforcelabels', to='accounts.grammaticalgender'),
        ),
    ]