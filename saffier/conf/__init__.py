import os

os.environ.setdefault("OVERRIDE_SETTINGS_MODULE_VARIABLE", "SAFFIER_SETTINGS_MODULE")

if not os.environ.get("SAFFIER_SETTINGS_MODULE"):
    os.environ.setdefault(
        "SAFFIER_SETTINGS_MODULE", "saffier.conf.global_settings.SaffierSettings"
    )

from dymmond_settings import settings as settings  # noqa
