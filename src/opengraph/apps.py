from django.apps import AppConfig


class OpengraphConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'opengraph'

    def ready(self):
        from opengraph import cache  # noqa: F401  registers the cache receivers
