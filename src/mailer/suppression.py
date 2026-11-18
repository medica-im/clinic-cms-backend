"""Addresses not to send to automatically: dead ones, and refusals.

A bounce (the mailbox does not exist or does not receive mail) or an address
the service refused as written is remembered for every organization: the
address does not work, whoever sends. A spam complaint or an unsubscribe is
the person refusing one organization's mail: remembered for that one only.

Automatic sends (a new invitation, a batch) skip a remembered address; an
administrator's resend may force a dead one after checking it, never a
refusal. A later delivery to a bounced address forgets the bounce. Filled by
mailer.delivery (mark_result, apply_event). See tests/api/test_bad_addresses.py.
"""
import logging

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from mailer.models import EmailSuppression

logger = logging.getLogger(__name__)

R = EmailSuppression.Reason
DEAD = {R.BOUNCED, R.REFUSED}
OPTED_OUT = {R.COMPLAINED, R.UNSUBSCRIBED}


def normalize(address: str) -> str:
    return (address or "").strip().lower()


def record(address: str, reason: str, organization=None, detail: str = "", event=None) -> EmailSuppression | None:
    """Remember an address, or count it again if it already is."""
    address = normalize(address)
    if not address:
        return None
    with transaction.atomic():
        row, created = EmailSuppression.objects.select_for_update().get_or_create(
            address=address, organization=organization,
            defaults={"reason": reason, "detail": detail[:2000], "event": event},
        )
        if not created:
            EmailSuppression.objects.filter(id=row.id).update(
                reason=reason, detail=detail[:2000] or row.detail, event=event or row.event,
                count=F("count") + 1, last_seen=timezone.now(),
            )
            row.refresh_from_db()
    return row


def forget_dead(address: str) -> None:
    """The address received mail after all: forget its bounce or refusal."""
    EmailSuppression.objects.filter(address=normalize(address), organization__isnull=True, reason__in=DEAD).delete()


def _scope(organization):
    organization_id = getattr(organization, "id", None)
    if organization_id is None:
        return Q(organization__isnull=True)
    return Q(organization__isnull=True) | Q(organization_id=organization_id)


def blocking(address: str, organization) -> EmailSuppression | None:
    """Why not to send to this address for this organization, or None.

    A refusal of this organization's mail comes first: it cannot be forced.
    """
    rows = list(EmailSuppression.objects.filter(_scope(organization), address=normalize(address)))
    rows.sort(key=lambda row: row.reason not in OPTED_OUT)
    return rows[0] if rows else None


def issues_for(addresses, organization) -> dict[str, EmailSuppression]:
    """blocking() for many addresses at once, keyed by normalized address."""
    wanted = {normalize(a) for a in addresses if a}
    found: dict[str, EmailSuppression] = {}
    if not wanted:
        return found
    for row in EmailSuppression.objects.filter(_scope(organization), address__in=wanted):
        current = found.get(row.address)
        if current is None or (row.reason in OPTED_OUT and current.reason not in OPTED_OUT):
            found[row.address] = row
    return found


def is_opted_out(row) -> bool:
    return row is not None and row.reason in OPTED_OUT


def issue_payload(row) -> dict | None:
    """What the API says about a remembered address (addressIssue)."""
    if row is None:
        return None
    return {
        "reason": row.reason,
        "since": row.first_seen.isoformat().replace("+00:00", "Z"),
        "detail": row.detail or None,
    }
