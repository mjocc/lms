from django.apps import AppConfig


class LmsConfig(AppConfig):
    """App config for lms system, defining basic configuration data about app
    functionality."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "lms"

    def ready(self):
        """Imports signals file when app is ready to ensure the defined signals have
        been registered and will run when triggered."""

        # noinspection PyUnresolvedReferences
        from . import signals