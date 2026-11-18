"""The images an organization puts in its emails.

An HTML email cannot carry its pictures on the page it is built in: it
references them by absolute URL, and the recipient's client downloads them.
So each organization gets a gallery on its own site -- upload, rename,
delete, and copy the URL into the template.

* Files live under email_images/<organization>/, one directory per
  organization, and are never shared.
* Each file gets a random name. A rename changes only the label shown in the
  gallery, never the file: emails already sent point at the URL forever.
* JPEG, PNG and GIF only, checked on the bytes, not on the declared type.
  WebP is left out on purpose: Outlook for Windows does not render it.
* The URL is absolute and built from the site's public URL, so it includes
  the base path of a site like unipa.fr/annuaire.
* Deleting removes the row, the file and its thumbnails.
* Another organization's image does not exist, as far as the caller knows.

The API router (api.routers.email_images) is a thin shell over mailer.gallery,
tested in tests/api/test_email_images_api.py.
"""

import io
import os
import uuid

import pytest
from PIL import Image

from facility.models import Organization
from mailer.gallery import (
    ImageInvalid,
    NameTaken,
    add_image,
    delete_image,
    image_urls,
    list_images,
    update_image,
)
from mailer.models import EmailImage

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def _png(width=120, height=40, fmt="PNG"):
    buffer = io.BytesIO()
    mode = "P" if fmt == "GIF" else "RGB"
    Image.new(mode, (width, height)).save(buffer, format=fmt)
    return buffer.getvalue()


def _org(name="Cabinet", **fields):
    return Organization.objects.create(name=name, neomodel_uid=uuid.uuid4(), **fields)


# --- Uploading ----------------------------------------------------------------


def test_an_upload_is_stored_under_the_organizations_directory(media_root):
    org = _org()

    image = add_image(org, "logo.png", _png())

    assert image.image.name.startswith(f"email_images/{org.neomodel_uid.hex}/")
    assert os.path.exists(media_root / image.image.name)


def test_an_upload_records_what_an_img_tag_needs():
    image = add_image(_org(), "logo.png", _png(120, 40))

    assert (image.width, image.height) == (120, 40)
    assert image.name == "logo"


def test_two_uploads_of_the_same_file_do_not_share_a_path():
    org = _org()

    first = add_image(org, "logo.png", _png())
    second = add_image(org, "logo.png", _png())

    assert first.image.name != second.image.name
    assert second.name == "logo (2)"


def test_two_organizations_never_share_a_directory():
    a = add_image(_org("A"), "logo.png", _png())
    b = add_image(_org("B"), "logo.png", _png())

    assert os.path.dirname(a.image.name) != os.path.dirname(b.image.name)


def test_an_organization_without_a_graph_uid_still_gets_its_own_directory():
    org = Organization.objects.create(name="No uid")

    image = add_image(org, "logo.png", _png())

    assert image.image.name.startswith(f"email_images/org-{org.id}/")


def test_the_extension_comes_from_the_bytes_not_the_filename():
    image = add_image(_org(), "picture.png", _png(fmt="JPEG"))

    assert image.image.name.endswith(".jpg")


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "GIF"])
def test_the_formats_every_mail_client_shows_are_accepted(fmt):
    add_image(_org(), f"x.{fmt.lower()}", _png(fmt=fmt))


def test_webp_is_refused():
    with pytest.raises(ImageInvalid) as caught:
        add_image(_org(), "x.webp", _png(fmt="WEBP"))

    assert caught.value.code == "unsupported_type"


def test_a_file_that_is_not_an_image_is_refused():
    with pytest.raises(ImageInvalid) as caught:
        add_image(_org(), "fake.png", b"\x89PNG\r\n\x1a\nnot really")

    assert caught.value.code == "not_an_image"


def test_a_file_over_the_size_limit_is_refused(settings):
    settings.EMAIL_IMAGE_MAX_BYTES = 100

    with pytest.raises(ImageInvalid) as caught:
        add_image(_org(), "logo.png", _png(400, 400))

    assert caught.value.code == "too_large"
    assert not EmailImage.objects.exists()


# --- Listing ------------------------------------------------------------------


def test_the_list_holds_only_the_organizations_own_images():
    mine, theirs = _org("Mine"), _org("Theirs")
    add_image(mine, "a.png", _png())
    add_image(theirs, "b.png", _png())

    assert [i.name for i in list_images(mine)] == ["a"]


def test_the_list_shows_the_newest_first():
    org = _org()
    add_image(org, "old.png", _png())
    add_image(org, "new.png", _png())

    assert [i.name for i in list_images(org)] == ["new", "old"]


# --- Renaming -----------------------------------------------------------------


def test_a_rename_changes_the_label_and_never_the_file():
    org = _org()
    image = add_image(org, "logo.png", _png())
    path_before = image.image.name

    renamed = update_image(org, image.uid, name="Logo du cabinet", alt="Logo")

    assert renamed.name == "Logo du cabinet"
    assert renamed.alt == "Logo"
    assert renamed.image.name == path_before


def test_a_rename_to_a_name_already_used_is_refused():
    org = _org()
    add_image(org, "logo.png", _png())
    other = add_image(org, "banner.png", _png())

    with pytest.raises(NameTaken):
        update_image(org, other.uid, name="logo")


def test_the_same_name_is_free_in_another_organization():
    add_image(_org("A"), "logo.png", _png())

    assert add_image(_org("B"), "logo.png", _png()).name == "logo"


def test_another_organizations_image_cannot_be_renamed():
    image = add_image(_org("A"), "logo.png", _png())

    with pytest.raises(EmailImage.DoesNotExist):
        update_image(_org("B"), image.uid, name="mine now")


# --- Deleting -----------------------------------------------------------------


def test_deleting_removes_the_row_the_file_and_the_thumbnails(media_root):
    org = _org()
    image = add_image(org, "logo.png", _png())
    urls = image_urls(image, "https://example.org")  # generates the thumbnail
    thumbnail_dir = media_root / os.path.dirname(image.image.name)
    assert len(os.listdir(thumbnail_dir)) >= 2, "no thumbnail was generated"

    delete_image(org, image.uid)

    assert not EmailImage.objects.exists()
    assert os.listdir(thumbnail_dir) == [], urls


def test_another_organizations_image_cannot_be_deleted():
    image = add_image(_org("A"), "logo.png", _png())

    with pytest.raises(EmailImage.DoesNotExist):
        delete_image(_org("B"), image.uid)

    assert EmailImage.objects.filter(pk=image.pk).exists()


def test_deleting_an_organization_removes_its_files(media_root):
    org = _org()
    image = add_image(org, "logo.png", _png())

    org.delete()

    assert not os.path.exists(media_root / image.image.name)


# --- URLs ---------------------------------------------------------------------


def test_the_url_is_absolute_on_a_root_site():
    image = add_image(_org(), "logo.png", _png())

    urls = image_urls(image, "https://annuaire.example.org")

    assert urls["url"] == f"https://annuaire.example.org/media/{image.image.name}"
    assert urls["path"] == f"/media/{image.image.name}"


def test_the_url_keeps_the_base_path_of_a_site_served_under_one():
    image = add_image(_org(), "logo.png", _png())

    urls = image_urls(image, "https://example.org/annuaire")

    assert urls["url"] == f"https://example.org/annuaire/media/{image.image.name}"


def test_the_thumbnail_is_served_from_the_site_too():
    image = add_image(_org(), "logo.png", _png(800, 400))

    urls = image_urls(image, "https://example.org/annuaire")

    assert urls["thumbnail_url"].startswith("https://example.org/annuaire/media/email_images/")
    assert urls["thumbnail_url"] != urls["url"]
