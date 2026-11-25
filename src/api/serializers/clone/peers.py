"""Make this instance's peer registry match the list it is given.

The list is a trust decision kept outside the code (the console's reviewed
file); this applies it. A row the list no longer names is retired, never
deleted: `active=False` is how the model retires a peer without losing its row.

All or nothing: every row is checked before anything is written, so a bad row
cannot leave the registry half-applied.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from directory.models import PeerInstance

FIELDS = ("display_name", "origin", "outbound", "inbound")


class InvalidPeers(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def apply_peers(peers: list[dict]) -> dict[str, list[str]]:
    problems = _duplicates(peers)
    if problems:
        raise InvalidPeers(problems)

    existing = {p.name: p for p in PeerInstance.objects.all()}
    created, updated = [], []
    to_save = []
    for wanted in peers:
        row = existing.get(wanted["name"])
        if row is None:
            row = PeerInstance(name=wanted["name"])
            created.append(row.name)
        elif row.active and all(getattr(row, f) == wanted[f] for f in FIELDS):
            continue
        else:
            updated.append(row.name)
        for f in FIELDS:
            setattr(row, f, wanted[f])
        row.active = True
        problems += _problems(row)
        to_save.append(row)
    if problems:
        raise InvalidPeers(problems)

    named = {p["name"] for p in peers}
    retired = [name for name, row in existing.items() if name not in named and row.active]
    with transaction.atomic():
        for row in to_save:
            row.save()
        PeerInstance.objects.filter(name__in=retired).update(active=False)
    return {"created": created, "updated": updated, "retired": retired}


def _duplicates(peers: list[dict]) -> list[str]:
    problems = []
    for key in ("name", "origin"):
        values = [p[key].rstrip("/") if key == "origin" else p[key] for p in peers]
        for value in sorted({v for v in values if values.count(v) > 1}):
            problems.append(f"two peers share the {key} {value!r}")
    return problems


def _problems(row: PeerInstance) -> list[str]:
    try:
        row.full_clean(validate_unique=False)
    except ValidationError as e:
        return [f"{row.name}: {message}" for message in e.messages]
    return []
