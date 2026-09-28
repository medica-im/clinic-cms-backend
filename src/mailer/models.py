from django.db import models


class BatchEmailMessage(models.Model):
    author_uid = models.UUIDField(
        help_text="Neo4j UID of the User who authored the message"
    )
    subject = models.CharField(max_length=998)
    body = models.TextField()
    sent_at = models.BigIntegerField(
        help_text="Timestamp in milliseconds when the email was sent"
    )
    recipient_uids = models.JSONField(
        help_text="List of Neo4j User UIDs who were recipients"
    )
    mailgun_response = models.JSONField(
        help_text="Full Mailgun API response"
    )
    success = models.BooleanField(
        help_text="Whether the Mailgun API call succeeded"
    )

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"BatchEmail '{self.subject}' by {self.author_uid} at {self.sent_at}"


class MailgunAccount(models.Model):
    """Per-organization Mailgun credentials and From identity.

    An organization without a row here -- or with an inactive or incomplete
    one -- sends under the credentials in the .env file. See
    mailer.config.get_sender.
    """

    class Region(models.TextChoices):
        EU = "eu", "Europe (api.eu.mailgun.net)"
        US = "us", "United States (api.mailgun.net)"

    organization = models.OneToOneField(
        "facility.Organization",
        on_delete=models.CASCADE,
        related_name="mailgun_account",
    )
    domain = models.CharField(
        max_length=255,
        help_text="Mailgun sending domain, e.g. mail.example.org",
    )
    region = models.CharField(
        max_length=2,
        choices=Region.choices,
        default=Region.EU,
        help_text="Mailgun region the domain is hosted in",
    )
    sending_key_id = models.CharField(
        max_length=255,
        help_text="Mailgun sending key ID (the HTTP basic auth username)",
    )
    api_key = models.CharField(
        max_length=255,
        help_text="Mailgun sending key (the HTTP basic auth password)",
    )
    from_email = models.EmailField(
        help_text="Address the organization's mail is sent from",
    )
    from_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Display name shown next to the From address; optional",
    )
    active = models.BooleanField(
        default=True,
        help_text=(
            "Uncheck to fall back to the default credentials without "
            "deleting the row"
        ),
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mailgun account"
        verbose_name_plural = "Mailgun accounts"

    def __str__(self):
        return f"{self.organization} <{self.from_email}>"

    def is_usable(self) -> bool:
        """True when every field needed to authenticate and send is filled."""
        return bool(
            self.active
            and self.domain
            and self.sending_key_id
            and self.api_key
            and self.from_email
        )


class EmailTemplate(models.Model):
    """Subject and body of one kind of email, per organization or by default.

    organization NULL is the default for every organization without a row of
    its own; mailer.templating.get_template resolves organization row >
    default row > mailer.defaults, skipping any row that is not usable.
    Placeholders are written {{ name }}; see mailer.templating.render.
    """

    class Kind(models.TextChoices):
        INVITATION = "invitation", "Invitation"

    class ContentType(models.TextChoices):
        HTML = "html", "HTML"
        TEXT = "text", "Plain text"

    organization = models.ForeignKey(
        "facility.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="email_templates",
        help_text="Leave empty for the default used by every organization without its own",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    subject = models.CharField(max_length=998)
    body = models.TextField()
    content_type = models.CharField(
        max_length=8,
        choices=ContentType.choices,
        default=ContentType.HTML,
    )
    body_text = models.TextField(
        blank=True,
        help_text=(
            "Plain-text alternative sent with an HTML body; derived from the "
            "HTML when left empty"
        ),
    )
    active = models.BooleanField(
        default=True,
        help_text="Uncheck to fall back to the default without deleting the row",
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind"],
                name="email_template_one_per_organization_and_kind",
            ),
            # Postgres NULLs are not equal, so the constraint above lets any
            # number of defaults through.
            models.UniqueConstraint(
                fields=["kind"],
                condition=models.Q(organization__isnull=True),
                name="email_template_one_default_per_kind",
            ),
        ]

    def __str__(self):
        owner = self.organization or "default for all organizations"
        return f"{self.get_kind_display()} — {owner}"

    def is_usable(self) -> bool:
        """True when it can be sent: active, with a subject and a body."""
        return bool(self.active and self.subject and self.body)

    PROBLEM_MESSAGES = {
        "syntax": "Invalid template syntax: {detail}",
        "unknown_placeholder": "Unknown placeholder(s): {names}",
        "missing_signin_url": "The invitation must contain {{{{ signin_url }}}}",
        "mjml_source": "This is MJML source; paste the compiled HTML instead",
    }

    def clean(self):
        from django.core.exceptions import ValidationError

        from mailer.templating import validate_template

        problems = validate_template(self.kind, self.subject, self.body, self.body_text)
        errors: dict[str, list[str]] = {}
        for problem in problems:
            message = self.PROBLEM_MESSAGES[problem.code].format(
                detail=problem.detail, names=", ".join(problem.names or [])
            )
            errors.setdefault(problem.field, []).append(message)
        if errors:
            raise ValidationError(errors)
