"""Mailgun endpoint construction, free of any Django import.

Kept separate from mailer.config so backend.settings can build the default
API URL without importing a module that reads settings back.
"""

REGION_HOSTS = {
    "eu": "api.eu.mailgun.net",
    "us": "api.mailgun.net",
}

DEFAULT_REGION = "eu"


def build_api_url(domain: str, region: str = DEFAULT_REGION) -> str:
    host = REGION_HOSTS.get(region, REGION_HOSTS[DEFAULT_REGION])
    return f"https://{host}/v3/{domain}/messages"
