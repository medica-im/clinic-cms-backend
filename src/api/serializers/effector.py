import logging
import time
from django.utils.text import slugify
from neomodel import db
from pydantic import ValidationError
from directory.models import (
    Directory,
    Facility,
    Organization,
    OrganizationType,
    Commune,
    Website,
    DepartmentOfFrance
)
from directory.models.agraph import (
    HealthWorker as AsyncHealthWorker,
    Effector as AsyncEffector,
    Directory as AsyncDirectory,
)
from api.types.effector import Effector, EffectorPost, EffectorPatch
from rest_framework import serializers
from adrf.serializers import Serializer
from langcodes import standardize_tag

logger = logging.getLogger(__name__)

def get_effector(
        effector_type: str|None = None,
        facility: str|None = None,
        directory: str|None = None,
        uid: str|None = None,
        active: bool = True,
    ) -> Effector:
    try:
        return get_effectors(
            effector_type=effector_type,
            facility=facility,
            directory=directory,
            uid=uid,
            active=active
        )[0]
    except Exception as e:
        logger.debug(e)
        raise Exception(e)

def get_effectors(
        effector_type: str|None = None,
        department_of_france: str|None = None,
        commune: str|None = None,
        facility: str|None = None,
        directory: str|None = None,
        uid: str|None = None,
        active: bool = True,
    )->list[Effector]:
    filter: list = []
    if effector_type:
        filter.append(f'et.uid="{effector_type}"')
    if facility:
        filter.append(f'f.uid="{facility}"')
    elif commune:
        filter.append(f'commune.uid="{commune}"')
    elif department_of_france:
        filter.append(f'dof.code="{department_of_france}"')
    if directory:
        filter.append(f'effector.creator_directory="{directory}"')
    if uid:
        query = (f"""MATCH (effector:Effector) WHERE effector.uid="{uid}" RETURN effector;""")
    elif not filter:
        query=(f"""MATCH (effector:Effector) RETURN effector;""")
    else:
        query=(f"""MATCH (entry:Entry)-[:HAS_FACILITY]->(f:Facility)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY
]->(commune:Commune)-[:LOCATED_IN_THE_ADMINISTRATIVE_TERRITORIAL_ENTITY
]->(dof:DepartmentOfFrance), (effector:Effector)<-[:HAS_EFFECTOR]-(entry)-[:HAS_EFFECTOR_TYPE]->(et:EffectorType) WHERE {" AND ".join(filter)} RETURN DISTINCT effector;""")
    q = db.cypher_query(query,resolve_objects = True)
    effectors: list[Effector]=[]
    if q:
        for row in q[0]:
            logger.debug(row)
            (
                effector,
            ) = row
            effector_dct=effector.__properties__
            try:
                e=Effector.model_validate(effector_dct)
                effectors.append(e)
            except ValidationError as e:
                logger.error(e)
    return effectors

async def create_effector(effector: EffectorPost, directory_name: str)->Effector:
    try:
        existing_effector = await AsyncEffector.nodes.get(
            name_fr=effector.name_fr,
            gender=effector.gender,
            slug_fr=effector.slug_fr,
        )
        ts = time.time()*1000
        if (ts - existing_effector.createdAt < 5000):
            effector_dct=existing_effector.__properties__
            _effector=Effector.model_validate(effector_dct)
            return _effector
    except:
        pass
    neo4j_directory = await AsyncDirectory.nodes.get(name=directory_name)
    node = await AsyncEffector(
        name_fr=effector.name_fr,
        label_fr=effector.label_fr or effector.name_fr,
        slug_fr=effector.slug_fr or slugify(effector.name_fr),
        gender=effector.gender,
        creator_directory=neo4j_directory.name,
    ).save()
    _effector = await AsyncEffector.nodes.get(uid=node.uid)
    effector_dct=_effector.__properties__
    new_effector=Effector.model_validate(effector_dct)
    logger.debug(new_effector)
    return new_effector


class EffectorSerializer(Serializer):
    spoken_languages = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_null=True
    )
    rpps = serializers.IntegerField(required=False, allow_null=True)
    name_fr = serializers.CharField(required=False, allow_null=False)
    label_fr = serializers.CharField(required=False, allow_null=True)
    slug_fr = serializers.CharField(required=False, allow_null=False)
    gender = serializers.CharField(required=False, allow_null=True)

    async def update(self, instance, validated_data):
        for attribute in validated_data.keys():
            logger.debug(f"{attribute=}")
            try:
                value = validated_data.get(attribute)
                setattr(instance, attribute, value)
            except validated_data.DoesNotExist:
                pass
        await instance.save()
        return instance


async def patch_effector(uid, kwargs)->Effector:
    logger.debug(f"{kwargs=}")
    hw=["rpps", "spoken_languages"]
    if (any(x in kwargs.keys() for x in hw)):
        node = await AsyncHealthWorker.nodes.get(uid=uid)
    else:
        node = await AsyncEffector.nodes.get(uid=uid)
    serializer = EffectorSerializer(node, data=kwargs, partial=True)
    if serializer.is_valid(raise_exception=True):
        node = await serializer.save()
    effector_dct=node.__properties__
    effector=Effector.model_validate(effector_dct)
    logger.debug(effector)
    return effector