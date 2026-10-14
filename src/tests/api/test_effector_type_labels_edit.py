"""Editing an effector type's labels from the web UI.

    GET /api/v2/effector-types/{uid}/labels
    PUT /api/v2/effector-types/{uid}/labels

The body is the type's whole label set, every language, number and gender,
null where no word is authored: {"fr": {"S": {"F", "M", "N"}, "P": {...}},
"en": {...}}. A PUT replaces the set, so a slot left empty is a word removed.

Gated by the `effector-types` endpoint like the rest of the type's editing:
superuser only, in practice.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from asgiref.sync import sync_to_async
from fastapi import HTTPException

pytestmark = [pytest.mark.asyncio]

UID = uuid.uuid4().hex
URL = f"/api/v2/effector-types/{UID}/labels"

EMPTY = {"S": {"F": None, "M": None, "N": None}, "P": {"F": None, "M": None, "N": None}}
OSTEOPATH = {
    "fr": {
        "S": {"F": "ostéopathe", "M": "ostéopathe", "N": "ostéopathe"},
        "P": {"F": "ostéopathes", "M": "ostéopathes", "N": "ostéopathes"},
    },
    "en": {
        "S": {"F": None, "M": None, "N": "osteopath"},
        "P": {"F": None, "M": None, "N": "osteopaths"},
    },
}


@pytest.fixture
def genders(transactional_db):
    from accounts.models import GrammaticalGender

    for name, code in {"feminine": "F", "masculine": "M", "neutral": "N"}.items():
        GrammaticalGender.objects.get_or_create(code=code, defaults={"name": name, "label": name})


@pytest.fixture
def authorize():
    with patch("api.routers.effector_type_labels.authorize_api", AsyncMock(return_value=True)) as mock:
        yield mock


@pytest.fixture
def known_type():
    with patch("api.routers.effector_type_labels.effector_type_exists", AsyncMock(return_value=True)):
        yield


@pytest.fixture
def cleared():
    calls: list[str] = []
    with patch(
        "api.routers.effector_type_labels.sync_clear_cache",
        lambda endpoint, **_: calls.append(endpoint),
    ):
        yield calls


@pytest.fixture
def editing(versioned_client, patch_jwt, genders, authorize, known_type, cleared):
    with patch_jwt({"sub": "superuser"}):
        yield versioned_client


@sync_to_async
def rows() -> list[tuple[str, str, str, list[str]]]:
    from directory.models.core import Label

    return sorted(
        (r.language, r.grammatical_number, r.label, sorted(r.gender.values_list("code", flat=True)))
        for r in Label.objects.filter(uid=UID, term_type="name")
    )


class TestReading:
    async def test_a_type_without_labels_answers_every_slot_empty(self, editing):
        response = await editing.get(URL)

        assert response.status_code == 200
        assert response.json() == {"fr": EMPTY, "en": EMPTY}

    async def test_what_was_saved_is_what_is_read(self, editing):
        await editing.put(URL, json=OSTEOPATH)

        assert (await editing.get(URL)).json() == OSTEOPATH


class TestSaving:
    async def test_it_answers_the_saved_labels(self, editing):
        response = await editing.put(URL, json=OSTEOPATH)

        assert response.status_code == 200
        assert response.json() == OSTEOPATH

    async def test_one_word_for_several_genders_is_one_row(self, editing):
        await editing.put(URL, json=OSTEOPATH)

        assert await rows() == [
            ("en", "P", "osteopaths", ["N"]),
            ("en", "S", "osteopath", ["N"]),
            ("fr", "P", "ostéopathes", ["F", "M", "N"]),
            ("fr", "S", "ostéopathe", ["F", "M", "N"]),
        ]

    async def test_a_slot_emptied_is_a_word_removed(self, editing):
        await editing.put(URL, json=OSTEOPATH)

        await editing.put(URL, json={"fr": OSTEOPATH["fr"], "en": EMPTY})

        assert [r for r in await rows() if r[0] == "en"] == []

    async def test_blank_text_counts_as_empty(self, editing):
        body = {"fr": {"S": {"F": "  ", "M": " secrétaire médical ", "N": ""}, "P": EMPTY["P"]}, "en": EMPTY}

        await editing.put(URL, json=body)

        assert await rows() == [("fr", "S", "secrétaire médical", ["M"])]

    async def test_the_sites_see_the_new_labels(self, editing):
        from api.serializers.effector_type_labels import get_effector_type_labels

        await editing.put(URL, json=OSTEOPATH)

        assert (await get_effector_type_labels("fr")).model_dump()[UID] == OSTEOPATH["fr"]

    async def test_it_clears_both_label_caches(self, editing, cleared):
        await editing.put(URL, json=OSTEOPATH)

        assert set(cleared) == {"v1:effector_type_labels", "v2:effector-type-labels"}


class TestRefusals:
    async def test_an_unknown_type_is_not_found(self, editing):
        with patch("api.routers.effector_type_labels.effector_type_exists", AsyncMock(return_value=False)):
            response = await editing.put(URL, json=OSTEOPATH)

        assert response.status_code == 404
        assert await rows() == []

    async def test_a_caller_without_the_right_writes_nothing(self, editing, authorize):
        authorize.side_effect = HTTPException(status_code=403, detail="Insufficient permissions")

        response = await editing.put(URL, json=OSTEOPATH)

        assert response.status_code == 403
        assert await rows() == []

    async def test_it_is_gated_by_the_effector_types_endpoint(self, editing, authorize):
        await editing.put(URL, json=OSTEOPATH)

        assert authorize.await_args.args[0] == "effector-types"

    async def test_a_language_the_labels_do_not_know_is_refused(self, editing):
        response = await editing.put(URL, json={**OSTEOPATH, "de": EMPTY})

        assert response.status_code == 422
