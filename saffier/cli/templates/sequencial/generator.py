import os
import re

MIGRATIONS_DIR = "migrations/versions"
FILENAME_PATTERN = re.compile(r"(\\d{4})_(.*)\\.py")


def get_next_migration_number() -> int:
    """
    Returns the next sequential migration number based on existing files.
    """
    existing_files = os.listdir(MIGRATIONS_DIR)
    numbers = [
        int(match.group(1))
        for filename in existing_files
        if (match := FILENAME_PATTERN.match(filename))
    ]
    return max(numbers, default=0) + 1


def create_migration_filename(slug: str | None = None, with_extension: bool = False) -> str:
    """
    Creates a migration revision id with a zero-padded sequential number.
    """
    next_number = get_next_migration_number()
    if slug is None:
        return f"{next_number:04d}_"
    return f"{next_number:04d}_{slug}" if with_extension else f"{next_number:04d}"
