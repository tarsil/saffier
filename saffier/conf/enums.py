from enum import Enum


class EnvironmentType(str, Enum):
    """Deployment environments recognized by Saffier settings objects."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"
