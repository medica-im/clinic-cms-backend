# Generated by Django 4.1.5 on 2023-01-14 02:36

import django.core.validators
from django.db import migrations
import wagtail.blocks
import wagtail.fields
import wagtail.images.blocks


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0015_homepage_site_timeline_site'),
    ]

    operations = [
        migrations.AlterField(
            model_name='timeline',
            name='content',
            field=wagtail.fields.StreamField([('slide', wagtail.blocks.StructBlock([('title', wagtail.blocks.StructBlock([('text', wagtail.blocks.StructBlock([('headline', wagtail.blocks.RichTextBlock(required=False)), ('text', wagtail.blocks.RichTextBlock(required=False))])), ('media', wagtail.blocks.StructBlock([('image', wagtail.images.blocks.ImageChooserBlock(required=False)), ('url', wagtail.blocks.URLBlock(help_text='url, iframe or blockquote', required=False)), ('alt', wagtail.blocks.CharBlock(help_text='An alt tag for your image. If none is provided, the caption, if any, will be used.', max_length=255, required=False)), ('caption', wagtail.blocks.RichTextBlock(required=False)), ('credit', wagtail.blocks.RichTextBlock(required=False)), ('thumbnail', wagtail.blocks.URLBlock(help_text='A URL for an image to use in the timenav marker for this event. If omitted, Timeline will use an icon based on the type of media. Not relevant for title slides, because they do not have a marker.', required=False)), ('title', wagtail.blocks.CharBlock(help_text='A title for your image. If none is provided, the caption, if any, will be used. ', max_length=255, required=False)), ('link', wagtail.blocks.URLBlock(help_text='Optional URL to use as the href for wrapping the media with an <a> tag. ', required=False)), ('link_target', wagtail.blocks.ChoiceBlock(choices=[('_blank', '_blank'), ('_self', '_self'), ('_parent', '_parent'), ('_top', '_top')], icon='cup', required=False))])), ('group', wagtail.blocks.CharBlock(help_text='Any text. If present, Timeline will organize events with the same value for group to be in the same row or adjacent rows, separate from events in other groups. The common value for the group will be shown as a label at the left edge of the navigation.', max_length=255, required=False)), ('display_date', wagtail.blocks.CharBlock(help_text="A string for presenting the date. This value will be presented exactly as specified, overriding TimelineJS's default date formatting. Note that the year property, at a minimum, must still be provided so that TimelineJS can properly position the event on the actual timeline. ", max_length=255, required=False))])), ('events', wagtail.blocks.ListBlock(wagtail.blocks.StructBlock([('id', wagtail.blocks.CharBlock(help_text='A string value which is unique among all slides in your timeline. If not specified, TimelineJS will construct an ID based on the headline, but if you later edit your headline, the ID will change. Unique IDs are used when the hash_bookmark option is used, and can also be used with the timeline.goToId() method to programmatically move the timeline to a specific slide.', max_length=255, required=False)), ('start_date', wagtail.blocks.StructBlock([('year', wagtail.blocks.IntegerBlock(required=False)), ('month', wagtail.blocks.IntegerBlock(required=False, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)])), ('day', wagtail.blocks.IntegerBlock(required=False, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)])), ('hour', wagtail.blocks.IntegerBlock(required=False, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(23)])), ('minute', wagtail.blocks.IntegerBlock(required=False, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(59)])), ('second', wagtail.blocks.IntegerBlock(required=False, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(59)])), ('millisecond', wagtail.blocks.IntegerBlock(required=False, validators=[django.core.validators.MinValueValidator(0)])), ('display_date', wagtail.blocks.CharBlock(help_text="A string for presenting the date. This value will be presented exactly as specified, overriding TimelineJS's default date formatting. Note that the year property, at a minimum, must still be provided so that TimelineJS can properly position the event on the actual timeline. ", max_length=255, required=False)), ('format', wagtail.blocks.CharBlock(help_text="A formatting string which will be used to render the date parts, if you wish to override TimelineJS's default formatting. Note that in general you can achieve the same with display_date (above), without needing to master the complexity of the date format strings.", max_length=255, required=False))], required=True)), ('end_date', wagtail.blocks.StructBlock([('year', wagtail.blocks.IntegerBlock(required=False)), ('month', wagtail.blocks.IntegerBlock(required=False, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)])), ('day', wagtail.blocks.IntegerBlock(required=False, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)])), ('hour', wagtail.blocks.IntegerBlock(required=False, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(23)])), ('minute', wagtail.blocks.IntegerBlock(required=False, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(59)])), ('second', wagtail.blocks.IntegerBlock(required=False, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(59)])), ('millisecond', wagtail.blocks.IntegerBlock(required=False, validators=[django.core.validators.MinValueValidator(0)])), ('display_date', wagtail.blocks.CharBlock(help_text="A string for presenting the date. This value will be presented exactly as specified, overriding TimelineJS's default date formatting. Note that the year property, at a minimum, must still be provided so that TimelineJS can properly position the event on the actual timeline. ", max_length=255, required=False)), ('format', wagtail.blocks.CharBlock(help_text="A formatting string which will be used to render the date parts, if you wish to override TimelineJS's default formatting. Note that in general you can achieve the same with display_date (above), without needing to master the complexity of the date format strings.", max_length=255, required=False))], required=False)), ('text', wagtail.blocks.StructBlock([('headline', wagtail.blocks.RichTextBlock(required=False)), ('text', wagtail.blocks.RichTextBlock(required=False))])), ('media', wagtail.blocks.StructBlock([('image', wagtail.images.blocks.ImageChooserBlock(required=False)), ('url', wagtail.blocks.URLBlock(help_text='url, iframe or blockquote', required=False)), ('alt', wagtail.blocks.CharBlock(help_text='An alt tag for your image. If none is provided, the caption, if any, will be used.', max_length=255, required=False)), ('caption', wagtail.blocks.RichTextBlock(required=False)), ('credit', wagtail.blocks.RichTextBlock(required=False)), ('thumbnail', wagtail.blocks.URLBlock(help_text='A URL for an image to use in the timenav marker for this event. If omitted, Timeline will use an icon based on the type of media. Not relevant for title slides, because they do not have a marker.', required=False)), ('title', wagtail.blocks.CharBlock(help_text='A title for your image. If none is provided, the caption, if any, will be used. ', max_length=255, required=False)), ('link', wagtail.blocks.URLBlock(help_text='Optional URL to use as the href for wrapping the media with an <a> tag. ', required=False)), ('link_target', wagtail.blocks.ChoiceBlock(choices=[('_blank', '_blank'), ('_self', '_self'), ('_parent', '_parent'), ('_top', '_top')], icon='cup', required=False))])), ('group', wagtail.blocks.CharBlock(help_text='Any text. If present, Timeline will organize events with the same value for group to be in the same row or adjacent rows, separate from events in other groups. The common value for the group will be shown as a label at the left edge of the navigation.', max_length=255, required=False))])))]))], blank=True, null=True, use_json_field=True),
        ),
    ]
