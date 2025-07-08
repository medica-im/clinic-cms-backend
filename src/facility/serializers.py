import logging
from facility.models import Organization, Category, Facility, LegalEntity
from addressbook.api.serializers import ContactSerializer
from rest_framework import serializers
from directory.models import Organization as Neo4jOrganization

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


class FacilitySerializer(serializers.ModelSerializer):
    contact = ContactSerializer(many=False, read_only=True)
    
    class Meta:
        model = Facility
        fields = [
            'id',
            'name',
            'contact',
        ]
        depth = 3


class OrganizationSerializer(serializers.ModelSerializer):
    contact = ContactSerializer(many=False, read_only=True)
    facility = FacilitySerializer(many=True, read_only=True)
    legal_entity = LegalEntitySerializer(many=False, read_only=True)
    uid = serializers.UUIDField(format='hex', source='neomodel_uid')
    department = serializers.SerializerMethodField()

    def get_department(self, obj):  # type: ignore
        try:
            organization = Neo4jOrganization.nodes.get(uid=obj.neomodel_uid.hex)
        except Exception as e:
            logger.error(f"{e}\n Cannot find an Organization neo4j node with uid {obj.neomodel_uid.hex} for Organization {obj.name}")
            return
        try:
            commune = organization.commune
        except Exception as e:
            logger.error(f"{e}")
        try:
            department = commune.department
        except Exception as e:
            logger.error(f"{e}")
        try:
            return {
                "uid": department.uid,
                "name": department.name,
                "code": department.code,
                "slug": department.slug,
                "wikidata": department.wikidata
            }
        except Exception as e:
            return


    class Meta:
        model = Organization
        fields = [
            'id',
            'name',
            'company_name',
            'language',
            'formatted_name',
            'formatted_name_definite_article',
            'website_title',
            'website_description',
            'category',
            'contact',
            'facility',
            'registration',
            'google_site_verification',
            'city',
            'legal_entity',
            'uid',
            'department',
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