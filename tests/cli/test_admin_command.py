from tests.cli.utils import run_cmd


def test_admin_command_is_exposed():
    output, _, status = run_cmd("tests.cli.main:app", "saffier --help")
    text = output.decode("utf-8")

    assert status == 0
    assert "admin_serve" in text
