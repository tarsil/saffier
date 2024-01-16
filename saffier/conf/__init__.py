import os

if not os.environ.get("SETTINGS_MODULE"):
    os.environ.setdefault("SETTINGS_MODULE", "saffier.conf.global_settings.SaffierSettings")
from dymmond_settings import settings as settings
