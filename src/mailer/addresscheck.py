"""Checking an address before anything is sent to it.

Warnings for the person typing or importing addresses, never refusals:
- a typo in a common mail domain gets a suggestion ("gmial.com" ->
  "gmail.com");
- a domain that cannot receive mail (no MX record, nor an address record to
  fall back on, RFC 5321 5.1) is flagged;
- an address already known to be bad (mailer.suppression) says why.

A DNS timeout or failure is not evidence: the address then passes. Asks DNS,
not the mail service, so it does not depend on the provider. See
tests/api/test_address_checks.py.
"""
import functools
import logging

import dns.exception
import dns.resolver
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from mailer import suppression

logger = logging.getLogger(__name__)

# Where the members' addresses mostly are: a mistyped one of these is far more
# likely than a real domain one letter away.
COMMON_DOMAINS = (
    "gmail.com", "googlemail.com", "orange.fr", "wanadoo.fr", "free.fr", "laposte.net", "sfr.fr", "neuf.fr",
    "bbox.fr", "aliceadsl.fr", "numericable.fr", "hotmail.fr", "hotmail.com", "live.fr", "outlook.fr",
    "outlook.com", "msn.com", "yahoo.fr", "yahoo.com", "icloud.com", "me.com", "aol.com", "protonmail.com",
    "proton.me", "apicrypt.org", "mssante.fr",
)
MAX_DISTANCE = 2
DNS_LIFETIME = 3


def _distance(a: str, b: str) -> int:
    """Levenshtein distance, stopping early once past MAX_DISTANCE."""
    if abs(len(a) - len(b)) > MAX_DISTANCE:
        return MAX_DISTANCE + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        if min(current) > MAX_DISTANCE:
            return MAX_DISTANCE + 1
        previous = current
    return previous[-1]


def suggest_domain(domain: str) -> str | None:
    """The common domain this one is probably a typo of, if any."""
    domain = domain.lower()
    if domain in COMMON_DOMAINS:
        return None
    best = min(COMMON_DOMAINS, key=lambda common: _distance(domain, common))
    return best if 0 < _distance(domain, best) <= MAX_DISTANCE else None


@functools.lru_cache(maxsize=2048)
def receives_mail(domain: str) -> bool | None:
    """True / False when DNS says so; None when it could not tell."""
    try:
        dns.resolver.resolve(domain, "MX", lifetime=DNS_LIFETIME)
        return True
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        pass
    except dns.exception.DNSException as e:
        logger.info(f"MX lookup for {domain} inconclusive: {e}")
        return None
    for rtype in ("A", "AAAA"):
        try:
            dns.resolver.resolve(domain, rtype, lifetime=DNS_LIFETIME)
            return True
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            continue
        except dns.exception.DNSException as e:
            logger.info(f"{rtype} lookup for {domain} inconclusive: {e}")
            return None
    return False


def check(address: str, organization=None) -> dict:
    """{"email", "suggestion": better address or None, "problem": None |
    "invalid" | "no_mail_domain" | a suppression reason}."""
    email = (address or "").strip()
    result = {"email": email, "suggestion": None, "problem": None}
    try:
        validate_email(email)
    except ValidationError:
        result["problem"] = "invalid"
        return result
    local, domain = email.rsplit("@", 1)
    better = suggest_domain(domain)
    if better:
        result["suggestion"] = f"{local}@{better}"
    known = suppression.blocking(email, organization)
    if known is not None:
        result["problem"] = known.reason
    elif receives_mail(domain.lower()) is False:
        result["problem"] = "no_mail_domain"
    return result
