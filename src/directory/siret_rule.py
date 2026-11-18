"""An establishment's SIRET starts with the SIREN of the legal unit that runs it.

The SIRET is the SIREN followed by a 5-digit number, so when an entry is run by a
porteur that has a SIREN and sits at a facility that has a SIRET the two must
agree. Only the entry's own porteur (RUN_BY) is looked at, never a chain, and
nothing is checked while either number is missing: an entry may be entered before
its identifiers are known.

Three writes can break it, so each asks here first and refuses with nothing
written: attaching an entry to a porteur, giving a facility a SIRET, giving a
porteur a SIREN.
"""
from api.graph import read


class SiretMismatch(Exception):
    """A SIRET and the SIREN of the porteur that runs its entry do not agree."""


async def run_by_disagrees(entry_uid: str, porteur_uid: str) -> bool:
    """Whether the entry's facility SIRET does not start with the porteur's SIREN."""
    rows = await read(
        """
        MATCH (e:Entry {uid: $entry})-[:HAS_FACILITY]->(f:Facility), (p:Entry {uid: $porteur})
        WHERE f.siret IS NOT NULL AND p.siren IS NOT NULL AND NOT f.siret STARTS WITH p.siren
        RETURN count(*) AS n
        """,
        entry=entry_uid,
        porteur=porteur_uid,
    )
    return bool(rows[0]["n"])


async def check_facility_siret(facility_uid: str, siret: str | None) -> None:
    """Raise unless `siret` agrees with the porteur of every entry at the facility."""
    if siret is None:
        return
    rows = await read(
        """
        MATCH (:Facility {uid: $facility})<-[:HAS_FACILITY]-(:Entry)-[:RUN_BY]->(p:Entry)
        WHERE p.siren IS NOT NULL AND NOT $siret STARTS WITH p.siren
        RETURN count(*) AS n
        """,
        facility=facility_uid,
        siret=siret,
    )
    if rows[0]["n"]:
        raise SiretMismatch("The SIRET does not start with the SIREN of the porteur that runs an entry here")


async def check_siren(entry_uid: str, siren: str | None) -> None:
    """Raise unless `siren` agrees with the SIRET of every service this entry runs."""
    if siren is None:
        return
    rows = await read(
        """
        MATCH (:Entry {uid: $entry})<-[:RUN_BY]-(:Entry)-[:HAS_FACILITY]->(f:Facility)
        WHERE f.siret IS NOT NULL AND NOT f.siret STARTS WITH $siren
        RETURN count(*) AS n
        """,
        entry=entry_uid,
        siren=siren,
    )
    if rows[0]["n"]:
        raise SiretMismatch("The SIREN does not agree with the SIRET of a service this entry runs")
