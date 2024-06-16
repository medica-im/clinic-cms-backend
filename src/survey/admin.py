from django.contrib import admin
from survey.models import Survey, Response

@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    autocomplete_fields = ["moderators"]
    list_display = [
        "id", "name", "label", "created", "is_active", "start", "end", "site"
    ]
    readonly_fields=('created',)

@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ["id", "survey", "moderation", "content", "created"]
    readonly_fields=('created',)