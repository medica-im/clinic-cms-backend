"""Who may change an entry's effector type, and until when.

A superuser at any time. An administrator within the organization's
administrator window, the entry's creator or an owner ("connected") within
its connected window (Organization.entry_type_edit_days_*); someone who is
both gets the longer one, and a window of 0 means never. An entry with no
createdAt cannot be shown to be recent: only a superuser may change it.

Pure: the caller supplies the role (from this site's graph), whether the
caller is connected to the entry, and the organization's windows.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class TypeEditPermission:
    allowed: bool
    # None when allowed; else not_allowed (no right at all), expired (the
    # window has passed) or no_date (no createdAt to measure it from).
    reason: str | None
    # The window that applies, in days; None for a superuser or no right.
    window_days: int | None
    deadline: datetime | None


def type_edit_permission(
    *,
    role: str | None,
    connected: bool,
    created_at_ms: int | None,
    now: datetime,
    admin_days: int,
    connected_days: int,
) -> TypeEditPermission:
    if role == "superuser":
        return TypeEditPermission(True, None, None, None)

    windows = []
    if role == "administrator":
        windows.append(admin_days)
    if connected:
        windows.append(connected_days)
    window = max(windows, default=0)
    if window <= 0:
        return TypeEditPermission(False, "not_allowed", None, None)

    if not created_at_ms:
        return TypeEditPermission(False, "no_date", window, None)

    created = datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc)
    deadline = created + timedelta(days=window)
    if now <= deadline:
        return TypeEditPermission(True, None, window, deadline)
    return TypeEditPermission(False, "expired", window, deadline)
