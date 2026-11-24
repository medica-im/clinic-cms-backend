"""seed_peer_instances registers every deployment, this backend's own sites included.

One backend serves several sites: the dev backend answers for dev.santelyon3.fr,
dev.sante-gadagne.fr and the others, which share its database. Skipping each peer
whose host is one of those sites left the dev registry without a single dev peer,
so no dev site could clone from another. Which peer is "this instance" depends on
the request, not on the backend, and the clone page already hides it
(api.routers.clone.is_this_instance).
"""
import pytest
from django.contrib.sites.models import Site
from django.core.management import call_command

from directory.management.commands.seed_peer_instances import PEERS
from directory.models import PeerInstance

pytestmark = pytest.mark.django_db


def test_a_peer_on_one_of_this_backends_own_sites_is_registered():
    Site.objects.create(domain="dev.santelyon3.fr", name="Lyon 3 dev")
    Site.objects.create(domain="dev.sante-gadagne.fr", name="Gadagne dev")

    call_command("seed_peer_instances", "--write")

    names = set(PeerInstance.objects.values_list("name", flat=True))
    assert {"santelyon3-dev", "sante-gadagne-dev"} <= names
    assert names == {name for name, *_ in PEERS}
