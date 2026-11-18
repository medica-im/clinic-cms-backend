"""SIREN and SIRET, the identifiers of the French register of companies.

A SIREN (9 digits) names a legal unit, a SIRET (14 digits) one of its
establishments: the SIREN followed by a 5-digit NIC. Both end in a Luhn check
digit, so a typo is caught before it is stored.
"""

LA_POSTE = "356000000"


def normalize(value: str | None) -> str | None:
    """The number without its spaces ("441 921 913" is written that way on the
    register's pages); None when nothing is left."""
    if value is None:
        return None
    digits = "".join(value.split())
    return digits or None


def _luhn(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        n = int(char)
        if position % 2:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def is_siren(value: str | None) -> bool:
    return bool(value) and len(value) == 9 and value.isascii() and value.isdigit() and _luhn(value)


def is_siret(value: str | None) -> bool:
    if not value or len(value) != 14 or not value.isascii() or not value.isdigit():
        return False
    if value.startswith(LA_POSTE):
        # The register's one exception: La Poste's SIRETs are valid when their
        # digits add up to a multiple of 5, whatever the Luhn check says.
        return sum(int(c) for c in value) % 5 == 0
    return _luhn(value)


def siren_of(siret: str | None) -> str | None:
    """The legal unit a SIRET belongs to: its first nine digits."""
    return siret[:9] if siret and len(siret) == 14 and siret.isdigit() else None
