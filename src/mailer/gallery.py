"""The images an organization links from its HTML emails.

Synchronous and free of HTTP; api.routers.email_images authorises, resolves
the organization and maps the exceptions to status codes. Every function
takes the organization, and looks images up within it only, so another
organization's image is indistinguishable from one that does not exist.
"""

import logging
from io import BytesIO
from pathlib import PurePath

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from PIL import Image, UnidentifiedImageError

from mailer.models import EmailImage

logger = logging.getLogger(__name__)

# PIL format -> extension. What every mail client shows; WebP is left out
# because Outlook for Windows does not render it.
FORMATS = {"JPEG": "jpg", "PNG": "png", "GIF": "gif"}
NAME_MAX_LENGTH = 200


class ImageInvalid(Exception):
    """code: too_large | unsupported_type | not_an_image | name_required"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class NameTaken(Exception):
    pass


def list_images(organization) -> list[EmailImage]:
    return list(EmailImage.objects.filter(organization=organization))


def _inspect(content: bytes) -> tuple[str, int, int]:
    """(extension, width, height), judged on the bytes alone."""
    if len(content) > settings.EMAIL_IMAGE_MAX_BYTES:
        raise ImageInvalid("too_large")
    try:
        with Image.open(BytesIO(content)) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ImageInvalid("not_an_image")
    if image_format not in FORMATS:
        raise ImageInvalid("unsupported_type")
    return FORMATS[image_format], width, height


def _free_name(organization, wanted: str) -> str:
    """wanted, or "wanted (2)", "wanted (3)"... the first not yet used."""
    taken = set(
        EmailImage.objects.filter(organization=organization, name__startswith=wanted)
        .values_list("name", flat=True)
    )
    name, n = wanted, 1
    while name in taken:
        n += 1
        name = f"{wanted} ({n})"
    return name


def add_image(organization, filename: str, content: bytes, *, name: str = "", alt: str = "") -> EmailImage:
    ext, width, height = _inspect(content)
    wanted = (name.strip() or PurePath(filename or "image").stem.strip() or "image")[:NAME_MAX_LENGTH]
    with transaction.atomic():
        image = EmailImage(
            organization=organization,
            name=_free_name(organization, wanted),
            alt=alt.strip(),
            width=width,
            height=height,
            size=len(content),
        )
        # The name given here only carries the extension: email_image_path
        # picks the stored name.
        image.image.save(f"upload.{ext}", ContentFile(content), save=False)
        image.save()
    return image


def update_image(organization, uid, *, name: str | None = None, alt: str | None = None) -> EmailImage:
    """Rename or re-describe. Never touches the file: sent emails link to it."""
    image = EmailImage.objects.get(organization=organization, uid=uid)
    if name is not None:
        name = name.strip()[:NAME_MAX_LENGTH]
        if not name:
            raise ImageInvalid("name_required")
        image.name = name
    if alt is not None:
        image.alt = alt.strip()
    try:
        with transaction.atomic():
            image.save(update_fields=["name", "alt"])
    except IntegrityError:
        raise NameTaken(name)
    return image


def delete_image(organization, uid) -> None:
    """Row, file and thumbnails: see mailer.models.delete_email_image_file."""
    EmailImage.objects.get(organization=organization, uid=uid).delete()


def image_urls(image: EmailImage, site_url: str) -> dict[str, str]:
    """path: for this site's pages; url and thumbnail_url: absolute, built
    from the site's public URL (base path included), for emails."""
    from easy_thumbnails.files import get_thumbnailer

    path = image.image.url
    try:
        thumbnail_path = get_thumbnailer(image.image)["email_thumb"].url
    except Exception as error:
        logger.warning(f"No thumbnail for email image {image.uid}: {error}")
        thumbnail_path = path
    return {
        "path": path,
        "url": f"{site_url}{path}",
        "thumbnail_url": f"{site_url}{thumbnail_path}",
    }
