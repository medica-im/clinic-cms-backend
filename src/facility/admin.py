from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Organization, Category, Facility, LegalEntity
from modeltranslation.admin import TranslationAdmin

@admin.register(Organization)
class OrganizationAdmin(TranslationAdmin):
    list_display = (
        'name',
        'neomodel_uid',
        'company_name',
        'formatted_name',
        'formatted_name_definite_article',
        'website_title',
        'active',
        'created',
        'updated',
        'site',
        'language',
        'category',
        'city',
    )
    list_filter = (
        'active',
        'category',
        'language',
        'city',
    )
    search_fields = [
        'name', 'formatted_name', 'city', 'company_name', 'neomodel_uid'
    ]
    autocomplete_fields = ['contact',]
    fields = (
        'name',
        'neomodel_uid',
        'contact',
        'company_name',
        'formatted_name',
        'formatted_name_definite_article',
        'website_title',
        'website_description',
        'active',
        'created',
        'updated',
        'site',
        'language',
        'category',
        'city',
        'logo',
        'logo_tag',
        'logo_alt',
        'google_site_verification'
    )
    readonly_fields = (
        'created',
        'updated',
        'logo_tag',
    )

    @admin.display(description='Logo thumbnail')
    def logo_tag(self, obj):
        if obj.logo:
            try:
                return mark_safe(
                    '<img src="%s" alt="profile picture" width="%s" height="%s">'
                    % (
                        obj.logo["avatar_facebook"].url,
                        obj.logo["avatar_facebook"].thumbnail_options["size"][0],
                        "100%"
                    )
                )
            except Exception as e:
                return


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'formatted_name',
        'definition',
        'slug',
    )
    search_fields = ['name', 'formatted_name',]


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'contact',
        'active',
        'created',
        'updated',
        'node',
    )
    list_filter = (
        'active',
        'organization',
    )
    search_fields = ['name', 'contact__formatted_name',]
    autocomplete_fields = ['contact',]

@admin.register(LegalEntity)
class LegalEntityAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'organization',
        'type',
    ]
    autocomplete_fields = ['organization',]
