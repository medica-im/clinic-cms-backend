from django.core.cache import cache
from fastapi import APIRouter, Request, Response, status

from api.types.opengraph import OpenGraphCard
from api.utils import DEFAULT_TTL, get_site_from_request, get_ttl, resolve_ttl
from opengraph.cache import opengraph_cache_key
from opengraph.models import TwitterCard

router = APIRouter()

API_VERSION = "v2"


def _card(card: TwitterCard) -> dict:
    return {
        "title": card.title,
        "username": card.username,
        "twitter_description": card.twitter_description,
        "description": card.description,
        "image_url": f"https://{card.site.domain}{card.image.url}" if card.image else None,
        "image_alt": card.image_alt or None,
    }


@router.get(
    "/opengraph",
    response_model=OpenGraphCard,
    responses={status.HTTP_204_NO_CONTENT: {"description": "The site has no sharing card."}},
)
async def opengraph(request: Request):
    """The requesting site's sharing card, or 204 when it has none.

    Cached per site, the absence of a card included; saving or deleting a card
    clears its site's entry (opengraph.cache).
    """
    site = await get_site_from_request(request)
    key = opengraph_cache_key(site.domain)
    cached = cache.get(key)
    if cached is None:
        card = await TwitterCard.objects.select_related("site").filter(site=site).afirst()
        cached = {"card": _card(card) if card else None}
        cache.set(key, cached, timeout=resolve_ttl(await get_ttl(API_VERSION, request), DEFAULT_TTL))
    if cached["card"] is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return OpenGraphCard(**cached["card"])
