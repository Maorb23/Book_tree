from django.apps import AppConfig


class TreeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tree'

    def ready(self):
        from . import signals  # noqa: F401
