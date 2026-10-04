"""Collection into ``CollectedDocument`` records.

Workbook import is the guaranteed baseline. YouTube comment collection is a
separate read-only path in ``youtube.py`` and does not classify or extract.
"""

from src.collect.workbook import import_workbook

__all__ = ["import_workbook"]
