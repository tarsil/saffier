from saffier.core.terminal.print import Print
from saffier.core.terminal.terminal import Terminal


def test_print_wrapper_methods(monkeypatch):
    printer = Print()
    captured: list[str] = []
    monkeypatch.setattr(printer, "print", lambda message: captured.append(message))

    printer.write_success("ok")
    printer.write_info("info")
    printer.write_warning("warn")
    printer.write_error("err")
    printer.write_plain("plain")

    assert len(captured) == 5


def test_terminal_wrapper_methods_return_message():
    terminal = Terminal()
    assert isinstance(terminal.write_success("ok"), str)
    assert isinstance(terminal.write_info("info"), str)
    assert isinstance(terminal.write_warning("warn"), str)
    assert isinstance(terminal.write_error("err"), str)
    assert isinstance(terminal.write_plain("plain"), str)
