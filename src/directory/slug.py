import logging
from django.utils.text import slugify
from neomodel import adb
from directory.models.core import Label

logger = logging.getLogger(__name__)


async def _get_et_terms(effector_type, gender: str | None) -> list[str]:
    """Get gender-appropriate effector type terms for slug generation.

    For F/M gender: use gendered name/label from the Label table,
    fallback to raw name_fr/label_fr if no Label entries exist.
    For synonyms_fr: each synonym is checked against the Label table.
    If it has a Label entry, it's gendered — only include the matching
    gender form. If it has no Label entry, it's neutral and always included.
    """
    terms = []

    if gender and gender in ("F", "M"):
        # Gendered name/label from Label table
        labels = Label.objects.filter(
            uid=effector_type.uid,
            gender__code=gender,
            grammatical_number="S",
            language="fr",
            term_type__in=["name", "label", "synonym"],
        )
        async for lbl in labels:
            terms.append(lbl.label)

    # Fallback: use raw name/label if no gendered forms found
    if not terms:
        if effector_type.name_fr:
            terms.append(effector_type.name_fr)
        if effector_type.label_fr and effector_type.label_fr != effector_type.name_fr:
            terms.append(effector_type.label_fr)

    # Add synonyms_fr that are either gender-neutral or match the effector gender
    if effector_type.synonyms_fr:
        # Get all synonym labels for this effector type to check which are gendered
        gendered_synonyms = set()
        all_synonym_labels = Label.objects.filter(
            uid=effector_type.uid,
            language="fr",
            term_type="synonym",
        )
        async for lbl in all_synonym_labels:
            gendered_synonyms.add(lbl.label)

        existing = set(terms)
        for syn in effector_type.synonyms_fr:
            if syn in existing:
                continue
            if syn in gendered_synonyms:
                # This synonym is gendered — it was already included above
                # via the gender-filtered Label query if it matched
                continue
            # Not in Label table — it's neutral, always include
            terms.append(syn)
            existing.add(syn)

    return terms


def _name_variants(name_fr: str, include_last_only: bool = False) -> list[str]:
    """Generate name permutations from a full name string."""
    parts = name_fr.strip().split()
    if not parts:
        return []
    variants = [" ".join(parts)]
    if len(parts) > 1:
        variants.append(" ".join(reversed(parts)))
    if include_last_only and len(parts) > 1:
        variants.append(parts[-1])
    return variants


def _all_name_variants(effector, include_last_only: bool = False) -> list[str]:
    """Combine name variants from both name_fr and label_fr, deduplicated."""
    variants = _name_variants(effector.name_fr, include_last_only)
    if effector.label_fr and effector.label_fr != effector.name_fr:
        seen = set(variants)
        for v in _name_variants(effector.label_fr, include_last_only):
            if v not in seen:
                variants.append(v)
                seen.add(v)
    return variants


def _build_candidates(
    name_variants: list[str],
    et_terms: list[str],
    location_variants: list[str],
) -> list[str]:
    """Build slug candidates from all combinations, slugify, and deduplicate."""
    seen = set()
    candidates = []
    for name in name_variants:
        for term in et_terms:
            for loc in location_variants:
                raw = f"{name} {term} {loc}"
                slug = slugify(raw)
                if slug and slug not in seen:
                    seen.add(slug)
                    candidates.append(slug)
    return candidates


async def _filter_existing_slugs(slugs: list[str]) -> list[str]:
    """Remove slugs that already exist as Entry.slug in Neo4j."""
    if not slugs:
        return []
    results, _ = await adb.cypher_query(
        "MATCH (e:Entry) WHERE e.slug IN $slugs RETURN e.slug",
        {"slugs": slugs},
    )
    existing = {row[0] for row in results}
    return [s for s in slugs if s not in existing]


async def _is_hcw(effector_type) -> bool:
    """Check if the EffectorType node has the HCW label."""
    results, _ = await adb.cypher_query(
        "MATCH (n:EffectorType {uid: $uid}) RETURN labels(n)",
        {"uid": effector_type.uid},
    )
    if results:
        return "HCW" in results[0][0]
    return False


async def generate_entry_slugs(
    effector,
    facility,
    effector_type,
    count: int = 12,
) -> list[str]:
    """Generate a list of unique, human-readable slug candidates for an Entry.

    Args:
        effector: AsyncEffector node (needs name_fr, label_fr, gender)
        facility: AsyncFacility node (needs zip, street, commune relationship)
        effector_type: AsyncEffectorType node (needs name_fr, label_fr, synonyms_fr, uid)
        count: maximum number of slugs to return

    Returns:
        List of available slugs sorted shortest-to-longest.
    """
    # Step 1: Gather parts
    is_hcw = await _is_hcw(effector_type)
    gender = effector.gender if is_hcw else None
    et_terms = await _get_et_terms(effector_type, gender)

    zip_code = facility.zip or ""
    zip_short = zip_code[:2]
    zip_full = zip_code

    commune_name = ""
    communes = await facility.commune.all()
    if communes:
        commune_name = communes[0].name_fr or ""

    # Step 2: Location variants (no zip when commune is used)
    locations = []
    if zip_short:
        locations.append(zip_short)
    if commune_name:
        locations.append(commune_name)
    if zip_full and zip_full != zip_short:
        locations.append(zip_full)
    if not locations:
        locations.append("")

    # Step 3: Primary candidates
    # For HCW (physical persons): permute name variants (reversed, last-only)
    # For non-HCW (personne morale): use name as-is, no permutations
    if is_hcw:
        names = _all_name_variants(effector)
    else:
        names = [effector.name_fr]
        if effector.label_fr and effector.label_fr != effector.name_fr:
            names.append(effector.label_fr)
    candidates = _build_candidates(names, et_terms, locations)
    available = await _filter_existing_slugs(candidates)

    if is_hcw:
        # Fallback tier 1: last-name-only
        if len(available) < count:
            names_short = _all_name_variants(effector, include_last_only=True)
            # only the last-name-only variant (skip already-tried full variants)
            last_only = [v for v in names_short if v not in names]
            if last_only:
                extra = _build_candidates(last_only, et_terms, locations)
                extra = [s for s in extra if s not in set(available)]
                extra = await _filter_existing_slugs(extra)
                available.extend(extra)

    # Fallback tier 2: commune-zip combo
    if len(available) < count and commune_name and zip_short:
        combo_loc = [f"{commune_name} {zip_short}"]
        if is_hcw:
            all_names = _all_name_variants(effector, include_last_only=True)
        else:
            all_names = names
        extra = _build_candidates(all_names, et_terms, combo_loc)
        extra = [s for s in extra if s not in set(available)]
        extra = await _filter_existing_slugs(extra)
        available.extend(extra)

    # Fallback tier 3: street last word
    if len(available) < count and facility.street:
        street_parts = facility.street.strip().split()
        if street_parts:
            street_last = street_parts[-1]
            street_loc = [f"{street_last} {zip_short}"] if zip_short else [street_last]
            if is_hcw:
                all_names = _all_name_variants(effector, include_last_only=True)
            else:
                all_names = names
            extra = _build_candidates(all_names, et_terms, street_loc)
            extra = [s for s in extra if s not in set(available)]
            extra = await _filter_existing_slugs(extra)
            available.extend(extra)

    # Sort by length, trim
    available.sort(key=len)
    return available[:count]
