"""Domain exceptions for dairytools library modules.

Library functions raise subclasses of `DairyToolsError` instead of `SystemExit`, so Python callers can catch and
handle errors cleanly while `cli.py` translates them into user-facing exit messages.
"""

from __future__ import annotations


class DairyToolsError(Exception):
    """Base error for all dairytools operations."""


class FolderNotFoundError(DairyToolsError):
    """The export folder does not exist or is not a directory."""


class MissingDataError(DairyToolsError):
    """A required report, column, or sufficient observation window is missing."""


class NotFoundError(DairyToolsError):
    """A requested pen, cow, or column was not found in the herd."""
