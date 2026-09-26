"""Manual collection, the guaranteed baseline path (spec Section 11.4).

The workbook importer lives here. CSV/JSONL import, the SQLite store, and
stage-event emission are the rest of Phase 2 and are not imported by this
package, so a workbook can become a ``CollectedDocument`` with no Phase 3
module present.
"""

from src.collect.workbook import import_workbook

__all__ = ["import_workbook"]
