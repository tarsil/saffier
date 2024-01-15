import os

try:
    from dymmond_settings import settings as settings
except ModuleNotFoundError:
    os.environ.setdefault("SETTINGS_MODULE", "saffier.conf.global_settings.SaffierSettings")
    from dymmond_settings import settings as settings
