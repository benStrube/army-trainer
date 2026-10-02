"""Indexes built from the document tree (WP 1.4). Read-only consumers of the tree."""

from .build import build_indexes, write_indexes

__all__ = ["build_indexes", "write_indexes"]
