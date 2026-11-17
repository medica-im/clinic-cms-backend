"""The clone page offers every peer but the instance it is on.

The route hid a peer when this instance's hostname appeared anywhere in the peer's
origin, so on santelyon3.fr « Santé Lyon 3 (dev) » (https://dev.santelyon3.fr) and its
staging were both hidden: `"santelyon3.fr" in "https://dev.santelyon3.fr"`. The same
happened on annuaire.medica.im to every annuaire peer. Only the instance itself is
hidden: its hostname is the peer's hostname, not a part of it.
"""
import pytest

from api.routers.clone import is_this_instance


@pytest.mark.parametrize("origin", [
    "https://santelyon3.fr",
    "https://santelyon3.fr/",
    "https://santelyon3.fr/annuaire",
    "https://SanteLyon3.fr",
    "https://santelyon3.fr:443",
])
def test_the_instance_itself_is_hidden(origin):
    assert is_this_instance(origin, "santelyon3.fr")


@pytest.mark.parametrize("origin", [
    "https://dev.santelyon3.fr",
    "https://staging.santelyon3.fr",
    "https://santelyon3.fr.example.org",
    "https://notsantelyon3.fr",
])
def test_a_peer_whose_hostname_contains_this_one_is_offered(origin):
    assert not is_this_instance(origin, "santelyon3.fr")


@pytest.mark.parametrize("origin, here", [
    ("", "santelyon3.fr"),
    (None, "santelyon3.fr"),
    ("https://dev.santelyon3.fr", ""),
    ("https://dev.santelyon3.fr", None),
])
def test_what_cannot_be_compared_is_not_hidden(origin, here):
    assert not is_this_instance(origin, here)
