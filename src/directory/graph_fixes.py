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
