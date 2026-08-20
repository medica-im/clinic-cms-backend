import logging
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models.functions import Length
from django.db.models import CharField

from easy_thumbnails.fields import (
    ThumbnailerImageField,
    ThumbnailerField,
)
from easy_thumbnails.widgets import ImageClearableFileInput
from django_countries.fields import CountryField
from taggit.managers import TaggableManager
from django.contrib.auth import get_user_model
from access.models import Role
from simple_history.models import HistoricalRecords
from easy_thumbnails.signals import saved_file
from easy_thumbnails.signal_handlers import generate_aliases
from django.db.models import UniqueConstraint
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone
from directory.timestamp import update_contact_timestamp

logger = logging.getLogger(__name__)

CharField.register_lookup(Length)

User = get_user_model()

saved_file.connect(generate_aliases)

def profile_image_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    path = settings.AVATAR_FILE_STORAGE
    return '{0}/{1}'.format(path, filename)

social_net_prefixes = dict(
    Skype='skype:',
    Twitter='https://twitter.com/',
    LinkedIn='https://linkedin.com/',
    Facebook='https://www.facebook.com/',
    Pinterest='https://www.pinterest.com/',
)


class Contact(models.Model):
    formfield_overrides = {
        ThumbnailerField: {'widget': ImageClearableFileInput},
    }

    class PersonType(models.TextChoices):
        NATURAL = 'Natural', _('Natural person')
        LEGAL = 'Legal', _('Legal person')

    person_type = models.CharField(
        max_length=255,
        choices=PersonType.choices,
        default=PersonType.NATURAL,
    )
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    formatted_name = models.CharField(max_length=255, blank=True)
    formatted_name_definite_article = models.CharField(
        max_length=255,
        blank=True,
    )
    last_name = models.CharField(max_length=255, blank=True)
    first_name = models.CharField(max_length=255, blank=True)
    middle_name = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=255, blank=True)
    organization = models.CharField(max_length=255, blank=True)
    url = models.URLField(blank=True)
    blurb = models.TextField(null=True, blank=True)
    profile_image = ThumbnailerImageField(
        upload_to=profile_image_path,
        blank=True,
        null=True
    )
    avatar_access = models.CharField(
        max_length=20,
        default='anonymous',
        help_text=(
            "Minimum role required to see the profile image: "
            "anonymous (public), staff (team), administrator."
        ),
    )
    qr_image = models.ImageField(upload_to="qr_images/", blank=True, null=True)
    twitter_handle = models.CharField(max_length=15, blank=True, null=True)
    worked_with = models.ManyToManyField('self', blank=True)
    tags = TaggableManager(blank=True,)
    neomodel_uid = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
    )

    # The contact's own last-modified stamp, and the only one that survives a
    # related object being deleted. A deleted phone takes its updatedAt with
    # it, so a max() over the survivors can move backwards in time — see
    # the post_delete receiver at the end of this module.
    updatedAt = models.DateTimeField(auto_now=True, null=True)

    def natural_key(self):
        return (self.neomodel_uid,)
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.neomodel_uid)
        except TypeError as e:
            logger.warning(f'uid is {self.neomodel_uid} {e}')
        # The avatar (and its access level) is embedded in the cached entry
        # payloads, so those must be rebuilt when it changes.
        from directory.models.core import sync_clear_cache
        sync_clear_cache("v2:entries")


class PhoneNumber(models.Model):

    class TelephoneType(models.TextChoices):
        MOBILE = 'M', _('Mobile')
        MOBILE_WORK = 'MW', _('Mobile Work')
        WORK = 'W', _('Work')
        FAX = 'F', _('Fax')
        ANSWERING_SERVICE = 'AS', _('Answering service')

    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="phonenumbers"
    )
    roles = models.ManyToManyField(
        Role,
        blank=True,
        help_text="Roles allowed so see the related object",
    )
    organization = models.ManyToManyField(
        "facility.Organization",
        blank=True
    )
    phone = models.CharField(max_length=255)
    type = models.CharField(max_length=255, choices=TelephoneType.choices)
    public_visible = models.BooleanField(default=False)
    contact_visible = models.BooleanField(default=False)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["contact", "phone", "type"], name="unique_contact_phone_type"),
        ]

    def __str__(self):
        return "%s %s: %s" % (
            self.contact.first_name,
            self.contact.last_name,
            self.phone
        )

#    def natural_key(self):
#        return (self.phone,) + self.contact.natural_key()

#    natural_key.dependencies = [
#        'addressbook.contact',
#        'facility.organization'
#    ]

    # Maintained by the ORM rather than by a save() override, so a write path
    # that bypasses save() — a queryset .update(), the Django admin, a data
    # migration — still leaves a mark. The administrative entries table reads
    # the max of these across an entry's objects for its "last modified"
    # column, and the entry detail page reads them individually to say which
    # part changed.
    updatedAt = models.DateTimeField(auto_now=True, null=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.contact.neomodel_uid)
        except TypeError as e:
            logger.warning(f'uid is {self.contact.neomodel_uid} {e}')


class Email(models.Model):
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="emails",
    )
    roles = models.ManyToManyField(
        Role,
        blank=True,
        help_text="Roles allowed so see the related object",
    )
    organization = models.ManyToManyField(
        "facility.Organization",
        blank=True
    )
    email = models.EmailField()
    public_visible = models.BooleanField(default=False)
    contact_visible = models.BooleanField(default=False)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["contact", "email"], name="unique_contact_email"),
        ]

    def __str__(self):
        return "%s %s: %s" % (
            self.contact.first_name,
            self.contact.last_name,
            self.email
        )

    # Maintained by the ORM rather than by a save() override, so a write path
    # that bypasses save() — a queryset .update(), the Django admin, a data
    # migration — still leaves a mark. The administrative entries table reads
    # the max of these across an entry's objects for its "last modified"
    # column, and the entry detail page reads them individually to say which
    # part changed.
    updatedAt = models.DateTimeField(auto_now=True, null=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.contact.neomodel_uid)
        except TypeError as e:
            logger.warning(f'uid is {self.contact.neomodel_uid} {e}')


class Website(models.Model):
    
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="websites",
    )
    roles = models.ManyToManyField(
        Role,
        blank=True,
        help_text="Roles allowed so see the related object",
    )
    organization = models.ManyToManyField(
        "facility.Organization",
        blank=True
    )
    url = models.URLField(blank=True)
    public_visible = models.BooleanField(default=False)
    contact_visible = models.BooleanField(default=False)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["contact", "url"], name="unique_contact_url"),
        ]

    def __str__(self):
        return "%s: %s" % (self.contact.neomodel_uid, self.url)

    # Maintained by the ORM rather than by a save() override, so a write path
    # that bypasses save() — a queryset .update(), the Django admin, a data
    # migration — still leaves a mark. The administrative entries table reads
    # the max of these across an entry's objects for its "last modified"
    # column, and the entry detail page reads them individually to say which
    # part changed.
    updatedAt = models.DateTimeField(auto_now=True, null=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.contact.neomodel_uid)
        except TypeError as e:
            logger.warning(f'uid is {self.contact.neomodel_uid} {e}')


class SocialNetwork(models.Model):

    class SocialNetworkType(models.TextChoices):
        TWITTER = 'T', 'X'
        LINKEDIN = 'LI', 'LinkedIn'
        FACEBOOK = 'F', 'Facebook'
        PINTEREST = 'P', 'Pinterest'
        INSTAGRAM = 'I', 'Instagram'
        YOUTUBE = 'YT', 'YouTube'
        TIKTOK = 'TT', 'TikTok'
        SNAPCHAT = 'SC', 'Snapchat'
        TWITCH = 'TH', 'Twitch'
        BLUESKY = 'B', 'Bluesky'
        MASTODON = 'M', 'Mastodon'

    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="socialnetworks",
    )
    roles = models.ManyToManyField(
        Role,
        blank=True,
        help_text="Roles allowed so see the related object",
    )
    organization = models.ManyToManyField(
        "facility.Organization",
        blank=True
    )
    handle = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=255, choices=SocialNetworkType.choices)
    public_visible = models.BooleanField(default=False)
    contact_visible = models.BooleanField(default=False)
    url = models.URLField(blank=True)

    def __str__(self):
        return (
            f"{self.contact.formatted_name} {self.type} "
            f"{self.handle or self.url}"
        )

    # Maintained by the ORM rather than by a save() override, so a write path
    # that bypasses save() — a queryset .update(), the Django admin, a data
    # migration — still leaves a mark. The administrative entries table reads
    # the max of these across an entry's objects for its "last modified"
    # column, and the entry detail page reads them individually to say which
    # part changed.
    updatedAt = models.DateTimeField(auto_now=True, null=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.contact.neomodel_uid)
        except TypeError as e:
            logger.warning(f'uid is {self.contact.neomodel_uid} {e}')


class Profile(models.Model):
    contact = models.OneToOneField(
        Contact,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    roles = models.ManyToManyField(
        Role,
        blank=True,
        help_text="Roles allowed so see the related object",
    )
    organization = models.ForeignKey(
        "facility.Organization",
        on_delete=models.SET_NULL,
        related_name="profiles",
        null=True,
        blank=True, 
    )
    text = models.TextField(
        blank=True    
    )
    changed_by = models.ForeignKey(
      settings.AUTH_USER_MODEL,
      on_delete=models.PROTECT
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return (
            f"{self.contact.formatted_name} {self.text[0:35]}"
        )

    @property
    def _history_user(self):
        return self.changed_by

    @_history_user.setter
    def _history_user(self, value):
        self.changed_by = value


    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['contact', 'organization'],
                name='unique_profile',
            ),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.contact.neomodel_uid)
        except TypeError as e:
            logger.warn(f'uid is {self.contact.neomodel_uid} {e}')


class Appointment(models.Model):
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="appointments"
    )
    roles = models.ManyToManyField(
        Role,
        blank=True,
        help_text="Roles allowed so see the related object",
    )
    organization = models.ManyToManyField(
        "facility.Organization",
        blank=True
    )
    url = models.URLField(blank=True)
    phone = models.CharField(max_length=255, blank=True)
    app = models.ForeignKey(
        'addressbook.App',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    house_call = models.BooleanField(
        default=False
    )


    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(url__length__gt=0,phone__length__lte=0,app__isnull=True)
                    |
                    Q(url__length__lte=0,phone__length__gt=0,app__isnull=True)
                    |
                    Q(url__length__lte=0,phone__length__lte=0,app__isnull=False)
                ),
                name='one_and_only_one_field_not_null_among_url_phone_app'
            )
        ]

    def __str__(self):
        return "%s: %s" % (
            self.contact.neomodel_uid,
            self.phone or self.url or self.app
        )

    # Maintained by the ORM rather than by a save() override, so a write path
    # that bypasses save() — a queryset .update(), the Django admin, a data
    # migration — still leaves a mark. The administrative entries table reads
    # the max of these across an entry's objects for its "last modified"
    # column, and the entry detail page reads them individually to say which
    # part changed.
    updatedAt = models.DateTimeField(auto_now=True, null=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.contact.neomodel_uid)
        except TypeError as e:
            logger.warning(f'uid is {self.contact.neomodel_uid} {e}')


class App(models.Model):
    name = models.CharField(
        max_length=255,
        blank=True,
        unique=True
    )
    label = models.CharField(
        max_length=255,
        blank=True
    )
    links = models.ManyToManyField(
        'addressbook.AppLink',
    )

    def __str__(self):
        return self.name


class AppLink(models.Model):
    url = models.URLField(blank=True)
    store = models.ForeignKey(
        'addressbook.AppStore',
        on_delete=models.CASCADE,
        related_name="links"
    )

    def __str__(self):
        return "%s %s" % (
            self.url,
            self.store.name,
        )


class AppStore(models.Model):
    name = models.CharField(max_length=255, unique=True)
    image = models.ImageField(blank=True, null=True)

    def __str__(self):
        return self.name


# Deletion has to move the contact's stamp, and it cannot be done in a model's
# delete(): every delete route in api/routers/ calls
# `.filter(id=...).adelete()`, a queryset delete that never loads the instance.
# post_delete fires for both forms, and for the Django admin and data
# migrations besides.
@receiver(post_delete, sender=PhoneNumber)
@receiver(post_delete, sender=Email)
@receiver(post_delete, sender=Website)
@receiver(post_delete, sender=SocialNetwork)
def touch_contact_on_delete(sender, instance, **kwargs):
    """Stamp the contact when one of its objects is deleted.

    Without this the administrative table shows an entry growing *younger*
    after an edit: the deleted row's timestamp was the maximum, and removing it
    leaves an older one behind.

    contact_id rather than instance.contact: the related object may already be
    gone from the session, and this only needs the key. save(update_fields=...)
    keeps it to one column and still triggers auto_now.
    """
    contact_id = getattr(instance, "contact_id", None)
    if not contact_id:
        return
    # update() rather than save(): auto_now does not fire on a queryset update,
    # so the value is set explicitly, and no other field is touched.
    Contact.objects.filter(pk=contact_id).update(updatedAt=timezone.now())
