import logging
from facility.models import Organization, Category, Facility, LegalEntity
from nlp.models import City
from addressbook.api.serializers import ContactSerializer
from rest_framework import serializers
from directory.models import Organization as Neo4jOrganization
from directory.models import Entry

logger = logging.getLogger(__name__)

class LegalEntitySerializer(serializers.ModelSerializer):

    class Meta:
        model= LegalEntity
        fields= [
            'id',
            'name',
            'type',
            'get_type_display',
            'RNA',
            'SIREN',
            'SIRET',
            'RCS',
            'SHARE_CAPITAL',
            'VAT',
        ]


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ['id', 'name', 'label', 'to_label', 'from_label', 'grammatical_number']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            'id',
            'name',
            'formatted_name',
            'definition',
            'slug',
        ]


class OrganizationSerializer(serializers.ModelSerializer):
    contact = serializers.SerializerMethodField()
    legal_entity = LegalEntitySerializer(many=False, read_only=True)
    uid = serializers.UUIDField(format='hex', source='neomodel_uid')
    commune = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    city = CitySerializer(read_only=True)

    def _get_commune_and_department(self, obj):
        """Traverse Neo4j: Entry → Facility → Commune → Department. Cached per obj.

        Returns the facility as well, because the address is on that node and
        the walk to reach it is the same one. It used to be fetched separately
        through Organization.contact — a Django row whose only contribution was
        the `neomodel_uid` this method already reads from `obj`.
        """
        cache_attr = f'_cached_commune_dept_{obj.pk}'
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)
        result = self._fetch_commune_and_department(obj)
        setattr(self, cache_attr, result)
        return result

    def _fetch_commune_and_department(self, obj):
        try:
            entry = Entry.nodes.get(uid=obj.neomodel_uid.hex)
        except Exception as e:
            logger.error(f"{e}\n Cannot find an Entry neo4j node with uid {obj.neomodel_uid.hex} for Organization {obj.name}")
            return None, None, None
        try:
            facility = entry.facility.all()[0]
        except Exception as e:
            logger.error(f"{e}")
            return None, None, None
        try:
            commune = facility.commune.all()[0]
        except Exception as e:
            logger.error(e)
            return facility, None, None
        try:
            department = commune.department.all()[0]
        except Exception as e:
            logger.error(f"{e}")
            return facility, commune, None
        return facility, commune, department

    def get_contact(self, obj):
        """The organisation's contact details, with the address from the graph.

        The Contact row still supplies what is genuinely its own — the emails,
        phone numbers, websites and social networks hanging off it. Its
        `address` is replaced, because that key never held Django data: the old
        ContactSerializer.get_address() read `contact.neomodel_uid` and then
        walked Entry → Facility itself, which is the walk this serializer
        already performs for `commune` and `department`.

        The address stays nested under `contact` rather than being promoted to
        a field of its own. The frontend reads
        `organization.contact.address` in the footer, on the contact page and
        in publicHolidaysStore; moving it would be a breaking change for no
        gain, and the point here is to change the source, not the shape.

        An organisation with no Contact row still gets an address — which is
        the whole reason for the change, since nothing about a facility's
        street requires a row in the addressbook.
        """
        data = ContactSerializer(obj.contact).data if obj.contact else {}
        data = dict(data)
        data["address"] = self.get_address(obj)
        return data

    def get_address(self, obj):
        """The facility's address, read from the node it lives on."""
        facility, commune, department = self._get_commune_and_department(obj)
        if facility is None:
            return None

        public_holidays_zone = None
        if department is not None:
            try:
                public_holidays_zone = department.public_holiday_zone.all()[0].name
            except Exception as e:
                logger.debug(f"no public holiday zone: {e}")

        location = getattr(facility, "location", None)
        return {
            "building": facility.building,
            "city": commune.name_fr if commune is not None else None,
            # Always None, as it was before: the country is not on the facility
            # and no caller reads it.
            "country": None,
            "facility_uid": facility.uid,
            "geographical_complement": facility.geographical_complement,
            "latitude": location.latitude if location else None,
            "longitude": location.longitude if location else None,
            "street": facility.street,
            "zip": facility.zip,
            "zoom": facility.zoom,
            "tooltip_direction": facility.tooltip_direction,
            "tooltip_permanent": facility.tooltip_permanent,
            "tooltip_text": facility.tooltip_text,
            "public_holidays_zone": public_holidays_zone,
        }

    def get_commune(self, obj):
        _, commune, _ = self._get_commune_and_department(obj)
        if not commune:
            return None
        return {
            "uid": commune.uid,
            "name_fr": commune.name_fr,
            "slug_fr": commune.slug_fr,
            "wikidata": commune.wikidata,
        }

    def get_department(self, obj):
        _, _, department = self._get_commune_and_department(obj)
        if not department:
            return None
        return {
            "uid": department.uid,
            "name": department.name,
            "code": department.code,
            "slug": department.slug,
            "wikidata": department.wikidata
        }


    class Meta:
        model = Organization
        fields = [
            'id',
            'name',
            'company_name',
            'language',
            'formatted_name',
            'formatted_name_short',
            'formatted_name_definite_article',
            'website_title',
            'website_description',
            'category',
            'contact',
            'registration',
            'google_site_verification',
            'google_calendar_id',
            'google_calendar_api_key',
            'city',
            'commune',
            'legal_entity',
            'uid',
            'department',
            'logo',
            'logo_alt',
            'sandbox',
        ]