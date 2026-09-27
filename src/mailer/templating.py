"""Building the content of outgoing emails."""


def organization_site_url(organization, domain: str) -> str:
    """Public root URL of the organization's site, with no trailing slash.

    A site served under a base path (unipa.fr/annuaire) cannot be derived from
    site.domain: nginx strips the prefix before the request reaches the
    backend. Such sites set Organization.public_base_url; every other site
    leaves it blank and gets https://{domain}.
    """
    base_url = (getattr(organization, "public_base_url", "") or "").strip()
    if base_url:
        return base_url.rstrip("/")
    return f"https://{domain}"


def organization_site_name(organization, domain: str) -> str:
    """How the site is named in prose: its public URL without the scheme.

    dev.unipa.fr/annuaire rather than dev.unipa.fr, which is the WordPress at
    the root and not the service the invitee is sent to.
    """
    return organization_site_url(organization, domain).split("://", 1)[-1]
