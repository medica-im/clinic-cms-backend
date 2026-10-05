"""The mail service this deployment uses, chosen by settings.MAIL_PROVIDER."""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from mailer.providers.base import MailProvider


def get_provider() -> MailProvider:
    name = getattr(settings, "MAIL_PROVIDER", "mailgun")
    if name == "mailgun":
        from mailer.providers.mailgun import MailgunProvider
        return MailgunProvider()
    raise ImproperlyConfigured(f"Unknown MAIL_PROVIDER: {name!r}")
