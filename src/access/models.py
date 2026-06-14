import uuid

from django.db import models
from django.core.validators import MaxValueValidator

class Endpoint(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class RoleManager(models.Manager):
    def get_by_natural_key(self, name):
        return self.get(name=name)


class Role(models.Model):
    name = models.CharField(max_length=255, unique=True)
    label = models.CharField(max_length=255, unique=True, null=True)
    description = models.TextField(
        blank=True
    )
    objects = RoleManager()

    def __str__(self):
        return self.name

    def natural_key(self):
        return (self.name,)


class AccessControl(models.Model):
    endpoint = models.ForeignKey(
        "access.Endpoint",
        on_delete=models.CASCADE,
    )
    role = models.ForeignKey(
        "access.Role",
        on_delete=models.CASCADE,
    )
    permissions = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(15)]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['endpoint', 'role'],
                name='unique_accesscontrol_endpoint_role'
            )
        ]

    def __str__(self):
        return (
            "%s %s %s" %
            (self.endpoint.name, self.role.name, self.permissions)
        )

    def check_permission(self, permissions: int):
        if not 0 <= permissions < 16:
            return False
        return (permissions & self.permissions) > 0
    
    async def async_check_permission(self, permissions: int):
        if not 0 <= permissions < 16:
            return False
        return (permissions & self.permissions) > 0


class BatchInviteeJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        FAILED = "failed", "Failed"

    uid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    organization_neomodel_uid = models.UUIDField()
    user_uid = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    total_rows = models.PositiveIntegerField()
    processed_rows = models.PositiveIntegerField(default=0)
    successful_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    skipped_duplicate_email_count = models.PositiveIntegerField(default=0)
    skipped_active_user_count = models.PositiveIntegerField(default=0)
    failed_email_count = models.PositiveIntegerField(default=0)
    role = models.CharField(max_length=50)
    send_emails = models.BooleanField(default=True)
    summary = models.JSONField(default=list)
    celery_task_id = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"BatchInviteeJob {self.uid} ({self.status})"