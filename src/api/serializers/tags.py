from directory.models.agraph import Tag, TagCategory
from api.types.tag import TagCategory as TagCategoryPy, Tag as TagPy
from rest_framework import serializers
from fastapi import HTTPException
from pydantic import TypeAdapter
import logging

logger=logging.getLogger(__name__)

class TagSerializer(serializers.BaseSerializer):
    def to_representation(self, instance):
        return {
            "uid": instance.uid,
            "name": instance.name,
            "label": instance.label,
            "labelShort": instance.labelShort,
            "synonyms": instance.synonyms,
            "definition": instance.definition,
        }

class TagCategorySerializer(serializers.BaseSerializer):
    def to_representation(self, instance):
        effector_types=None
        try:
            effector_types=[_type.uid for _type in instance.effector_type.all()]
        except Exception as e:
            logger.error(e)
            effector_types=None
        return {
            "uid": instance.uid,
            "name": instance.name,
            "label": instance.label,
            "labelShort": instance.labelShort,
            "synonyms": instance.synonyms,
            "definition": instance.definition,
            "effector_types": effector_types
        }

async def tag_categories()->list[TagCategoryPy]:
    tag_categories = await TagCategory.nodes.all()
    serializer=TagCategorySerializer(tag_categories, many=True)
    ta = TypeAdapter(list[TagCategoryPy])
    return ta.validate_python(serializer.data)

async def tag_category(uid: str)->TagCategoryPy:
    tag_categories = await TagCategory.nodes.get(uid=uid)
    serializer=TagCategorySerializer(tag_categories)
    return TagCategoryPy.model_validate(serializer.data)

async def tags()->list[TagPy]:
    tags = await Tag.nodes.all()
    serializer=TagSerializer(tags, many=True)
    ta = TypeAdapter(list[TagPy])
    return ta.validate_python(serializer.data)
