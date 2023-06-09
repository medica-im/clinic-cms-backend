# Generated by Django 4.1.8 on 2023-04-13 14:56

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('workforce', '0021_alter_networknode_slug'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='networknode',
            name='slug',
        ),
        migrations.CreateModel(
            name='WorkforceSlug',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=255, unique=True)),
                ('slug_en', models.SlugField(max_length=255, null=True, unique=True)),
                ('slug_fr', models.SlugField(max_length=255, null=True, unique=True)),
                ('node', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='slug', to='workforce.networknode')),
            ],
        ),
    ]
