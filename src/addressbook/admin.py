import uuid
from django.contrib import admin
from addressbook.models import (
    Appointment,
    Contact,
    PhoneNumber,
    Website,
    SocialNetwork,
    App,
    AppLink,
    AppStore,
    Email,
    Profile,
)
from facility.models import Organization, Facility
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe
from simple_history.admin import SimpleHistoryAdmin
from django.db.models import F
from django.contrib.postgres.search import SearchVector, SearchQuery
from neomodel import db
from directory.models import Effector, Entry, Directory
from directory.models import Facility as NeoFacility
from directory.utils import contact_uids
from access.utils import get_access
import logging

logger=logging.getLogger(__name__)


class ContactDirectoryFilter(admin.SimpleListFilter):
    title = 'Directory'
    parameter_name = 'directory'

    def lookups(self, request, model_admin):
        lookups = list(
            Directory.objects.values_list('name', 'display_name')
        )
        return lookups

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        try:
            directory=Directory.objects.get(name=self.value())
        except Directory.DoesNotExist:
            return Contact.objects.none()
        uids=contact_uids(directory=directory)
        try:
            return queryset.filter(neomodel_uid__in=uids)
        except TypeError:
            return Contact.objects.none()


class ContactOrganizationFilter(admin.SimpleListFilter):
    title = 'Organization'
    parameter_name = 'organization'

    def lookups(self, request, model_admin):
        lookups = list(
            Organization.objects.values_list('id', 'formatted_name')
        )
        lookups.append((0, _('None')))
        return lookups

    def queryset(self, request, queryset):
        id = self.value()
        if not id:
            return queryset
        elif id == '0':
            org = None
        else:
            org = Organization.objects.get(id=int(id))
        return queryset.filter(organisation=org)


class ContactFacilityFilter(admin.SimpleListFilter):
    title = 'Facility'
    parameter_name = 'facility'

    def lookups(self, request, model_admin):
        lookups = list(
            Facility.objects.values_list('id', 'contact__formatted_name')
        )
        lookups.append((0, _('None')))
        return lookups
        
    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        if self.value() == '0':
            facility = None
        else:
            facility = Facility.objects.get(id=int(self.value()))
        return queryset.filter(facility=facility)


class SocialInline(admin.StackedInline):
    model = SocialNetwork
    extra = 0

class WebsiteInline(admin.TabularInline):
    model = Website
    extra = 0

class PhoneInline(admin.TabularInline):
    model = PhoneNumber
    extra = 0

class EmailInline(admin.TabularInline):
    model = Email
    extra = 0

# addressbook.Address is not registered, and AddressInline is not attached to
# ContactAdmin.
#
# Nothing reads the table. A facility's address lives on the Facility node —
# street, zip, building, geographical_complement, location — and
# ContactSerializer.get_address() resolves it through neomodel_uid rather than
# from here, so the footer, the contact page and the organisation payload all
# come from the graph. The 131 remaining rows are residue from before that
# move, plus 17 written by the retired create_organization command.
#
# The rows are left in place; only the editing surface is withdrawn. An
# administrator filling in a street here would have seen it save and change
# nothing on the site, which is a worse failure than the field being absent.
# Re-registering is a one-line change if a reader ever appears.

class AppointmentInline(admin.TabularInline):
    model = Appointment
    extra = 0

class ProfileInline(admin.StackedInline):
    model = Profile
    extra = 0


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = (
        'name_tag',
        'profile_image_tag',
        'neomodel_uid',
        'phone_tag',
        'user_tag',
        'email_tag',
        'profile_tag',
    )
    fields = (
        'formatted_name',
        'formatted_name_definite_article',
        'user',
        'name_tag',
        'profile_image_tag',
        'phone_tag',
        'user_tag',
        'email_tag',
        'profile_image',
        'neomodel_uid',
    )
    search_fields = ['id', 'neomodel_uid']
    readonly_fields = (
        'name_tag',
        'profile_image_tag',
        'phone_tag',
        'user_tag',
        'email_tag',
        'profile_image_tag',
    )
    autocomplete_fields = ['user']
    inlines = [
        EmailInline,
        PhoneInline,
        SocialInline,
        WebsiteInline,
        AppointmentInline,
        ProfileInline,
    ]
    list_filter = [
        #ContactOrganizationFilter,
        #ContactFacilityFilter,
        #("neomodel_uid", admin.EmptyFieldListFilter),
        #ContactDirectoryFilter,
    ]

    @admin.display(description='User')
    def user_tag(self, obj):
        if not obj.user:
            return "∅"
        try:
            return f"{str(obj.user)[:10]}.."
        except TypeError:
            return "∅"

    @admin.display(description=_('Building'))
    def building_tag(self, obj):
        return

    @admin.display(description=_('Street'))
    def street_tag(self, obj):
        return

    @admin.display(description=_('Geo complement'))
    def geographical_complement_tag(self, obj):
        return

    @admin.display(description='zip')
    def zip_tag(self, obj):
        return

    @admin.display(description=_('City'))
    def city_tag(self, obj):
        return
        
    @admin.display(description='GPS')
    def gps_tag(self, obj):
        return

    @admin.display(description='Name')
    def name_tag(self, obj):
        if not obj.neomodel_uid:
            return
        try:
            entry = Entry.nodes.get(uid=obj.neomodel_uid.hex)
        except Exception as e:
            logger.error(e)
            return
        effector: list[Effector]= entry.effector.all()
        try:
            return effector[0].name_fr
        except Exception as e:
            return

    @admin.display(description='Phones')
    def phone_tag(self, obj):
        return [phone.phone for phone in obj.phonenumbers.all()]

    @admin.display(description='Emails')
    def email_tag(self, obj):
        return [email.email for email in obj.emails.all()]

    @admin.display(description='Profile img')
    def profile_image_tag(self, obj):
        if obj.profile_image:
            try:
                return mark_safe(
                    '<img src="%s" alt="profile picture" width="%s" height="%s">'
                    % (
                        obj.profile_image["avatar_facebook"].url,
                        obj.profile_image["avatar_facebook"].thumbnail_options["size"][0],
                        "100%"
                    )
                )
            except Exception as e:
                logger.error(e)
                return
    
    @admin.display(description=_('Profile'))
    def profile_tag(self, obj):
        return obj.profile.text[:35]


@admin.register(App)
class AppAdmin(admin.ModelAdmin):
    pass


@admin.register(AppLink)
class AppLinkAdmin(admin.ModelAdmin):
    pass


@admin.register(AppStore)
class AppStoreAdmin(admin.ModelAdmin):
    pass


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    autocomplete_fields = ['contact']
    
    
@admin.register(PhoneNumber)
class PhoneNumberAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "contact",
        "type",
        "phone",
    )
    list_filter = ["type"]


@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_display = (
        'url',
        'access_tag',
        'contact',
    )
    fields = (
        'url',
        'access_tag',
        'contact',
    )
    readonly_fields = (
        'access_tag',
    )
    @admin.display(description=_('Access'))
    def access_tag(self, obj):
        return get_access(obj.roles.all())


admin.site.register(SocialNetwork, admin.ModelAdmin)
admin.site.register(Email, admin.ModelAdmin)
admin.site.register(Profile, SimpleHistoryAdmin)