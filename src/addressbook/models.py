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


class ContactManager(models.Manager):
    def get_by_natural_key(self, neomodel_uid):
        return self.get(neomodel_uid=neomodel_uid)


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
    qr_image = models.ImageField(upload_to="qr_images/", blank=True, null=True)
    twitter_handle = models.CharField(max_length=15, blank=True, null=True)
    worked_with = models.ManyToManyField('self', blank=True)
    tags = TaggableManager(blank=True,)
    neomodel_uid = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
    )

    objects = ContactManager()

    class Meta:
        ordering = ['formatted_name', 'last_name', 'first_name']


    def __str__(self):
        if self.formatted_name:
            return "%s %s" % (self.id, self.formatted_name)
        else:
            return "%s %s %s" % (self.id, self.first_name, self.last_name)

    def natural_key(self):
        return (self.neomodel_uid,)
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.neomodel_uid)
        except TypeError as e:
            logger.warn(f'uid is {self.neomodel_uid} {e}')


class AddressManager(models.Manager):
    def get_by_natural_key(self, contact):
        return self.get(contact__neomodel_uid=contact)


class Address(models.Model):

    class AddressType(models.TextChoices):
        HOME = 'Home', pgettext_lazy('Address', 'Home')
        WORK = 'Work', pgettext_lazy('Address', 'Work')

    class Direction(models.TextChoices):
        RIGHT = 'R', _('right')
        LEFT = 'L', _('left')
        TOP = 'T', _('top')
        BOTTOM = 'B', _('bottom')
        CENTER = 'C', _('center')
        AUTO = 'A', _('auto')

    class PublicHolidaysZone(models.TextChoices):
        ALSACE_MOSELLE = 'alsace-moselle', 'Alsace-Moselle'
        GUADELOUPE = 'guadeloupe', 'Guadeloupe'
        GUYANE = 'guyane', 'Guyane'
        LA_REUNION = 'la-reunion', 'La Réunion'
        MARTINIQUE = 'martinique', 'Martinique'
        MAYOTTE = 'mayotte', 'Mayotte'
        METROPOLE = 'metropole', 'Métropole'
        NOUVELLE_CALEDONIE = 'nouvelle-caledonie', 'Nouvelle-Calédonie'
        POLYNESIE_FRANCAISE = 'polynesie-francaise', 'Polynésie française'
        SAINT_BARTHELEMY = 'saint-barthelemy', 'Saint-Barthélemy'
        SAINT_MARTIN ='saint-martin', 'Saint-Martin'
        SAINT_PIERRE_ET_MIQUELON = 'saint-pierre-et-miquelon', 'Saint-Pierre-et-Miquelon'
        WALLIS_ET_FUTUNA = 'wallis-et-futuna', 'Wallis-et-Futuna'


    contact = models.OneToOneField(
        Contact,
        on_delete=models.CASCADE,
        related_name="address",
    )
    roles = models.ManyToManyField(
        Role,
        blank=True,
        help_text="Roles allowed so see the related object",
    )
    building = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Address line for building name",
    )
    street = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Address line for street name and house number",
    )
    geographical_complement = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Geographical complement to facilitate geolocation"
    )
    city = models.CharField(max_length=255)
    state = models.CharField(max_length=255, null=True, blank=True)
    country = CountryField()
    public_holidays_zone = models.CharField(
        max_length=255,
        choices=PublicHolidaysZone.choices,
        default=PublicHolidaysZone.METROPOLE
    )
    zip = models.CharField(max_length=255, null=True, blank=True)
    type = models.CharField(
        max_length=255,
        choices=AddressType.choices,
        default=AddressType.WORK,
    )
    public_visible = models.BooleanField(default=False)
    contact_visible = models.BooleanField(default=False)
    latitude = models.DecimalField(
        max_digits=17,
        decimal_places=15,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=17,
        decimal_places=15,
        null=True,
        blank=True,
    )
    zoom = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(21)
        ]
    )
    tooltip_direction = models.CharField(
        max_length=1,
        choices=Direction.choices,
        default=Direction.AUTO,
    )
    tooltip_permanent = models.BooleanField(
        default=False
    )
    tooltip_text = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    objects = AddressManager()

    def __str__(self):
        return '%s %s: %s %s, %s, %s' % (
            self.contact.first_name,
            self.contact.last_name,
            self.street,
            self.city,
            self.state,
            self.country
        )

    def natural_key(self):
        return self.contact.natural_key()

    natural_key.dependencies = ['addressbook.contact']


    class Meta:
        verbose_name_plural = "Addresses"


    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.contact.neomodel_uid)
        except TypeError as e:
            logger.warn(f'uid is {self.contact.neomodel_uid} {e}')


class PhoneNumberManager(models.Manager):
    def get_by_natural_key(self, phone, contact):
        return self.get(
            phone=phone,
            contact=Contact.objects.get_by_natural_key(contact)
        )


class PhoneNumber(models.Model):

    class TelephoneType(models.TextChoices):
        MOBILE = 'M', _('Mobile')
        MOBILE_WORK = 'MW', _('Mobile Work')
        WORK = 'W', _('Work')
        FAX = 'F', _('Fax')
        SKYPE = 'S', _('Skype')
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
    objects = PhoneNumberManager()

    class Meta:
        managed = True
        UniqueConstraint(
            fields=['contact', 'phone'],
            name='unique_contact_phone'
        )

    def __str__(self):
        return "%s %s: %s" % (
            self.contact.first_name,
            self.contact.last_name,
            self.phone
        )

    def natural_key(self):
        return (self.phone,) + self.contact.natural_key()

    natural_key.dependencies = [
        'addressbook.contact',
        'facility.organization'
    ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.contact.neomodel_uid)
        except TypeError as e:
            logger.warn(f'uid is {self.contact.neomodel_uid} {e}')


class Email(models.Model):

    class EmailType(models.TextChoices):
        PERSONAL = 'P', _('Personal')
        WORK = 'W', _('Work')
        MSSANTE = 'M', 'MSSanté'

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
    type = models.CharField(max_length=255, choices=EmailType.choices)
    public_visible = models.BooleanField(default=False)
    contact_visible = models.BooleanField(default=False)

    def __str__(self):
        return "%s %s: %s" % (
            self.contact.first_name,
            self.contact.last_name,
            self.email
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.contact.neomodel_uid)
        except TypeError as e:
            logger.warn(f'uid is {self.contact.neomodel_uid} {e}')


class Website(models.Model):
    
    class WebsiteType(models.TextChoices):
        WORK = 'W', _('Work')
        PERSONAL = 'PE', _('Personal')
        PORTFOLIO = 'PO', _('Portfolio')
        BLOG = 'Blog', _('Blog')

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
    website = models.URLField(blank=True)
    type = models.CharField(max_length=255, choices=WebsiteType.choices)
    public_visible = models.BooleanField(default=False)
    contact_visible = models.BooleanField(default=False)

    def __str__(self):
        return "%s %s: %s" % (self.contact.first_name, self.type, self.website)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.contact.neomodel_uid)
        except TypeError as e:
            logger.warn(f'uid is {self.contact.neomodel_uid} {e}')


class SocialNetwork(models.Model):

    class SocialNetworkType(models.TextChoices):
        SKYPE = 'S', 'Skype'
        TWITTER = 'T', 'Twitter'
        LINKEDIN = 'LI', 'LinkedIn'
        FACEBOOK = 'F', 'Facebook'
        PINTEREST = 'P', 'Pinterest'
        INSTAGRAM = 'I', 'Instagram'
        YOUTUBE = 'YT', 'YouTube'
        TIKTOK = 'TT', 'TikTok'
        SNAPCHAT = 'SC', 'Snapchat'
        TWITCH = 'TH', 'Twitch'

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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.contact.neomodel_uid)
        except TypeError as e:
            logger.warn(f'uid is {self.contact.neomodel_uid} {e}')


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
        models.UniqueConstraint(
            fields=['contact', 'organization'],
            name='unique_profile'
        )

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
            self.contact.formatted_name,
            self.phone or self.url or self.app.name
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Call the "real" save() method.
        try:
            update_contact_timestamp(self.contact.neomodel_uid)
        except TypeError as e:
            logger.warn(f'uid is {self.contact.neomodel_uid} {e}')


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