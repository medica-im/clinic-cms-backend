import logging
from uuid import uuid4
from neomodel.contrib import spatial_properties as neomodel_spatial
from neomodel import (
    config,
    AsyncStructuredNode,
    BooleanProperty,
    StringProperty,
    IntegerProperty,
    DateTimeFormatProperty,
    UniqueIdProperty,
    ArrayProperty,
    AsyncRelationshipTo,
    AsyncRelationshipFrom,
    AsyncRelationship,
    AsyncStructuredRel,
    AsyncZeroOrOne,
    OneOrMore,
    AsyncOne,
)
from django.utils.translation import get_language

logger=logging.getLogger(__name__)

class PaymentMethod(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    label_fr = StringProperty()
    label_en = StringProperty()
    definition_fr = StringProperty()
    definition_en = StringProperty()


class ThirdPartyPayer(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    label_fr = StringProperty()
    label_en = StringProperty()
    definition_fr = StringProperty()
    definition_en = StringProperty()


class Convention(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    label = StringProperty()
    definition = StringProperty()


class Need(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name_fr = StringProperty(unique_index=True)
    name_en = StringProperty(unique_index=True)
    definition_fr = StringProperty()
    definition_en = StringProperty()
    need = AsyncRelationshipTo('Need', 'PART_OF')


class EffectorType(AsyncStructuredNode):
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
    need = AsyncRelationshipTo('Need', 'MANAGES')
    situation = AsyncRelationshipTo('Situation', 'MANAGES')
    effector_type = AsyncRelationshipTo(
        'EffectorType',
        'IS_A'
    )


class HCW(EffectorType):
    concept_en = StringProperty(unique_index=True)
    concept_fr = StringProperty(unique_index=True)
    unique_ID = StringProperty(unique_index=True)
    hcw = AsyncRelationshipTo('HCW', 'IS_A')


class MESH(AsyncStructuredNode):
    uid = UniqueIdProperty()
    label_fr = StringProperty(unique_index=True)
    label_en = StringProperty(unique_index=True)
    definition_en = StringProperty()
    definition_fr = StringProperty()
    concept_en = StringProperty(unique_index=True)
    concept_fr = StringProperty(unique_index=True)
    unique_ID = StringProperty(unique_index=True)
    is_a = AsyncRelationshipTo('MESH', 'IS_A')
    need = AsyncRelationshipTo('Need', 'MANAGES')
    situation = AsyncRelationshipTo('Situation', 'MANAGES')


class Situation(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name_en = StringProperty(unique_index=True)
    name_fr = StringProperty(unique_index=True)
    definition_en = StringProperty()
    definition_fr = StringProperty()
    ICD_11 = ArrayProperty(StringProperty())
    impacts_need = AsyncRelationshipTo('Need', 'IMPACTS')


class OrganizationType(AsyncStructuredNode):
    uid = UniqueIdProperty()
    label_en = StringProperty(unique_index=True)
    label_fr = StringProperty(unique_index=True)
    name_en = StringProperty(unique_index=True)
    name_fr = StringProperty(unique_index=True)
    synonyms_fr = ArrayProperty(base_property=StringProperty())
    synonyms_en = ArrayProperty(base_property=StringProperty())
    organization_type = AsyncRelationshipTo(
        'OrganizationType',
        'PART_OF'
    )


class Website(AsyncStructuredNode):
    uid = UniqueIdProperty()
    url = StringProperty(unique_index=True)


class Organization(AsyncStructuredNode):
    uid = UniqueIdProperty()
    label_en = StringProperty(unique_index=True)
    label_fr = StringProperty(unique_index=True)
    name_en = StringProperty(unique_index=True)
    name_fr = StringProperty(unique_index=True)
    type = AsyncRelationshipTo(
        'OrganizationType',
        'IS_A'
    )
    organization = AsyncRelationshipTo(
        'Organization',
        'PART_OF'
    )
    commune = AsyncRelationshipTo(
        'Commune',
        'LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY',
        cardinality=AsyncOne
    )
    website = AsyncRelationshipTo(
        'Website',
        'OFFICIAL_WEBSITE'
    )
    division = AsyncRelationshipTo(
        'Effector',
        'HAS_DIVISION'
    )


class EffectorFacility(AsyncStructuredRel):
    """
    Location relationship between an Effector and a Facility. Includes relevant
    directory.
    """
    #TODO switch uid to UniqueIdProperty() when we upgrade neo4j to version 5
    uid = StringProperty(default=uuid4)
    directories = ArrayProperty(base_property=StringProperty())
    thirdPartyPayment = ArrayProperty(base_property=StringProperty())
    contactUpdatedAt = IntegerProperty(default=0)
    active = BooleanProperty(
        index=True,
        default=True
    )
    carteVitale = BooleanProperty(
        index=True,
        default=None
    )


class Effector(AsyncStructuredNode):
    uid = UniqueIdProperty()
    label_en = StringProperty()
    label_fr = StringProperty()
    name_en = StringProperty()
    name_fr = StringProperty()
    slug_en = StringProperty()
    slug_fr = StringProperty()
    type = AsyncRelationshipTo('EffectorType', 'IS_A')
    organization = AsyncRelationshipTo('Organization', 'MEMBER_OF')
    facility = AsyncRelationshipTo(
        "Facility",
        "LOCATION",
        model = EffectorFacility
    )
    effector = AsyncRelationshipTo('Effector', 'PART_OF')
    #commune = RelationshipTo(
    #    'Commune',
    #    'LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY'
    #)
    updatedAt = IntegerProperty(default=0)
    createdAt = IntegerProperty(default=0)
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
            logger.error(f"{self.label_fr=} {e=}")
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
    spoken_languages = ArrayProperty(base_property=StringProperty())


class AdministrativeTerritorialEntityOfFrance(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name_en = StringProperty(unique_index=False)
    name_fr = StringProperty(unique_index=False)
    slug_en = StringProperty(unique_index=False)
    slug_fr = StringProperty(unique_index=False)
    wikidata = StringProperty(unique_index=True)


class Commune(AdministrativeTerritorialEntityOfFrance):
    department = AsyncRelationshipTo(
        'DepartmentOfFrance',
        'LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY'
    )


class DepartmentOfFrance(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    code = StringProperty(unique_index=True)
    slug = StringProperty(unique_index=True)
    wikidata = StringProperty(unique_index=True)
    region = AsyncRelationshipTo(
        'RegionOfFrance',
        'LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY'
    )


class RegionOfFrance(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    code = StringProperty(unique_index=True)
    slug = StringProperty(unique_index=True)
    country = AsyncRelationshipTo(
        'Country',
        'LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY'
    )


class Country(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    code = StringProperty(unique_index=True)
    slug = StringProperty(unique_index=True)


class MunicipalArrondissement(AdministrativeTerritorialEntityOfFrance):
    commune = AsyncRelationshipTo('Commune', 'PART_OF')


class Facility(AsyncStructuredNode):
    uid = UniqueIdProperty()
    organization = AsyncRelationshipTo('Organization', 'PART_OF')
    commune = AsyncRelationshipTo(
        'Commune',
        'LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY'
    )
    contactUpdatedAt = IntegerProperty(default=0)
    updated = IntegerProperty(default=0)
    name = StringProperty()
    label = StringProperty()
    slug = StringProperty()
    location = neomodel_spatial.PointProperty(crs='wgs-84')
    entries = AsyncRelationshipFrom(
        'Entry',
        "HAS_FACILITY"
    )
    zoom = IntegerProperty(default=18)
    building = StringProperty()
    street = StringProperty()
    geographical_complement = StringProperty()
    zip = StringProperty()
    tooltip_permanent = BooleanProperty()
    tooltip_text = StringProperty()
    DIRECTIONS = {'top': 'Top', 'bottom': 'Bottom', 'left': 'Left', 'right': 'Right'}
    tooltip_direction = StringProperty(choices=DIRECTIONS)
    ban_id = StringProperty()
    ban_banId = StringProperty()


class Entry(AsyncStructuredNode):
    uid = UniqueIdProperty()
    active = BooleanProperty(
        index=True,
        default=True
    )
    deactivation_datetime = DateTimeFormatProperty(format="%Y-%m-%dT%H:%M:%S.%fZ")
    deactivation_reason = StringProperty()
    updatedAt = IntegerProperty(default=0)
    contactUpdatedAt = IntegerProperty(default=0)
    effector = AsyncRelationshipTo('Effector', 'HAS_EFFECTOR')
    facility = AsyncRelationshipTo('Facility', 'HAS_FACILITY')
    effector_type = AsyncRelationshipTo('EffectorType', 'HAS_EFFECTOR_TYPE')
    organizations = AsyncRelationshipTo('Organization', 'MEMBER_OF')
    memberships = AsyncRelationshipTo('Entry', 'MEMBER_OF')
    carte_vitale = BooleanProperty(
        index=True,
        default=None
    )
    payment = ArrayProperty(base_property=StringProperty())
    third_party_payer = ArrayProperty(base_property=StringProperty())
    convention = StringProperty()
    appointments = AsyncRelationshipTo('Appointment', 'HAS_APPOINTMENT') 


class Directory(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)
    entries = AsyncRelationshipTo('Entry', 'HAS_ENTRY')
    organization = AsyncRelationshipTo('Organization', 'OWNED_BY')
    owner = AsyncRelationshipTo('Entry', 'OWNED_BY')


class Monkey(AsyncStructuredNode):
    uid = UniqueIdProperty()
    name = StringProperty(unique_index=True)


class Appointment(AsyncStructuredNode):
    uid = UniqueIdProperty()
    url = StringProperty()
    phone = StringProperty()


class Office(Appointment):
    pass


class HouseCall(Appointment):
    pass