"""Project error types."""

INVALID_SLIDE = "INVALID_SLIDE"


class AgentSlidesError(Exception):
    """Base project exception with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return self.message
