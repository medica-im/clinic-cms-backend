from django.contrib import admin
from mailer.models import BatchEmailMessage


@admin.register(BatchEmailMessage)
class BatchEmailMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "author_uid", "success", "sent_at")
    list_filter = ("success",)
    readonly_fields = (
        "author_uid",
        "subject",
        "body",
        "sent_at",
        "recipient_uids",
        "mailgun_response",
        "success",
    )
