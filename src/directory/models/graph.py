import logging
from uuid import uuid4
from neomodel import (
    config,
    StructuredNode,
    ArrayProperty,
    BooleanProperty,
    StringProperty,
    IntegerProperty,
    DateTimeFormatProperty,
    UniqueIdProperty,
    ArrayProperty,
    RelationshipTo,
    RelationshipFrom,
    Relationship,
    StructuredRel,
    ZeroOrOne,
    OneOrMore,
)
from django.utils.translation import get_language

logger=logging.getLogger(__name__)

class PaymentMethod(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    label_fr = StringProperty()
    label_en = StringProperty()
    definition_fr = StringProperty()
    definition_en = StringProperty()


class ThirdPartyPayer(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    label_fr = StringProperty()
    label_en = StringProperty()
    definition_fr = StringProperty()
    definition_en = StringProperty()


class Convention(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    label = StringProperty()
    definition = StringProperty()


class Need(StructuredNode):
    uid = UniqueIdProperty()
    name_fr = StringProperty(unique_index=True)
    name_en = StringProperty(unique_index=True)
    definition_fr = StringProperty()
    definition_en = StringProperty()
    need = RelationshipTo('Need', 'PART_OF')


class EffectorType(StructuredNode):
    uid = UniqueIdProperty()
    label_fr = StringProperty(unique_index=True)
    label_en = StringProperty(unique_index=True)
    name_fr = StringProperty(unique_index=True)
    name_en = StringProperty(unique_index=True)
    slug_en = StringProperty(unique_index=True)
    slug_fr = StringProperty(unique_index=True)
    synonyms_fr = ArrayProperty(base_property=StringProperty())
    synonyms_en = ArrayProperty(base_property=StringProperty())
    definition_fr = StringProperty()
    definition_en = StringProperty()
    need = RelationshipTo('Need', 'MANAGES')
    situation = RelationshipTo('Situation', 'MANAGES')


class HCW(EffectorType):
    concept_en = StringProperty(unique_index=True)
    concept_fr = StringProperty(unique_index=True)
    unique_ID = StringProperty(unique_index=True)
    hcw = RelationshipTo('HCW', 'IS_A')


class MESH(StructuredNode):
    uid = UniqueIdProperty()
    label_fr = StringProperty(unique_index=True)
    label_en = StringProperty(unique_index=True)
    definition_en = StringProperty()
    definition_fr = StringProperty()
    concept_en = StringProperty(unique_index=True)
    concept_fr = StringProperty(unique_index=True)
    unique_ID = StringProperty(unique_index=True)
    is_a = RelationshipTo('MESH', 'IS_A')
    need = RelationshipTo('Need', 'MANAGES')
    situation = RelationshipTo('Situation', 'MANAGES')


class Situation(StructuredNode):
    uid = UniqueIdProperty()
    name_en = StringProperty(unique_index=True)
    name_fr = StringProperty(unique_index=True)
    definition_en = StringProperty()
    definition_fr = StringProperty()
    ICD_11 = ArrayProperty(StringProperty())
    impacts_need = RelationshipTo('Need', 'IMPACTS')


class OrganizationType(StructuredNode):
    uid = UniqueIdProperty()
    label_en = StringProperty(unique_index=True)
    label_fr = StringProperty(unique_index=True)
    name_en = StringProperty(unique_index=True)
    name_fr = StringProperty(unique_index=True)
    synonyms_fr = ArrayProperty(base_property=StringProperty())
    synonyms_en = ArrayProperty(base_property=StringProperty())
    organization_type = RelationshipTo(
        'OrganizationType',
        'PART_OF'
    )


class Website(StructuredNode):
    uid = UniqueIdProperty()
    url = StringProperty(unique_index=True)


class Organization(StructuredNode):
    uid = UniqueIdProperty()
    label_en = StringProperty(unique_index=True)
    label_fr = StringProperty(unique_index=True)
    name_en = StringProperty(unique_index=True)
    name_fr = StringProperty(unique_index=True)
    type = RelationshipTo(
        'OrganizationType',
        'IS_A'
    )
    organization = RelationshipTo(
        'Organization',
        'PART_OF'
    )
    commune = RelationshipTo(
        'Commune',
        'LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY'
    )
    website = RelationshipTo(
        'Website',
        'OFFICIAL_WEBSITE'
    )
    division = RelationshipTo(
        'Effector',
        'HAS_DIVISION'
    )


class EffectorFacility(StructuredRel):
    """
    Location relationship between an Effector and a Facility. Includes relevant
    directory.
    """
    #TODO switch uid to UniqueIdProperty() when we upgrade neo4j to version 5
    uid = StringProperty(default=uuid4)
    directories = ArrayProperty(base_property=StringProperty())
    thirdPartyPayment = ArrayProperty(base_property=StringProperty())
    payment = ArrayProperty(base_property=StringProperty())
    contactUpdatedAt = IntegerProperty(default=0)
    active = BooleanProperty(
        index=True,
        default=True
    )
    carteVitale = BooleanProperty(
        index=True,
        default=None
    )


class Effector(StructuredNode):
    uid = UniqueIdProperty()
    label_en = StringProperty()
    label_fr = StringProperty()
    name_en = StringProperty()
    name_fr = StringProperty()
    slug_en = StringProperty(unique_index=True)
    slug_fr = StringProperty(unique_index=True)
    type = RelationshipTo('EffectorType', 'IS_A')
    organization = RelationshipTo('Organization', 'MEMBER_OF')
    facility = RelationshipTo(
        "Facility",
        "LOCATION",
        model = EffectorFacility
    )
    effector = RelationshipTo('Effector', 'PART_OF')
    commune = RelationshipTo(
        'Commune',
        'LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY'
    )
    convention = RelationshipTo(
        'Convention',
        'HAS_CONVENTION',
        cardinality=ZeroOrOne,
    )
    updatedAt = IntegerProperty(default=0)
    gender = StringProperty(
        choices=(("F","Feminine"), ("M","Masculine"),("N", "Neutral"))
    )

    @property
    def serialize(self):
        #language = get_language()
        #label=getattr(self, f'label_{language}', None)
        #name=getattr(self, f'name_{language}', None)
        return {
            'label': 'label',
            'name': 'name'
        }

    @property
    def types(self):
        language = get_language()
        logger.debug(f"{language=}")
        _types = []
        try:
            types_array = self.type.all()
        except Exception as e:
            logger.error(
                "\n**********************************************************\n"
                f"* {self.label_fr=} {e=} *\n"
                "**********************************************************\n")
            return []
        for _type in types_array:
            name=getattr(_type, f'concept_{language}', None)
            if not name:
                name=getattr(_type, f'name_{language}', None)
            if not name:
                name=getattr(_type, f'label_{language}', None)
            uid=getattr(_type, 'uid', None)
            _dict = {"name": name, "uid": uid}
            _types.append(_dict)
        logger.debug(f"{_types=}")
        return _types

    @property
    def communes(self):
        language = get_language()
        _communes = []
        for _facility in self.facility.all():
            try:
                _commune = _facility.commune[0]
            except:
                continue
            name=getattr(_commune, f'name_{language}', None)
            uid=getattr(_commune, 'uid', None)
            _dict = {"name": name, "uid": uid}
            _communes.append(_dict)
        return _communes


class CareHome(Effector):
    regular_permanent_bed = IntegerProperty(default=0)
    regular_temporary_bed = IntegerProperty(default=0)
    alzheimer_permanent_bed = IntegerProperty(
        default=0,
        help_text="Unité Alzheimer (unité de vie Alzheimer)",
    )
    alzheimer_temporary_bed = IntegerProperty(default=0)
    uvpha_permanent_bed = IntegerProperty(
        default=0,
        help_text="Unité de vie pour personnes handicapées âgées",
    )
    uhr_permanent_bed = IntegerProperty(
        default=0,
        help_text="Unité d’hébergement renforcée",
    )
    day_care = IntegerProperty(
        default=0,
        help_text="Accueil de jour",
    )
    usld_permanent_bed = IntegerProperty(
        default=0,
        help_text="Unité de soins de longue durée"
    )


class HealthWorker(Effector):
    rpps = StringProperty(
        unique_index=True,
        max_length=11
    )
    adeli = StringProperty(
        unique_index=True,
        max_length=9
    )
    spoken_languages = ArrayProperty(base_property=StringProperty())


class AdministrativeTerritorialEntityOfFrance(StructuredNode):
    uid = UniqueIdProperty()
    name_en = StringProperty(unique_index=False)
    name_fr = StringProperty(unique_index=False)
    slug_en = StringProperty(unique_index=False)
    slug_fr = StringProperty(unique_index=False)
    wikidata = StringProperty(unique_index=True)


class Commune(AdministrativeTerritorialEntityOfFrance):
    department = RelationshipTo(
        'DepartmentOfFrance',
        'LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY'
    )


class DepartmentOfFrance(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    code = StringProperty(unique_index=True)
    slug = StringProperty(unique_index=True)
    wikidata = StringProperty(unique_index=True)


class MunicipalArrondissement(AdministrativeTerritorialEntityOfFrance):
    commune = RelationshipTo('Commune', 'PART_OF')


class Facility(StructuredNode):
    uid = UniqueIdProperty()
    organization = RelationshipTo('Organization', 'PART_OF')
    commune = RelationshipTo(
        'Commune',
        'LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY'
    )
    contactUpdatedAt = IntegerProperty(default=0)
    name = StringProperty()
    label = StringProperty()
    slug = StringProperty()
    type = RelationshipTo('FacilityType', 'IS_A')
    effectors = RelationshipFrom(
        Effector,
        "LOCATION",
        model = EffectorFacility
    )


class FacilityType(StructuredNode):
    uid = UniqueIdProperty()
    label_fr = StringProperty(unique_index=True)
    label_en = StringProperty(unique_index=True)
    name_fr = StringProperty(unique_index=True)
    name_en = StringProperty(unique_index=True)
    slug_en = StringProperty(unique_index=True)
    slug_fr = StringProperty(unique_index=True)
    synonyms_fr = ArrayProperty(base_property=StringProperty())
    synonyms_en = ArrayProperty(base_property=StringProperty())
    definition_fr = StringProperty()
    definition_en = StringProperty()


class Entry(StructuredNode):
    uid = UniqueIdProperty()
    active = BooleanProperty(
        index=True,
        default=True
    )
    deactivation_datetime = DateTimeFormatProperty(format="%Y-%m-%dT%H:%M:%S.%fZ")
    deactivation_reason = StringProperty()
    updatedAt = IntegerProperty(default=0)
    contactUpdatedAt = IntegerProperty(default=0)
    effector = RelationshipTo('Effector', 'HAS_EFFECTOR')
    facility = RelationshipTo('Facility', 'HAS_FACILITY')
    effector_type = RelationshipTo('EffectorType', 'HAS_EFFECTOR_TYPE')


class Directory(StructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    entries = RelationshipTo('Entry', 'HAS_ENTRY')
    organization = RelationshipTo('Organization', 'OWNED_BY')
