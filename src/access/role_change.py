"""Who may change whose role, and to what.

The decision only, with no HTTP and no database in it. The endpoint in
api/routers/users.py asks these functions and turns the answer into a status
code; keeping the rules here means the permission matrix can be read in one
place, and that the reasoning below sits next to the code it governs rather
than in a router that is mostly plumbing.

The refusals come in two kinds, and the difference is the one CLAUDE.md draws
between the AccessControl table and the serializer layer:

* **403 — you may not do this.** A judgement about the actor. Somebody else,
  holding a higher role, could do the same thing legitimately.
* **409 — this cannot be done.** An invariant of the data, refused whoever
  asks. A superuser is refused too; that is what makes it an invariant rather
  than a permission.

Getting that split wrong is not cosmetic. An invariant expressed as a
permission has to be repeated for every role, and the object-level branch of
`authorize_api` — which grants access to whoever is connected to the object —
would walk straight past it.
"""
from enum import Enum

from access.roles import ROLES


class Decision(Enum):
    """Why a role change was allowed or refused.

    FORBIDDEN and CONFLICT map to 403 and 409 respectively; the endpoint does
    that translation so this module stays free of HTTP.
    """
    ALLOWED = "allowed"
    FORBIDDEN = "forbidden"
    CONFLICT = "conflict"


# Ordered least to most privileged. Comparing roles is the whole of the
# escalation rule, so it is worth having the order written down once: deriving
# it from the ROLES dict's insertion order would make a rename or a reordering
# of that mapping silently change who may promote whom.
HIERARCHY = ["anonymous", "registered", "staff", "administrator", "superuser"]


def rank(role: str) -> int:
    """Position in the hierarchy; unknown roles rank lowest.

    An unrecognised role is treated as the least privileged rather than
    rejected, so a typo or a role dropped from ROLES fails closed — it can be
    granted nothing and can grant nothing.
    """
    try:
        return HIERARCHY.index(role)
    except ValueError:
        return -1


def is_valid_role(role: str) -> bool:
    return role in ROLES


def may_change_role(
    actor_role: str,
    target_role: str,
    granted: str,
    actor_is_target: bool,
    target_suspended: bool = False,
    actor_suspended: bool = False,
    last_superuser: bool = False,
) -> Decision:
    """Whether `actor_role` may change a `target_role` user to `granted`.

    `actor_is_target` distinguishes stepping down from pushing somebody else
    down: the two are the same request to the endpoint and different acts.
    """
    # Invariants first. These are refused whoever asks, so checking them after
    # the permission rules would let a superuser through the very cases the
    # invariants exist to forbid.
    if target_suspended:
        # A promotion would arrive as a fresh Access carrying no suspension,
        # which is precisely what suspension exists to prevent — the role
        # change would launder it.
        return Decision.CONFLICT

    if last_superuser and actor_is_target and granted != "superuser":
        # Otherwise nobody can promote anyone ever again and the way back is
        # the Django shell.
        return Decision.CONFLICT

    # A suspended account keeps its role — that is how the dashboard can
    # explain itself — so its privileges have to be denied here rather than by
    # the role lookup, or suspension would mean nothing for the actor.
    if actor_suspended:
        return Decision.FORBIDDEN

    if not is_valid_role(granted):
        return Decision.FORBIDDEN

    # Stepping down is always allowed. It needs no privilege, and refusing it
    # would leave somebody stuck holding rights they are trying to give up.
    if actor_is_target and rank(granted) < rank(actor_role):
        return Decision.ALLOWED

    if rank(actor_role) < rank("administrator"):
        # Nobody below administrator grants anything, whatever the target.
        return Decision.FORBIDDEN

    if rank(granted) > rank(actor_role):
        # The escalation the whole feature exists to prevent: otherwise an
        # administrator promotes themselves by way of a second account.
        return Decision.FORBIDDEN

    if rank(actor_role) < rank("superuser"):
        # An administrator works strictly below their own level. Two
        # administrators are peers, and letting one demote the other turns a
        # disagreement into a race — whoever clicks first wins — and makes
        # every administrator a single point of failure for the rest.
        if not actor_is_target and rank(target_role) >= rank(actor_role):
            return Decision.FORBIDDEN

        # Only a superuser, or the user themselves, demotes. Pushing somebody
        # else down is not an administrator's to do.
        if not actor_is_target and rank(granted) < rank(target_role):
            return Decision.FORBIDDEN

    return Decision.ALLOWED


def may_suspend(actor_role: str, actor_is_target: bool) -> Decision:
    """Whether `actor_role` may suspend or restore an account.

    Suspension is a superuser act. It is the one control that can leave an
    administrator unable to undo what was done to them, so it does not belong
    to a role that has peers.
    """
    if actor_is_target:
        # Suspending yourself is a confusing logout that leaves nobody able to
        # undo it — a conflict rather than a permission failure, since no role
        # makes it sensible.
        return Decision.CONFLICT

    if actor_role != "superuser":
        return Decision.FORBIDDEN

    return Decision.ALLOWED
