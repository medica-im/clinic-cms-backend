from django.contrib import admin
from modeltranslation.admin import TranslationAdmin
from access.models import AccessControl, BatchInviteeJob, Endpoint, Role

@admin.register(Endpoint)
class EndpointAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'name',    
    ]
    search_fields = ["name"]
    
@admin.register(Role)
class RoleAdmin(TranslationAdmin):
    list_display = [
        'id',
        'name',
        'label',
        'description', 
    ]

@admin.register(AccessControl)
class AccessControlAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'endpoint',
        'role',
        'permissions',
    ]
    list_filter = (
        'endpoint',
    )
    autocomplete_fields = [
        'endpoint'
    ]


@admin.register(BatchInviteeJob)
class BatchInviteeJobAdmin(admin.ModelAdmin):
    list_display = (
        "uid",
        "status",
        "total_rows",
        "successful_count",
        "failed_count",
        "failed_email_count",
        "role",
        "created_at",
    )
    list_filter = ("status", "role")
    readonly_fields = (
        "uid",
        "organization_neomodel_uid",
        "user_uid",
        "created_at",
        "status",
        "total_rows",
        "processed_rows",
        "successful_count",
        "failed_count",
        "skipped_duplicate_email_count",
        "skipped_active_user_count",
        "failed_email_count",
        "role",
        "send_emails",
        "summary",
        "celery_task_id",
    )