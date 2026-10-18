"""Local credential detection and explicit sensitive-file policy."""

from seam.security.content import contains_secret
from seam.security.paths import is_sensitive_path

__all__ = ["contains_secret", "is_sensitive_path"]
