"""Compatibility shim for legacy imports.

Prefer importing from ``pce_api.main`` for stable package paths across platforms.
"""

from pce_api.main import app

__all__ = ["app"]
