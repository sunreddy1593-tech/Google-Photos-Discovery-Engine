"""Shared model configuration.

Every contract in this package inherits :class:`ResearchModel`, so three
properties hold corpus-wide rather than per file.

**``extra="forbid"``.** An unrecognised key is a rejection, not a silently
retained extra. This is what makes "``CollectedDocument`` carries no
``normalized_text``" and "``RetrievalCase`` carries no ``candidate_cluster``"
testable as behaviour rather than as an absence in a field list: passing the
field raises. Spec Sections 15.1 and 15.4 remove those fields for real reasons,
and a permissive model would let a later stage put them back by accident.

**``frozen=True`` with tuple sequences.** Records are written once. Invariant I1
says raw text is never updated and all cleaning produces derived records; freezing
the models means an in-place edit fails at the point of the edit rather than
surfacing as an unexplained value change three stages later. Sequence fields are
``tuple`` rather than ``list`` so the freeze is not defeated by mutating a list
the model happens to hold.

**Timezone-aware datetimes only.** A naive timestamp is ambiguous the moment two
sources disagree about local time, and the corpus spans platforms in several
regions. Importers attach the zone at the boundary.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from src.core.versions import SCHEMA_VERSION


class ResearchModel(BaseModel):
    """Base for every research contract."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        str_strip_whitespace=False,
        use_enum_values=False,
    )


class VersionedModel(ResearchModel):
    """A contract that stamps the schema version that produced it.

    Defaulted rather than required so a caller cannot stamp a version the code
    did not produce, and present on every record so a corpus containing two
    schema generations can be read without guessing which is which
    (spec Section 15, invariant I7).
    """

    schema_version: str = Field(
        default=SCHEMA_VERSION,
        min_length=1,
        description="Contract version that produced this record.",
    )


#: Fields whose absence must be expressed as ``None`` plus an observation status,
#: never as a placeholder string. Referenced by the models' docstrings and by
#: ``tests/test_models.py``; see spec Section 16.9 and invariant I6.
FORBIDDEN_PLACEHOLDER_VALUES: Final[frozenset[str]] = frozenset(
    {"unknown", "none_stated", "n/a", "na", "null", "none", "unspecified"}
)
