"""The credential that lets one deployment read another's entries.

dev, staging and production each have their own Postgres and Neo4j, so cloning
an entry between them crosses a network boundary. The superuser is the same
person on both — `Account.sub` is the Google `providerAccountId` and is
identical everywhere — but the *session* is not: an Auth.js cookie is encrypted
with the issuing instance's AUTH_SECRET, so production cannot read dev's.

Rather than share a secret between instances, the source mints its own token
after the superuser signs in there, and verifies its own signature when the
token comes back. The target never decrypts anything; it relays opaque bytes.
Nothing has to be configured on both sides, and no instance can forge a
credential for another.

The signing key is *derived* from AUTH_SECRET rather than being it:

    sha256(b"clone-export-v1:" + AUTH_SECRET)

so that a fault here can never produce something a session decoder would accept,
and a leaked clone token says nothing about the session secret.
"""
import hashlib
import logging
import os
from uuid import uuid4

from django.core import signing
from django.core.cache import cache
from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

SALT = "clone-export-v1"
#: Long enough for a batch of entries with per-entry confirmation, short enough
#: that a token pasted into a bug report is dead before anyone reads it.
TTL_SECONDS = 900
#: One read per entry per object plus slack. A batch is capped at MAX_ENTRIES,
#: so this bounds what a single token can pull even if it leaks mid-run.
MAX_USES = 200
#: Also the cap on how many entries one token may name.
MAX_ENTRIES = 50


def _key() -> str:
    secret = os.getenv("AUTH_SECRET") or ""
    if not secret:
        # Refuse rather than sign with an empty key: a token anyone could mint
        # is worse than a clone tool that does not work.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AUTH_SECRET is not configured; cloning is unavailable",
        )
    return hashlib.sha256(f"{SALT}:{secret}".encode()).hexdigest()


def mint(*, sub: str, source_host: str, target_origin: str, directory: str,
         org_entry: str | None, entry_uids: list[str] | None) -> tuple[str, int]:
    """Sign a token for one superuser, one target, one directory.

    `org_entry` travels so the target can recognise a MEMBER_OF edge that points
    at the source organization's own entry and remap it to its own, without a
    second round trip. It is not a secret — it is implied by the directory the
    token is already scoped to.
    """
    jti = uuid4().hex
    claims = {
        "v": 1,
        "sub": sub,
        "src": source_host,
        "aud": target_origin,
        "dir": directory,
        "org_entry": org_entry,
        "uids": entry_uids,
        "jti": jti,
    }
    token = signing.dumps(claims, key=_key(), salt=SALT)
    # The use counter lives beside the token so a burnt or exhausted one stops
    # working before it expires.
    cache.set(f"clone:jti:{jti}", 0, TTL_SECONDS + 60)
    return token, TTL_SECONDS


class ExportClaims(dict):
    """A verified token's claims, with the accessors the callers actually use."""

    @property
    def sub(self) -> str:
        return self["sub"]

    @property
    def directory(self) -> str:
        return self["dir"]

    @property
    def org_entry(self) -> str | None:
        return self.get("org_entry")

    @property
    def uids(self) -> list[str] | None:
        return self.get("uids")

    def allows(self, uid: str) -> bool:
        """Whether this token may read that entry.

        A token with no uid list is scoped to the whole directory; one with a
        list is scoped to exactly those entries.
        """
        return self.uids is None or uid in self.uids


def read(token: str, *, request_host: str) -> ExportClaims:
    """Verify a token and return its claims, or raise 401.

    Raises rather than returns None so a caller cannot forget to check. The
    detail is deliberately vague — a caller holding a bad token learns that it
    is bad, not which of the checks it failed.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired clone token",
    )
    try:
        claims = signing.loads(token, key=_key(), salt=SALT, max_age=TTL_SECONDS)
    except signing.BadSignature:
        raise unauthorized
    if claims.get("v") != 1:
        raise unauthorized
    # A token minted for another instance is not valid here, even though this
    # instance could verify a signature it made itself.
    if claims.get("src") != request_host:
        logger.warning("clone token for %s presented at %s", claims.get("src"), request_host)
        raise unauthorized
    jti = claims.get("jti")
    uses = cache.get(f"clone:jti:{jti}")
    if uses is None or uses >= MAX_USES:
        raise unauthorized
    cache.set(f"clone:jti:{jti}", uses + 1, TTL_SECONDS + 60)
    return ExportClaims(claims)


def burn(token: str, *, request_host: str) -> None:
    """Invalidate a token before it expires, at the end of a batch."""
    try:
        claims = read(token, request_host=request_host)
    except HTTPException:
        return
    cache.delete(f"clone:jti:{claims['jti']}")


def bearer(request: Request) -> str | None:
    """The clone token on a request, if it carries one.

    A header rather than a cookie: a bearer token in a header is only ever sent
    where something deliberately puts it, while a cookie rides along on requests
    nobody intended.
    """
    header = request.headers.get("authorization") or ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value.strip()
