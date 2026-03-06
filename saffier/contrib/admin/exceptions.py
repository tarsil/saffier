class AdminError(Exception):
    """Base admin exception."""


class AdminModelNotFound(AdminError):
    """Raised when the admin requests an unknown model."""


class AdminValidationError(AdminError):
    """Raised when payload validation fails."""

    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__("Payload validation failed.")
