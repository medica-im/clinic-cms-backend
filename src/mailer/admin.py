from django import forms
from django.contrib import admin

from mailer.models import BatchEmailMessage, MailgunAccount


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


class MailgunAccountForm(forms.ModelForm):
    """Keeps the stored API key out of the rendered page.

    The key is shown as an empty password field with a note that one is on
    file; submitting the form blank keeps what is stored, so an administrator
    editing the From name never has to re-enter the credential.
    """

    api_key = forms.CharField(
        label="API key",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text=MailgunAccount._meta.get_field("api_key").help_text,
    )

    class Meta:
        model = MailgunAccount
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.api_key:
            self.fields["api_key"].help_text = (
                "A key is on file. Leave blank to keep it, or type a new one "
                "to replace it."
            )

    def clean_api_key(self):
        submitted = self.cleaned_data.get("api_key")
        if submitted:
            return submitted
        if self.instance.pk:
            return self.instance.api_key
        raise forms.ValidationError("An API key is required.")


@admin.register(MailgunAccount)
class MailgunAccountAdmin(admin.ModelAdmin):
    form = MailgunAccountForm
    list_display = ("organization", "from_email", "domain", "region", "active")
    list_filter = ("active", "region")
    search_fields = ("organization__name", "from_email", "domain")
    readonly_fields = ("created", "updated")
    fieldsets = (
        (None, {"fields": ("organization", "active")}),
        ("Identity", {"fields": ("from_email", "from_name")}),
        ("Mailgun credentials", {"fields": ("domain", "region", "sending_key_id", "api_key")}),
        ("Dates", {"fields": ("created", "updated")}),
    )
