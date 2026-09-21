"""Whether an invited person is recognised when they first sign in.

An administrator invited cabinet.duponchelle@gmail.com on unipa.fr and the
invitee was not recognised on sign-in. Nothing covered this path, which is how
it shipped: there were tests for creating and listing invitations, and none for
redeeming one.

Recognition is `_find_invitee`, reached from `/users/me` via
`get_or_create_neo4j_user`. Its query demands four things at once:

    MATCH (i:Invitee {active: true})-[:INVITED_TO]->(e:Entry {uid: $entry_uid})
    WHERE toLower(i.email) = toLower($email) AND i.redeemedAt IS NULL

so the invitee must be active, joined to the Entry by INVITED_TO, not already
redeemed, and matched on email. Miss any one and the caller falls through to
"no invitee" — which for a non-sandbox site means `/users/me` answers 403 and
the app simply does not know them. One failure mode, four causes, and no error
naming which.

`entry_uid` is the organisation's Entry **for the site the request resolved
to**, via `Organization.objects.aget(site=site)` — so an invitation created
against one site and redeemed against another cannot match. That was the first
suspicion here, since unipa.fr/annuaire is served by ipa.medica.im. It is NOT
the cause: both hostnames resolve to the same organisation (uid
3eb0102947274deb9e01cd5c5517173b, checked against both origins), so entry_uid
is identical either way. The tests below keep that pinned anyway, because it is
the failure a future hostname change would reintroduce and it looks exactly
like this one.
"""
import pytest
from api.neo4j_auth import _find_invitee

pytestmark = pytest.mark.asyncio

ENTRY_UID = "3eb0102947274deb9e01cd5c5517173b"
OTHER_ENTRY_UID = "ffffffffffffffffffffffffffffffff"
EMAIL = "cabinet.duponchelle@gmail.com"


async def _invite(adb, *, email=EMAIL, entry_uid=ENTRY_UID, active=True,
                  redeemed_at=None, linked=True):
    """One Invitee, optionally joined to an Entry, as the API creates it."""
    await adb.cypher_query(
        "MERGE (e:Entry {uid: $entry_uid})", {"entry_uid": entry_uid}
    )
    await adb.cypher_query(
        """
        CREATE (i:Invitee {uid: $uid, email: $email, active: $active,
                           redeemedAt: $redeemed_at, role: 'staff'})
        """,
        {"uid": f"inv-{email}-{entry_uid}", "email": email,
         "active": active, "redeemed_at": redeemed_at},
    )
    if linked:
        await adb.cypher_query(
            """
            MATCH (i:Invitee {uid: $uid}), (e:Entry {uid: $entry_uid})
            MERGE (i)-[:INVITED_TO]->(e)
            """,
            {"uid": f"inv-{email}-{entry_uid}", "entry_uid": entry_uid},
        )


class TestAnInvitedPersonIsRecognised:
    async def test_a_fresh_invitation_is_found(self, neo4j_graph):
        """The happy path, and the one that failed in production."""
        await _invite(neo4j_graph)

        invitee, entry = await _find_invitee(EMAIL, ENTRY_UID)

        assert invitee.email == EMAIL
        assert entry.uid == ENTRY_UID

    async def test_the_address_is_matched_regardless_of_case(self, neo4j_graph):
        """The query lowercases both sides, so a capitalised address still
        matches — people type their own address inconsistently, and the
        identity provider may hand back whatever it has stored."""
        await _invite(neo4j_graph, email="Cabinet.Duponchelle@Gmail.com")

        invitee, _ = await _find_invitee(EMAIL, ENTRY_UID)

        assert invitee.email == "Cabinet.Duponchelle@Gmail.com"

    async def test_the_sign_in_address_may_differ_in_case(self, neo4j_graph):
        await _invite(neo4j_graph)

        invitee, _ = await _find_invitee("CABINET.DUPONCHELLE@GMAIL.COM", ENTRY_UID)

        assert invitee.email == EMAIL


class TestWhenTheInvitationCannotBeUsed:
    """Each of the four conditions, so a failure names which one broke."""

    async def test_an_invitation_for_another_site_is_not_found(self, neo4j_graph):
        """The hostname suspicion, pinned. entry_uid comes from the site the
        request resolved to, so an invitation created against one site cannot
        be redeemed against another — and the symptom is identical to every
        other miss here."""
        await _invite(neo4j_graph, entry_uid=OTHER_ENTRY_UID)

        with pytest.raises(LookupError):
            await _find_invitee(EMAIL, ENTRY_UID)

    async def test_an_inactive_invitation_is_not_found(self, neo4j_graph):
        await _invite(neo4j_graph, active=False)

        with pytest.raises(LookupError):
            await _find_invitee(EMAIL, ENTRY_UID)

    async def test_an_already_redeemed_invitation_is_not_found(self, neo4j_graph):
        """Redeeming twice is not a sign-in: the second time there is nothing
        left to claim, and the user is expected to have an Access by then."""
        await _invite(neo4j_graph, redeemed_at=1_700_000_000_000)

        with pytest.raises(LookupError):
            await _find_invitee(EMAIL, ENTRY_UID)

    async def test_an_invitation_never_joined_to_the_entry_is_not_found(self, neo4j_graph):
        """An Invitee node with no INVITED_TO edge is invisible to the lookup,
        however correct its email. It would still be listed by the admin UI,
        which reads the nodes — so an invitation can look present and be
        unusable."""
        await _invite(neo4j_graph, linked=False)

        with pytest.raises(LookupError):
            await _find_invitee(EMAIL, ENTRY_UID)

    async def test_a_different_address_is_not_found(self, neo4j_graph):
        await _invite(neo4j_graph, email="someone.else@example.test")

        with pytest.raises(LookupError):
            await _find_invitee(EMAIL, ENTRY_UID)
