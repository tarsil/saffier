from saffier.core.terminal.base import Base, OutputColour


class Terminal(Base):
    """Terminal helper that returns styled strings instead of printing them."""

    def write_success(
        self,
        message: str,
        colour: str = OutputColour.SUCCESS,
    ) -> str:
        """Return a styled success message."""
        message = self.message(message, colour)
        return message

    def write_info(
        self,
        message: str,
        colour: str = OutputColour.INFO,
    ) -> str:
        """Return a styled informational message."""
        message = self.message(message, colour)
        return message

    def write_warning(
        self,
        message: str,
        colour: str = OutputColour.WARNING,
    ) -> str:
        """Return a styled warning message."""
        message = self.message(message, colour)
        return message

    def write_error(
        self,
        message: str,
        colour: str = OutputColour.ERROR,
    ) -> str:
        """Return a styled error message."""
        message = self.message(message, colour)
        return message

    def write_plain(self, message: str, colour: str = OutputColour.WHITE) -> str:
        message = self.message(message, colour)
        return message
