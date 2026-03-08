from pathlib import Path

from saffier.contrib.admin.config import AdminConfig


def test_admin_config_template_directories():
    cfg = AdminConfig(admin_extra_templates=[Path("/tmp/one"), "/tmp/two"])
    directories = cfg.template_directories()
    assert directories[0] == "/tmp/one"
    assert directories[1] == "/tmp/two"
    assert directories[-1].endswith("contrib/admin/templates")
