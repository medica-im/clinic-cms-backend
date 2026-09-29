"""Where an entry's former slug leads now (directory.EntrySlug).

The entry page asks when /fullentries/slug/{slug} answers 404, and redirects
to the current slug. Public, like the entry pages it serves.
"""

from asgiref.sync import sync_to_async
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from directory.models import EntrySlug
from directory.models.agraph import Entry as AgraphEntry

router = APIRouter()


class CurrentSlug(BaseModel):
    uid: str
    slug: str


def former_slug_entry(slug: str) -> str | None:
    row = EntrySlug.objects.filter(slug=slug).first()
    return row.entry_uid if row else None


@router.get("/entry-slugs/{slug}", response_model=CurrentSlug)
async def current_slug(slug: str) -> CurrentSlug:
    entry_uid = await sync_to_async(former_slug_entry)(slug)
    entry = await AgraphEntry.nodes.get_or_none(uid=entry_uid) if entry_uid else None
    if entry is None or not entry.slug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No entry had this slug")
    return CurrentSlug(uid=entry.uid, slug=entry.slug)
