from directory.models.agraph import Tag, TagCategory, Entry
from api.types.tag import TagCategory as TagCategoryPy, Tag as TagPy, TagEntry
from api.utils import clear_cache
from rest_framework import serializers
from fastapi import HTTPException, Request
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
            "category": instance.tag_category,
        }

class TagCategorySerializer(serializers.BaseSerializer):
    def to_representation(self, instance):
        return {
            "uid": instance.uid,
            "name": instance.name,
            "label": instance.label,
            "labelShort": instance.labelShort,
            "synonyms": instance.synonyms,
            "definition": instance.definition,
            "effector_types": instance.effector_type
        }

async def tag_categories()->list[TagCategoryPy]:
    tag_categories = await TagCategory.nodes.all()
    _tagcats = []
    for t in tag_categories:
        ets = await t.effector_type.all()
        uids=[et.uid for et in ets]
        t.effector_type=uids
        _tagcats.append(t)
    serializer=TagCategorySerializer(tag_categories, many=True)
    ta = TypeAdapter(list[TagCategoryPy])
    return ta.validate_python(serializer.data)

async def tag_category(uid: str)->TagCategoryPy:
    tag_categories = await TagCategory.nodes.get(uid=uid)
    serializer=TagCategorySerializer(tag_categories)
    return TagCategoryPy.model_validate(serializer.data)

async def tags(category: str|None)->list[TagPy]:
    if not category:
        tags = await Tag.nodes.all()
        for idx, item in enumerate(tags):
            category_nodes = await item.tag_category.all()
            category_node = category_nodes[0]
            uid = category_node.uid
            item.tag_category = uid
            tags[idx] = item
    else:
        try:
            category_node = await TagCategory.nodes.get(name=category)
        except Exception as e:
            logger.error(e)
            raise Exception(e)
        tags = await category_node.tags.all()
        for idx, item in enumerate(tags):
            item.tag_category = category_node.uid
            tags[idx] = item
    serializer=TagSerializer(tags, many=True)
    ta = TypeAdapter(list[TagPy] or None)
    return ta.validate_python(serializer.data or None)

async def update_tags(item: TagEntry, request: Request):
    try:
        entry = await Entry.nodes.get(uid=item.entry)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail=f"Entry {item.entry} not found")
    addTags = []
    try:
        for t in item.addTags:
            try:
                tag = await Tag.nodes.get(uid=t)
                addTags.append(tag)
            except Exception as e:
                logger.error(e)
                raise HTTPException(status_code=404, detail=f"Tag {t} not found")
    except TypeError:
        pass
    for tag in addTags:
        await entry.tags.connect(tag)
    removeTags = []
    try:
        for t in item.removeTags:
            try:
                tag = await Tag.nodes.get(uid=t)
                removeTags.append(tag)
            except Exception as e:
                logger.error(e)
                raise HTTPException(status_code=404, detail=f"Tag {t} not found")
    except TypeError:
        pass
    for tag in removeTags:
        await entry.tags.disconnect(tag)
    if addTags or removeTags:
        await clear_cache("v2:entries", request)

