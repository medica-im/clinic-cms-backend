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
