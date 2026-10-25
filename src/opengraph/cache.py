from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from opengraph.models import TwitterCard


def opengraph_cache_key(domain: str) -> str:
    # By domain, not site id: the test database's ids can match real sites' in
    # the shared Redis, its domain (testserver) cannot.
    return f"v2:opengraph:{domain}"


@receiver(post_save, sender=TwitterCard)
@receiver(post_delete, sender=TwitterCard)
def clear_opengraph_cache(sender, instance: TwitterCard, **kwargs):
    cache.delete(opengraph_cache_key(instance.site.domain))
