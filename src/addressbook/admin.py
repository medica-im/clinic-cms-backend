import uuid
from django.contrib import admin
from addressbook.models import (
    Address,
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
from constance import config
from neomodel import db
from directory.models import Effector, Directory
from directory.models import Facility as NeoFacility
from directory.utils import contact_uids
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
        if not self.value():
            return queryset
        if self.value() == '0':
            org = None
        else:
            org = Organization.objects.get(id=int(self.value()))
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

class AddressInline(admin.StackedInline):
    model = Address
    extra = 0

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
        'building_tag',
        'street_tag',
        'geographical_complement_tag',
        'zip_tag',
        'city_tag',
        'gps_tag',
        'phone_tag',
        'user_tag',
        'type_tag',
        'title',
        'organization',
        'email_tag',
        'profile_tag',
    )
    fields = (
        'person_type',
        'formatted_name',
        'formatted_name_definite_article',
        'user',
        'name_tag',
        'profile_image_tag',
        'building_tag',
        'street_tag',
        'geographical_complement_tag',
        'zip_tag',
        'city_tag',
        'gps_tag',
        'phone_tag',
        'user_tag',
        'type_tag',
        'title',
        'organization',
        'email_tag',
        'profile_image',
        'neomodel_uid',
    )
    search_fields = ['neomodel_uid']
    readonly_fields = (
        'name_tag',
        'profile_image_tag',
        'building_tag',
        'street_tag',
        'geographical_complement_tag',
        'zip_tag',
        'city_tag',
        'gps_tag',
        'phone_tag',
        'user_tag',
        'type_tag',
        'email_tag',
        'profile_image_tag',
    )
    autocomplete_fields = ['user']
    inlines = [
        AddressInline,
        EmailInline,
        PhoneInline,
        SocialInline,
        WebsiteInline,
        AppointmentInline,
        ProfileInline,
    ]
    list_filter = [
        ContactOrganizationFilter,
        ContactFacilityFilter,
        ("neomodel_uid", admin.EmptyFieldListFilter),
        ContactDirectoryFilter,
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
        return obj.address.building

    @admin.display(description=_('Street'))
    def street_tag(self, obj):
        return obj.address.street

    @admin.display(description=_('Geo complement'))
    def geographical_complement_tag(self, obj):
        return obj.address.geographical_complement

    @admin.display(description='zip')
    def zip_tag(self, obj):
        return obj.address.zip

    @admin.display(description=_('City'))
    def city_tag(self, obj):
        return obj.address.city
        
    @admin.display(description='GPS')
    def gps_tag(self, obj):
        if obj.address.latitude and obj.address.longitude:
            return "✔️"
        else:
            return "❌"

    @admin.display(description='Name')
    def name_tag(self, obj):
        if obj.formatted_name:
            return obj.formatted_name
        if not obj.neomodel_uid:
            return
        try:
            return f"E: {Effector.nodes.get(uid=obj.neomodel_uid.hex).name_fr}"
        except:
            pass
        # node uid is the UUID4 hex representation without dashes:
        # FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        results, _meta = db.cypher_query(
            f"""MATCH (f:Facility)
            WHERE f.uid="{obj.neomodel_uid.hex}"
            RETURN f"""
        )
        if results:
            f=NeoFacility.inflate(results[0][0])
            organization_array=f.organization.all()
            if organization_array:
                organization=organization_array[0]
                return f'O: {organization.name_fr or organization.label_fr}'
        results, _meta = db.cypher_query(
            f"""MATCH (e:Effector)-[l:LOCATION]-(f:Facility)
            WHERE f.uid="{obj.neomodel_uid.hex}"
            RETURN e"""
        )
        if results:
            names=[]
            for e in results:
                effector=Effector.inflate(e[0])
                names.append(effector.name_fr or effector.label_fr)
            return f'F: {", ".join(names)}'
        # relationship uid is the UUID4 string representation with dashes:
        # FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF
        query=f"""MATCH (e:Effector)-[rel:LOCATION {{ uid: "{obj.neomodel_uid}"}}]->(f:Facility) RETURN e"""
        results, cols = db.cypher_query(query)
        if results:
            effector = Effector.inflate(results[0][cols.index('e')])
            return f"EF: {effector.name_fr}"
        # check for hex version of uid
        query=f"""MATCH (e:Effector)-[rel:LOCATION {{ uid: "{obj.neomodel_uid.hex}"}}]->(f:Facility) RETURN e"""
        results, cols = db.cypher_query(query)
        if results:
            effector = Effector.inflate(results[0][cols.index('e')])
            return f"EF: {effector.name_fr}"

    def get_search_results(self, request, queryset, search_term):
        is_uuid = False
        try:
            _uuid = uuid.UUID(search_term)
            is_uuid=True
        except ValueError:
            pass
        if is_uuid:
            search_queryset, may_have_duplicates = super().get_search_results(
            request,
            queryset,
            _uuid,
            )
            return search_queryset, may_have_duplicates
        query_ids = queryset.values_list('id', flat=True)
        final_queryset = Contact.objects.none()
        _config = config.ADMIN_SEARCH_CONFIG
        queryset_field = self.model.objects.annotate(
            search=SearchVector('formatted_name', config=_config) \
            + SearchVector('last_name', config=_config) \
            + SearchVector('first_name', config=_config) \
            + SearchVector('middle_name', config=_config),
            ).filter(
                search=SearchQuery(search_term, config=_config),
                id__in=query_ids
            )
        uids=contact_uids(search=search_term)
        final_queryset |= queryset_field
        if uids:
            queryset_cypher = self.model.objects.filter(
                neomodel_uid__in=uids,
                id__in=query_ids
            )
            final_queryset |= queryset_cypher
        return final_queryset.distinct(), False

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

    @admin.display(description='Type')
    def type_tag(self, obj):
        if obj.user:
            return _("Django User")
        elif obj.organization:
            return _("Organization")
        elif obj.facility:
            return _("Facility")
        
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
    
    
@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "contact",
        "street",
        "zip",
        "city",
        "country",
        "latitude",
        "longitude",
        "public_holidays_zone",
    )
    autocomplete_fields = ['contact']


admin.site.register(PhoneNumber, admin.ModelAdmin)
admin.site.register(Website, admin.ModelAdmin)
admin.site.register(SocialNetwork, admin.ModelAdmin)
admin.site.register(Email, admin.ModelAdmin)
admin.site.register(Profile, SimpleHistoryAdmin)