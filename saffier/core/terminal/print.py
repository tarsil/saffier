from saffier.core.terminal.base import Base, OutputColour


class Print(Base):
    """Terminal writer that prints styled messages immediately."""

    def write_success(
        self,
        message: str,
        colour: str = OutputColour.SUCCESS,
    ) -> None:
        """Print a success message to the console."""
        message = self.message(message, colour)
        self.print(message)

    def write_info(self, message: str, colour: str = OutputColour.INFO) -> None:
        """Print an informational message to the console."""
        message = self.message(message, colour)
        self.print(message)

    def write_warning(
        self,
        message: str,
        colour: str = OutputColour.WARNING,
    ) -> None:
        """Print a warning message to the console."""
        message = self.message(message, colour)
        self.print(message)

    def write_plain(self, message: str, colour: str = OutputColour.WHITE) -> None:
        message = self.message(message, colour)
        self.print(message)

    def write_error(
        self,
        message: str,
        colour: str = OutputColour.ERROR,
    ) -> None:
        """Print an error message to the console."""
        message = self.message(message, colour)
        self.print(message)
