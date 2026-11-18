"""One-off corrections to data already in the graph, run by migrations."""
from neomodel import db

from directory.models.core import sync_clear_cache


def null_zero_facility_locations() -> int:
    """Remove the point from every facility stored at 0/0.

    0/0 was what the facility forms sent when nobody placed the facility; it
    means "unknown", and unknown is no point at all.
    """
    rows, _ = db.cypher_query(
        """
        MATCH (f:Facility)
        WHERE f.location.x = 0 AND f.location.y = 0
        REMOVE f.location
        RETURN count(f)
        """
    )
    count = rows[0][0]
    if count:
        for endpoint in ("v1:facilities", "v2:public/facilities", "v2:entries"):
            sync_clear_cache(endpoint)
    return count


def null_blank_facility_ban_ids() -> int:
    """Store null where a facility's BAN id is an empty string.

    The facility forms sent "" when the geocoder was not used; it meant no id.
    """
    rows, _ = db.cypher_query(
        """
        MATCH (f:Facility)
        WHERE f.ban_id = "" OR f.ban_banId = ""
        SET f.ban_id = CASE WHEN f.ban_id = "" THEN null ELSE f.ban_id END,
            f.ban_banId = CASE WHEN f.ban_banId = "" THEN null ELSE f.ban_banId END
        RETURN count(f)
        """
    )
    count = rows[0][0]
    if count:
        for endpoint in ("v1:facilities", "v2:public/facilities"):
            sync_clear_cache(endpoint)
    return count


def fill_two_state_booleans() -> tuple[int, int]:
    """Store the default where a two-state boolean has no value.

    neomodel applies a default when it saves a node, so nodes written before the
    property existed, or by Cypher, had none. Readers take a missing value as the
    default (`coalesce(t.immaterial, false)`), so what is displayed does not change
    and no cache needs clearing. Not the entry facets: for those null is unknown.

    Returns the effector types and the directories it filled.
    """
    types, _ = db.cypher_query(
        """
        MATCH (t:EffectorType) WHERE t.immaterial IS NULL
        SET t.immaterial = false
        RETURN count(t)
        """
    )
    directories, _ = db.cypher_query(
        """
        MATCH (d:Directory) WHERE d.list_owner_entry IS NULL
        SET d.list_owner_entry = true
        RETURN count(d)
        """
    )
    return types[0][0], directories[0][0]


def unset_empty_effector_type_synonyms() -> int:
    """Remove `synonyms_fr` and `synonyms_en` where an effector type stores `[]`.

    The console sent `[]` on every create and the API stored it; no synonyms is now
    no property. Readers take both as none, so what is displayed does not change and
    no cache needs clearing. Only effector types: conditions, situations and needs
    get their synonyms from other APIs.

    Returns the effector types it changed.
    """
    rows, _ = db.cypher_query(
        """
        MATCH (t:EffectorType) WHERE t.synonyms_fr = [] OR t.synonyms_en = []
        WITH t, t.synonyms_fr = [] AS fr, t.synonyms_en = [] AS en
        FOREACH (_ IN CASE WHEN fr THEN [1] ELSE [] END | REMOVE t.synonyms_fr)
        FOREACH (_ IN CASE WHEN en THEN [1] ELSE [] END | REMOVE t.synonyms_en)
        RETURN count(t)
        """
    )
    return rows[0][0]
