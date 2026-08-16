import os
import pytest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")


# ---------------------------------------------------------------------------
# Fake neomodel node helpers
# ---------------------------------------------------------------------------

class FakeNode:
    DoesNotExist = type("DoesNotExist", (Exception,), {})

    def __init__(self, **props):
        self.__properties__ = props
        for k, v in props.items():
            setattr(self, k, v)

    async def save(self):
        return self

    async def delete(self):
        pass

    async def labels(self):
        return getattr(self, "_labels", ["Appointment"])


class FakeRelationship:
    def __init__(self, nodes=None):
        self._nodes = nodes or []

    async def all(self):
        return self._nodes

    async def single(self):
        if self._nodes:
            return self._nodes[0]
        raise Exception("No related node")

    async def connect(self, node):
        self._nodes.append(node)

    async def disconnect(self, node):
        self._nodes = [n for n in self._nodes if n is not node]


class FakeNodeManager:
    def __init__(self, nodes=None):
        self._nodes = {n.uid: n for n in (nodes or [])}

    async def get(self, **kwargs):
        uid = kwargs.get("uid")
        if uid and uid in self._nodes:
            return self._nodes[uid]
        raise FakeNode.DoesNotExist()

    async def all(self):
        return list(self._nodes.values())


# ---------------------------------------------------------------------------
# Django DB fixtures (AccessControl, Roles, Endpoints)
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "no_db: this test asserts pure logic and must run without a database",
    )


@pytest.fixture(autouse=True)
def roles(request):
    # Autouse, so every test in this directory gets a database whether it needs
    # one or not. Tests that assert pure logic — which constant wins, what a
    # value means — should not need postgres to run: a rule that can only be
    # checked against a live server is a rule nobody checks. Mark those with
    # @pytest.mark.no_db and neither this fixture nor the database is set up.
    if request.node.get_closest_marker("no_db"):
        return {}

    request.getfixturevalue("transactional_db")
    from access.models import Role
    result = {}
    for name in ("superuser", "administrator", "staff", "registered", "anonymous"):
        result[name], _ = Role.objects.get_or_create(name=name)
    return result


@pytest.fixture
def site(transactional_db):
    from django.contrib.sites.models import Site
    site, _ = Site.objects.get_or_create(
        domain="testserver",
        defaults={"name": "Test Site"},
    )
    return site


@pytest.fixture
def appointments_acl(transactional_db, roles):
    """AccessControl for the appointments_v2 endpoint.

    Permissions (bitmask): GET=1, POST=2, PUT=4, DELETE=8
    superuser=15 (all), administrator=15 (all), staff=1 (read only),
    anonymous/registered have no ACL row → denied.
    """
    from access.models import Endpoint, AccessControl
    endpoint, _ = Endpoint.objects.get_or_create(name="appointments_v2")
    acls = {}
    permissions = {
        "superuser": 15,
        "administrator": 15,
        "staff": 1,
    }
    for role_name, perm in permissions.items():
        acl, _ = AccessControl.objects.get_or_create(
            endpoint=endpoint,
            role=roles[role_name],
            defaults={"permissions": perm},
        )
        acls[role_name] = acl
    return acls


# ---------------------------------------------------------------------------
# JWT fixtures per role
# ---------------------------------------------------------------------------

def _make_jwt(role_name: str, sub: str = "test-sub") -> dict:
    return {
        "email": f"{role_name}@example.com",
        # The auth code reads providerAccountId; `sub` is the same value under
        # the name a test uses when it seeds the caller's own Account, so a
        # test can say "this user is me" without knowing which key the JWT
        # happens to use.
        "providerAccountId": sub,
        "sub": sub,
        "name": f"Test {role_name.title()}",
    }


@pytest.fixture
def jwt_anonymous():
    return None


@pytest.fixture
def jwt_owner():
    return _make_jwt("owner", sub="owner-sub-001")


@pytest.fixture
def jwt_staff():
    return _make_jwt("staff", sub="staff-sub-001")


@pytest.fixture
def jwt_registered():
    return _make_jwt("registered", sub="registered-sub-001")


@pytest.fixture
def jwt_administrator():
    return _make_jwt("administrator", sub="admin-sub-001")


@pytest.fixture
def jwt_superuser():
    return _make_jwt("superuser", sub="super-sub-001")


# ---------------------------------------------------------------------------
# Neo4j auth mock: controls what role get_neo4j_role returns
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_get_site(site):
    """Patch get_site_from_request in api.auth to return the test site."""
    return patch(
        "api.auth.get_site_from_request",
        new_callable=AsyncMock,
        return_value=site,
    )


@pytest.fixture
def mock_neo4j_role():
    """Returns a context manager that patches get_neo4j_role to return a given role.

    Usage:
        with mock_neo4j_role("staff"):
            response = await client.post(...)
    """
    from contextlib import contextmanager

    @contextmanager
    def _mock(role_name: str | None):
        with patch(
            "api.auth.get_neo4j_role",
            new_callable=AsyncMock,
            return_value=role_name,
        ):
            yield

    return _mock


# ---------------------------------------------------------------------------
# Shared fake nodes
# ---------------------------------------------------------------------------

@pytest.fixture
def owner_user():
    user = FakeNode(uid="owner-uid-001", email="owner@example.com")
    accounts = FakeRelationship([FakeNode(sub="owner-sub-001")])
    user.accounts = accounts
    return user


@pytest.fixture
def fake_entry(owner_user):
    entry = FakeNode(uid="entry-uid-001", name="Test Entry")
    entry.owner = FakeRelationship([owner_user])
    entry.creator = FakeRelationship([])
    entry.appointments = FakeRelationship([])
    entry.tags = FakeRelationship([])
    return entry


@pytest.fixture
def fake_appointment(fake_entry):
    appt = FakeNode(
        uid="appt-uid-001",
        url="https://rdv.example.com",
        phone=None,
        _labels=["Appointment", "Office"],
    )
    appt.entry = FakeRelationship([fake_entry])
    return appt
