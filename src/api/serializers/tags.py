from directory.models.agraph import Tag, TagCategory
from api.types.tag import TagCategory as TagCategoryPy
from rest_framework import serializers
from fastapi import HTTPException
from pydantic import TypeAdapter
import logging

logger=logging.getLogger(__name__)

class TagSerializer(serializers.BaseSerializer):
    def to_representation(self, instance):
        category=None
        try:
            category = instance.tag_category.all()[0]
        except Exception as e:
            logger.error(e)
            raise Exception(e)
        return {
            "uid": instance.uid,
            "name": instance.name,
            "label": instance.label,
            "labelShort": instance.labelShort,
            "category": category.name,
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
