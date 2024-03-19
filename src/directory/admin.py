import logging
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import (
    Slug,
    RejectSlug,
    Asset,
    AssetFacility,
    Directory,
    InputField,
    Setting,
    Label,
    EffectorType,
)
from modeltranslation.admin import TranslationAdmin
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.translation import get_language


logger = logging.getLogger(__name__)

@admin.register(Slug)
class SlugAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'slug',
        'site',
        'user',    
    )
    list_filter = (
        'site',
    )
    autocomplete_fields = [
        'user',
        'site',
    ]


@admin.register(RejectSlug)
class RejectSlugAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'slug',    
    )
    search_fields = ['slug']


class AssetFacilityInline(admin.TabularInline):
    model = AssetFacility
    extra = 1
    fk_name = 'asset'


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'neomodel_uid',
    )
    inlines = (
        AssetFacilityInline,
    )


@admin.register(Directory)
class DirectoryAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'display_name',
        'presentation',
        'slug',
        'postal_codes',
    )


@admin.register(InputField)
class InputFieldAdmin(admin.ModelAdmin):
    list_display = (
        'directory',
        'geocoder',
        'situation',
        'commune',
        'category',
        'facility',
        'search',
    )


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = (
        'directory',
        'sort_category',
    )


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = (
        'label',
        'language',
        'uid',
        'effector_type_tag',
        'genders_tag',
        'grammatical_number',
    )
    list_filter = (
        'language',
        'gender',
        'grammatical_number',
        'uid',
    )
    fields = (
        'label',
        'language',
        'uid',
        'effector_type_tag',
        'gender',
        'genders_tag',
        'grammatical_number',
    )
    readonly_fields = (
        'effector_type_tag',
        'genders_tag',
    )

    @admin.display(description = _("Genders"))
    def genders_tag(self, obj):
        return [gender.name for gender in obj.gender.all()]

    @admin.display(description='EffectorType')
    def effector_type_tag(self, obj):
        logger.debug(f'{obj.uid}')
        #uid = str(obj.uid).replace("-", "")
        try:
            et=EffectorType.nodes.get(uid=obj.uid.hex)
        except:
            logger.warn(f'No node found for uid="{obj.uid}"')
            return
        return et.label_fr or et.name_fr or et.label_en or et.name_en