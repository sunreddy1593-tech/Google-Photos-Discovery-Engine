"""Read-only local evidence browser. No provider calls and no writes."""

from src.browse.snapshot import BrowserPaths, build_snapshot

__all__ = ["BrowserPaths", "build_snapshot"]
