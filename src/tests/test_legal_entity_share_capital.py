"""A legal entity's share capital is a number, as the column is.

The API type said str, which held only while every row left it empty: the first
organization with a capital (msp-vedene, 300) made /api/v2/organization answer
500 on every page of its site.
"""
from api.types.organization import LegalEntity


def test_a_share_capital_validates():
    entity = LegalEntity(
        id=1, name="MSP", type="SISA", get_type_display="SISA", RNA=None,
        SIREN="893932160", SIRET="89393216000011", RCS="Avignon D 893932160",
        SHARE_CAPITAL=300, VAT="FR50893932160",
    )
    assert entity.SHARE_CAPITAL == 300
