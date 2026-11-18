"""Mailgun: the only module that knows its URLs, fields and answers.

Turns an OutgoingMessage into a POST to Mailgun's messages endpoint, and
Mailgun's answer into a SendOutcome. Also where an organization's
MailgunAccount row becomes credentials. See mailer/providers/base.py for the
vocabulary, tests/test_mail_provider_boundary.py for the boundary.
"""
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from mailer.endpoints import build_api_url
from mailer.providers.base import DeliveryEvent, ErrorKind, EventKind, OutgoingMessage, SendOutcome

logger = logging.getLogger(__name__)

# (connect, read) seconds. Without one, a Mailgun that stops answering held
# the batch invitation task forever.
TIMEOUT = (5, 30)
MAX_ATTEMPTS = 4
BACKOFF = 2  # seconds before the 2nd attempt, doubled each time after
MAX_PAUSE = 60  # cap on Retry-After, so one header cannot park the worker


@dataclass(frozen=True)
class MailgunCredentials:
    api_url: str
    auth: tuple[str, str]


def format_from_address(email: str, name: str = "") -> str:
    return f"{name} <{email}>" if name else email


def _retryable(status: int) -> bool:
    return status == 429 or status >= 500


def _pause(attempt: int, response=None) -> float:
    retry_after = (response.headers or {}).get("Retry-After") if response is not None else None
    if retry_after:
        try:
            return min(float(retry_after), MAX_PAUSE)
        except ValueError:
            pass
    return min(BACKOFF * 2 ** (attempt - 1), MAX_PAUSE)


def _post(credentials: MailgunCredentials, **kwargs) -> requests.Response:
    """POST to Mailgun with a timeout, retrying what may pass.

    Retried: 429, 5xx, and a connection that never got through. Final: any
    other answer, and a read timeout -- the request reached Mailgun, which may
    have accepted it, and a second post would send the email twice. Raises
    the last connection error when every attempt failed to connect. Callers
    all run in Celery tasks, so the pause holds no web request.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(credentials.api_url, auth=credentials.auth, timeout=TIMEOUT, **kwargs)
        except (requests.ConnectionError, requests.ConnectTimeout) as e:
            if isinstance(e, requests.ReadTimeout) or attempt == MAX_ATTEMPTS:
                raise
            logger.warning(f"Mailgun unreachable (attempt {attempt}/{MAX_ATTEMPTS}): {e}")
            time.sleep(_pause(attempt))
            continue
        if not _retryable(response.status_code) or attempt == MAX_ATTEMPTS:
            return response
        logger.warning(f"Mailgun answered {response.status_code} (attempt {attempt}/{MAX_ATTEMPTS}), retrying")
        time.sleep(_pause(attempt, response))
    raise AssertionError("unreachable")


def _form(message: OutgoingMessage) -> dict:
    """Mailgun form fields. Optional ones only when set, so a plain email
    posts exactly the fields it always did."""
    data = {"from": message.from_address, "to": message.to, "subject": message.subject, "text": message.text}
    if message.html is not None:
        data["html"] = message.html
    if message.reply_to:
        data["h:Reply-To"] = message.reply_to
    if message.per_recipient is not None:
        # With recipient-variables Mailgun sends each address its own copy.
        data["recipient-variables"] = json.dumps(message.per_recipient)
    for key, value in (message.metadata or {}).items():
        # Custom variables: returned as "user-variables" in every event.
        data[f"v:{key}"] = str(value)
    if message.tags:
        data["o:tag"] = list(message.tags)
    return data


# Mailgun's event -> ours. "failed" is split on severity and reason below.
EVENTS = {
    "delivered": EventKind.DELIVERED,
    "complained": EventKind.COMPLAINED,
    "unsubscribed": EventKind.UNSUBSCRIBED,
}
# A permanent failure for one of these reasons was never attempted: Mailgun
# dropped it because the address is on the domain's own suppression lists.
SUPPRESSION_REASONS = {"suppress-bounce", "suppress-complaint", "suppress-unsubscribe"}


def _signing_keys() -> list[str]:
    """The .env account's key, and every organization account's."""
    from mailer.models import MailgunAccount

    keys = [settings.MAILGUN_WEBHOOK_SIGNING_KEY] if getattr(settings, "MAILGUN_WEBHOOK_SIGNING_KEY", "") else []
    keys += [
        key for key in MailgunAccount.objects.filter(active=True)
        .exclude(webhook_signing_key="").values_list("webhook_signing_key", flat=True)
    ]
    return keys


def _kind(event_data: dict) -> EventKind | None:
    name = event_data.get("event")
    if name == "failed":
        if event_data.get("severity") == "temporary":
            return EventKind.DEFERRED
        if event_data.get("reason") in SUPPRESSION_REASONS:
            return EventKind.SUPPRESSED
        return EventKind.BOUNCED
    return EVENTS.get(name)


def _detail(event_data: dict) -> str:
    status = event_data.get("delivery-status") or {}
    words = status.get("message") or status.get("description") or event_data.get("reason") or ""
    code = status.get("code")
    return f"{code} {words}".strip() if code else str(words)


def _error_kind(status: int) -> ErrorKind:
    if status == 429:
        return ErrorKind.RATE_LIMITED
    if status >= 500:
        return ErrorKind.PROVIDER_UNAVAILABLE
    if status in (401, 403, 404):
        # Bad key, a key without rights, an unknown sending domain.
        return ErrorKind.MISCONFIGURED
    return ErrorKind.INVALID_REQUEST


def _body(response):
    try:
        return response.json()
    except ValueError:
        return response.text


class MailgunProvider:
    def default_identity(self) -> tuple[MailgunCredentials, str]:
        return (
            MailgunCredentials(
                api_url=settings.MAILGUN_API_URL,
                auth=(settings.MAILGUN_SENDING_KEY_ID, settings.MAILGUN_SENDING_KEY),
            ),
            settings.MAILGUN_FROM_ADDRESS,
        )

    def identity_for(self, organization) -> tuple[MailgunCredentials, str] | None:
        """The organization's own MailgunAccount, when it has a usable one.

        A half-filled row must not reach Mailgun: it would fail with a 401 at
        send time, far harder to diagnose than mail from the default address.
        """
        if organization is None:
            return None
        try:
            account = organization.mailgun_account
        except (AttributeError, ObjectDoesNotExist):
            return None
        if account is None or not account.is_usable():
            logger.info(
                f"Mailgun account for organization {organization} is unusable; "
                f"falling back to the default credentials"
            )
            return None
        return (
            MailgunCredentials(
                api_url=build_api_url(account.domain, account.region),
                auth=(account.sending_key_id, account.api_key),
            ),
            format_from_address(account.from_email, account.from_name),
        )

    def send(self, message: OutgoingMessage, credentials: MailgunCredentials) -> SendOutcome:
        try:
            response = _post(credentials, data=_form(message))
        except requests.ReadTimeout as e:
            return SendOutcome(accepted=False, error_kind=ErrorKind.OUTCOME_UNKNOWN, detail=str(e))
        except (requests.ConnectionError, requests.ConnectTimeout) as e:
            return SendOutcome(accepted=False, error_kind=ErrorKind.UNREACHABLE, detail=str(e))
        except requests.RequestException as e:
            return SendOutcome(accepted=False, error_kind=ErrorKind.OUTCOME_UNKNOWN, detail=str(e))
        body = _body(response)
        if response.status_code == 200:
            message_id = body.get("id", "") if isinstance(body, dict) else ""
            return SendOutcome(accepted=True, message_id=message_id, status_code=200, raw=body)
        return SendOutcome(
            accepted=False,
            error_kind=_error_kind(response.status_code),
            detail=response.text,
            status_code=response.status_code,
            raw=body,
        )

    def verify_webhook(self, payload: dict) -> bool:
        """Mailgun signs HMAC-SHA256(signing key, timestamp + token)."""
        signature = payload.get("signature") if isinstance(payload, dict) else None
        if not isinstance(signature, dict):
            return False
        timestamp, token, given = (str(signature.get(k, "")) for k in ("timestamp", "token", "signature"))
        if not (timestamp and token and given):
            return False
        message = f"{timestamp}{token}".encode()
        return any(
            hmac.compare_digest(hmac.new(key.encode(), message, hashlib.sha256).hexdigest(), given)
            for key in _signing_keys()
        )

    def parse_event(self, payload: dict) -> DeliveryEvent | None:
        data = payload.get("event-data") or {}
        kind = _kind(data)
        if kind is None:
            return None  # accepted, opened, clicked...: not tracked
        headers = (data.get("message") or {}).get("headers") or {}
        return DeliveryEvent(
            provider="mailgun",
            event_id=str(data.get("id") or ""),
            kind=kind,
            recipient=data.get("recipient") or "",
            occurred_at=float(data.get("timestamp") or time.time()),
            metadata=data.get("user-variables") or {},
            message_id=str(headers.get("message-id") or "").strip("<>"),
            detail=_detail(data),
            raw=data,
        )


# --- Webhook registration (manage.py register_mail_webhooks) -------------------

# The webhooks whose events parse_event turns into ours.
WEBHOOKS = ("delivered", "permanent_fail", "temporary_fail", "complained", "unsubscribed")


def _webhooks_url(domain: str) -> str:
    from mailer.endpoints import DEFAULT_REGION, REGION_HOSTS
    host = REGION_HOSTS.get(getattr(settings, "MAILGUN_REGION", DEFAULT_REGION), REGION_HOSTS[DEFAULT_REGION])
    return f"https://{host}/v3/domains/{domain}/webhooks"


def _api_auth() -> tuple[str, str]:
    """Managing webhooks needs an account API key, not a domain sending key."""
    key = getattr(settings, "MAILGUN_API_KEY", "") or settings.MAILGUN_SENDING_KEY
    return ("api", key)


def webhook_targets(domain: str) -> dict[str, list[str]]:
    """For each tracked webhook, the URLs it points at now ([] if none)."""
    targets = {}
    for name in WEBHOOKS:
        response = requests.get(f"{_webhooks_url(domain)}/{name}", auth=_api_auth(), timeout=TIMEOUT)
        if response.status_code == 404:
            targets[name] = []
        elif response.status_code == 200:
            hook = response.json().get("webhook") or {}
            targets[name] = list(hook.get("urls") or ([hook["url"]] if hook.get("url") else []))
        else:
            raise RuntimeError(f"Mailgun answered {response.status_code} for webhook {name}: {response.text}")
    return targets


def point_webhook(domain: str, name: str, url: str, exists: bool) -> None:
    if exists:
        response = requests.put(f"{_webhooks_url(domain)}/{name}", auth=_api_auth(), data={"url": url}, timeout=TIMEOUT)
    else:
        response = requests.post(_webhooks_url(domain), auth=_api_auth(), data={"id": name, "url": url}, timeout=TIMEOUT)
    if response.status_code != 200:
        raise RuntimeError(f"Mailgun answered {response.status_code} for webhook {name}: {response.text}")
