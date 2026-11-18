"""The mail service this deployment uses, chosen by settings.MAIL_PROVIDER."""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from mailer.providers.base import MailProvider


def get_provider() -> MailProvider:
    name = getattr(settings, "MAIL_PROVIDER", "mailgun")
    provider = provider_named(name)
    if provider is None:
        raise ImproperlyConfigured(f"Unknown MAIL_PROVIDER: {name!r}")
    return provider


def provider_named(name: str) -> MailProvider | None:
    """A provider by the name in its webhook URL; None for one we do not have."""
    if name == "mailgun":
        from mailer.providers.mailgun import MailgunProvider
        return MailgunProvider()
    return None
