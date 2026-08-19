import logging

from api.types.effector_type_label import (
    EffectorTypeLabels,
    GenderedLabels,
    NumberedLabels,
)
from directory.models.core import Label

logger = logging.getLogger(__name__)

# The grammatical numbers a Label can carry, in the order the response lists
# them. From directory.models.core.Label.GrammaticalNumber; named here so the
# skeleton below does not depend on iteration order of a TextChoices.
NUMBERS = ("S", "P")


async def get_effector_type_labels(
    language: str,
    term_type: str = "name",
) -> EffectorTypeLabels:
    """Build the effector-type label dictionary for one language.

    Returns every uid that has a Label row of `term_type`, each mapped to the
    six slots (singular/plural x feminine/masculine/neutral). Slots with no
    authored label in `language` stay null rather than being omitted: the
    frontend indexes into them directly.

    Note that `term_type` decides which uids appear at all, while `language`
    only decides which slots get filled — a uid whose labels are all in another
    language is still listed, with six nulls. That asymmetry is inherited from
    the v1 endpoint and is relied upon: the uid set is the catalogue of effector
    types, not of translations.

    One query, unlike the v1 implementation which ran two per gender per number
    per uid. The rows carry everything needed, so the grouping happens here
    rather than in the database.
    """
    labels: dict[str, NumberedLabels] = {}

    # select_related is not available for a ManyToMany; prefetch_related pulls
    # every gender row in one extra query instead of one per label.
    queryset = (
        Label.objects.filter(term_type=term_type)
        .prefetch_related("gender")
        .only("uid", "label", "grammatical_number", "language")
    )

    async for row in queryset:
        uid = row.uid.hex
        if uid not in labels:
            # Every uid gets the full skeleton on first sight, so a uid whose
            # only rows are in another language still answers with nulls rather
            # than a missing key.
            labels[uid] = NumberedLabels(
                S=GenderedLabels(),
                P=GenderedLabels(),
            )
        if row.language != language:
            continue
        if row.grammatical_number not in NUMBERS:
            logger.warning(
                "Label %s has grammatical_number %r, which is neither S nor P; skipping",
                row.pk,
                row.grammatical_number,
            )
            continue
        slot = getattr(labels[uid], row.grammatical_number)
        # A label may be recorded against several genders — "CPTS" is the same
        # word whatever the gender — so this is a loop, not a single lookup.
        for gender in row.gender.all():
            if not hasattr(slot, gender.code):
                logger.warning(
                    "GrammaticalGender %r has code %r, which is none of F/M/N; skipping",
                    gender.name,
                    gender.code,
                )
                continue
            setattr(slot, gender.code, row.label)

    return EffectorTypeLabels(labels)
