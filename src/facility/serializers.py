import logging
from facility.models import Organization, Category, Facility, LegalEntity
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


class OrganizationSerializer(serializers.ModelSerializer):
    contact = ContactSerializer(many=False, read_only=True)
    legal_entity = LegalEntitySerializer(many=False, read_only=True)
    uid = serializers.UUIDField(format='hex', source='neomodel_uid')
    commune = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    timezone = serializers.SerializerMethodField()

    def _get_commune_and_department(self, obj):
        """Traverse Neo4j: Entry → Facility → Commune → Department. Cached per obj."""
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
            return None, None
        try:
            facility = entry.facility.all()[0]
        except Exception as e:
            logger.error(f"{e}")
            return None, None
        try:
            commune = facility.commune.all()[0]
        except Exception as e:
            logger.error(e)
            return None, None
        try:
            department = commune.department.all()[0]
        except Exception as e:
            logger.error(f"{e}")
            return commune, None
        return commune, department

    def get_commune(self, obj):
        commune, _ = self._get_commune_and_department(obj)
        if not commune:
            return None
        return {
            "uid": commune.uid,
            "name_fr": commune.name_fr,
            "slug_fr": commune.slug_fr,
            "wikidata": commune.wikidata,
        }

    def get_timezone(self, obj):
        return str(obj.timezone)

    def get_department(self, obj):
        _, department = self._get_commune_and_department(obj)
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
            'timezone',
            'logo',
            'logo_alt',
            'sandbox',
        ]
        depth = 4


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