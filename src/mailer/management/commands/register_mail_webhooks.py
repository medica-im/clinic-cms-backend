"""Point a sending domain's delivery-event webhooks at this backend.

    manage.py register_mail_webhooks --url https://<this server>/api/v2/mail/events/mailgun
        [--domain mail.example.org] [--replace] [--dry-run]

A domain's webhook reaches one URL, and a domain may be shared by several
backends: a webhook already pointing elsewhere is never moved without
--replace, or one backend would silently take another's events. Every
webhook is read before any is changed, so a refusal changes nothing.
Tested by tests/test_register_mail_webhooks.py.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from mailer.providers import mailgun


class Command(BaseCommand):
    help = "Point a sending domain's delivery-event webhooks at this backend."

    def add_arguments(self, parser):
        parser.add_argument("--url", required=True, help="This backend's events URL")
        parser.add_argument("--domain", default=None, help="Sending domain (default: MAILGUN_DOMAIN)")
        parser.add_argument("--replace", action="store_true", help="Move webhooks that point elsewhere")
        parser.add_argument("--dry-run", action="store_true", help="Say what would change, change nothing")

    def handle(self, *args, url, domain, replace, dry_run, **options):
        domain = domain or settings.MAILGUN_DOMAIN
        try:
            targets = mailgun.webhook_targets(domain)
        except RuntimeError as e:
            raise CommandError(str(e))

        elsewhere = {name: urls for name, urls in targets.items() if urls and url not in urls}
        if elsewhere and not replace:
            lines = "\n".join(f"  {name}: {', '.join(urls)}" for name, urls in elsewhere.items())
            raise CommandError(
                f"{domain}: these webhooks already point elsewhere, and moving them would take that "
                f"backend's events:\n{lines}\nUse --replace if that is intended."
            )

        for name, urls in targets.items():
            if url in urls:
                self.stdout.write(f"{name}: already {url}")
                continue
            verb = "replace" if urls else "create"
            if dry_run:
                self.stdout.write(f"{name}: would {verb} -> {url}")
                continue
            try:
                mailgun.point_webhook(domain, name, url, exists=bool(urls))
            except RuntimeError as e:
                raise CommandError(str(e))
            self.stdout.write(self.style.SUCCESS(f"{name}: {verb}d -> {url}"))
