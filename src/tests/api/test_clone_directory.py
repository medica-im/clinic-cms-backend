"""Cloning names the directory it reads from and writes into.

A site may have several directories: staging.santelyon3.fr has its own, santelyon3,
and the santé mentale directory, cpts-lyon-3-sante-mentale. The clone knew only the
first, so the santé mentale entries could neither be listed on the source nor land
in their directory on the target. A clone now names one; the same name on both
sides, since dev, staging and production of one site share their directory names.

A name is accepted only when it is one of the requesting site's directories: a token
scoped to another site's directory, or a write into one, is a 404 like any unknown
name. Without a name, the site's own directory, as before.
"""
import pytest
from asgiref.sync import sync_to_async
from django.contrib.sites.models import Site
from fastapi import HTTPException

from api.routers.clone import directory_of_site
from directory.models import Directory

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def sites():
    lyon = Site.objects.create(domain="clone-lyon.test", name="Lyon")
    other = Site.objects.create(domain="clone-other.test", name="Other")
    Directory.objects.create(name="clone-lyon-main", display_name="Lyon", presentation="", site=lyon)
    Directory.objects.create(name="clone-lyon-sante-mentale", display_name="Santé mentale", presentation="", site=lyon)
    Directory.objects.create(name="clone-other-main", display_name="Other", presentation="", site=other)
    return {"lyon": lyon, "other": other}


async def test_a_directory_of_the_site_is_the_one_used(sites):
    directory = await directory_of_site(sites["lyon"], "clone-lyon-sante-mentale")
    assert directory.name == "clone-lyon-sante-mentale"


@pytest.mark.parametrize("name", ["clone-other-main", "no-such-directory"])
async def test_another_sites_directory_or_an_unknown_one_is_not_found(sites, name):
    with pytest.raises(HTTPException) as refused:
        await directory_of_site(sites["lyon"], name)
    assert refused.value.status_code == 404
