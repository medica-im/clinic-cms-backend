"""A single contact-related object (a profile) reaches its serializer as itself.

The helper gathered every contact's results into a set, the way it gathers
phones and emails, and handed that set to the serializer even when asked for
one object. The serializer then read `.contact` off a set, and every entry with
a profile answered 500 on /api/v2/fullentries — the first was msp-vedene's.
"""
import pytest

from directory import utils


class Echo:
    def __init__(self, instance, many=False):
        assert not isinstance(instance, (set, list)), "given a collection, not the object"
        self.data = {"seen": instance}


class Node:
    def __init__(self, uid):
        self.uid = uid


@pytest.fixture
def profiles(monkeypatch):
    """Contacts by node uid: the entry has none, the effector and facility do."""
    found = {"effector": "effector's profile", "facility": "facility's profile"}

    async def fake(neo_entity, attribute, many):
        return found.get(neo_entity.uid) if neo_entity else None

    def fake_sync(neo_entity, attribute, many):
        return found.get(neo_entity.uid) if neo_entity else None

    monkeypatch.setattr(utils, "async_get_contact_related_elements", fake)
    monkeypatch.setattr(utils, "get_contact_related_elements", fake_sync)


NODES = dict(entry=Node("entry"), e=Node("effector"), ef=None, f=Node("facility"))


async def test_the_first_contact_with_one_wins(profiles):
    data = await utils.async_get_contact_related_neomodel(
        **NODES, attribute="profile", Serializer=Echo, many=False
    )
    assert data == {"seen": "effector's profile"}


def test_the_sync_helper_agrees(profiles):
    data = utils.get_contact_related_neomodel(
        **NODES, attribute="profile", Serializer=Echo, many=False
    )
    assert data == {"seen": "effector's profile"}


async def test_none_when_no_contact_has_one(monkeypatch):
    async def nothing(neo_entity, attribute, many):
        return None

    monkeypatch.setattr(utils, "async_get_contact_related_elements", nothing)
    data = await utils.async_get_contact_related_neomodel(
        **NODES, attribute="profile", Serializer=Echo, many=False
    )
    assert data is None
