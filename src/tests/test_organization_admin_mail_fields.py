"""The organization's mail settings can be edited in the Django admin.

OrganizationAdmin lists its fields explicitly, so a new model field is not
editable until it is added there. reply_to_email (where replies to the
organization's mail go) and batch_invitation_max_rows (rows per invitation
spreadsheet) were added to the model without it, and could not be set.
"""
from facility.admin import OrganizationAdmin


def test_the_reply_address_is_editable():
    assert "reply_to_email" in OrganizationAdmin.fields


def test_the_batch_limit_is_editable():
    assert "batch_invitation_max_rows" in OrganizationAdmin.fields
