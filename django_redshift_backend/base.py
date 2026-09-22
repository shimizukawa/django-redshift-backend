"""Public Django database backend entry point.

Version 6 activates the official Amazon Redshift Python connector backend while
retaining ``ENGINE = "django_redshift_backend"`` for existing settings.
"""

from ._backend import DatabaseWrapper
from .meta import DistKey, SortKey

__all__ = ["DatabaseWrapper", "DistKey", "SortKey"]
