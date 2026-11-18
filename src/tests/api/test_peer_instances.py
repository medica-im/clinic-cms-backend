"""The peer registry: which deployments a superuser may clone from.

A row here is a trust decision — it says a superuser may pull entries from that
server, and (via `inbound`) whether that server may pull from this one. The
validator and the direction flags are what keep that decision narrow, so they
are asserted rather than assumed.
"""
import pytest
from django.core.exceptions import ValidationError

from directory.models import PeerInstance

pytestmark = pytest.mark.django_db


def peer(**over):
    kwargs = dict(name="a-peer", display_name="A peer",
                  origin="https://peer.example", active=True,
                  outbound=True, inbound=True)
    kwargs.update(over)
    return PeerInstance(**kwargs)


class TestTheOriginIsAnOrigin:
    def test_https_is_required(self):
        """The export carries phone numbers and emails between servers.

        Over plain http they would be on the wire in clear.
        """
        with pytest.raises(ValidationError):
            peer(origin="http://peer.example").full_clean()

    def test_a_path_is_refused(self):
        """The clone code appends its own paths.

        An origin carrying one would produce URLs nobody wrote.
        """
        with pytest.raises(ValidationError):
            peer(origin="https://peer.example/annuaire").full_clean()

    def test_credentials_are_refused(self):
        with pytest.raises(ValidationError):
            peer(origin="https://user:pw@peer.example").full_clean()

    def test_a_bare_origin_is_accepted(self):
        peer(origin="https://peer.example").full_clean()
        peer(origin="https://peer.example/").full_clean()


class TestDirectionIsNotSymmetric:
    def test_a_production_peer_is_readable_but_not_a_reader(self):
        """What seed_peer_instances writes for production.

        Cloning runs production → staging → dev; a production server has no
        business pulling from a development box.
        """
        p = peer(name="prod", origin="https://prod.example", outbound=True, inbound=False)
        p.full_clean()
        p.save()
        assert PeerInstance.objects.get(name="prod").outbound is True
        assert PeerInstance.objects.get(name="prod").inbound is False

    def test_the_registry_can_refuse_a_peer_without_deleting_it(self):
        """`active` is the flip-a-row control, and it has to survive a round trip."""
        p = peer(name="retired", origin="https://retired.example", active=False)
        p.full_clean()
        p.save()
        assert not PeerInstance.objects.filter(active=True, name="retired").exists()
