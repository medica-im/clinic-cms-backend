# Generated by Django 4.1.5 on 2023-01-10 02:54

from django.db import migrations
import wagtail.blocks
import wagtail.fields
import wagtail.images.blocks


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0004_alter_timeline_content'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='timeline',
            name='custom_title',
        ),
        migrations.AlterField(
            model_name='timeline',
            name='content',
            field=wagtail.fields.StreamField([('cards', wagtail.blocks.StructBlock([('title', wagtail.blocks.CharBlock(help_text='Add your title', required=True)), ('cards', wagtail.blocks.ListBlock(wagtail.blocks.StructBlock([('image', wagtail.images.blocks.ImageChooserBlock(required=True)), ('title', wagtail.blocks.CharBlock(max_length=40, required=True)), ('start_date', wagtail.blocks.DateBlock(help_text='Start date: required', required=True)), ('start_time', wagtail.blocks.TimeBlock(help_text='Start time: optional', required=False)), ('end_date', wagtail.blocks.DateBlock(help_text='End date: optional', required=False)), ('end_time', wagtail.blocks.TimeBlock(help_text='End time: optional', required=False)), ('text', wagtail.blocks.TextBlock(max_length=200, required=True)), ('more_text', wagtail.blocks.TextBlock(required=False)), ('button_page', wagtail.blocks.PageChooserBlock(required=False)), ('button_url', wagtail.blocks.URLBlock(help_text='If the button page above is selected, that will be used first.', required=False))])))]))], blank=True, null=True, use_json_field=True),
        ),
    ]
