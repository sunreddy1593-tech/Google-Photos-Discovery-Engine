"""`ClusterAssignment` — taxonomy assignment (spec Section 15.9).

The only contract that carries ``taxonomy_version``, and the only place a cluster
label may exist at all (invariant I10).

Both restrictions are the same decision seen from two sides. Putting a cluster on
the extraction record would make extraction depend on a taxonomy that spec
Section 20 forbids until after pilot review, and it would mean a taxonomy
revision invalidated every cached extraction — re-running the whole corpus
through a paid model to produce byte-identical extractions, because extraction
never reads the taxonomy. That is not merely wasteful: it creates a standing
financial reason not to revise the taxonomy, in direct opposition to the
requirement that the taxonomy be refined against evidence (ADR-19).

Keyed by ``(case_id, taxonomy_version, assignment_fingerprint)``, so re-assigning
under a revised taxonomy adds rows and preserves earlier versions.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field, model_validator

from src.models.base import VersionedModel
from src.models.enums import AssignmentMethod


class ClusterAssignment(VersionedModel):
    """One case's membership in one cluster of one taxonomy version."""

    case_id: str = Field(min_length=1)
    taxonomy_version: str = Field(
        min_length=1,
        description=(
            "Part of the key. Phase 0 ships '0-unassigned' and Phase 8 replaces "
            "it; no cluster may be named before the pilot review."
        ),
    )
    cluster_id: str = Field(
        min_length=1,
        description=(
            "Assigned cluster, including the permanent 'other' and 'uncertain' "
            "members."
        ),
    )
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    method: AssignmentMethod
    model_name: str | None = None
    prompt_version: str | None = None
    assignment_fingerprint: str = Field(
        min_length=1,
        description=(
            "Spec Section 26.2. The only fingerprint that includes "
            "taxonomy_version."
        ),
    )
    assigned_at: AwareDatetime

    @model_validator(mode="after")
    def _check_provenance(self) -> "ClusterAssignment":
        if self.method is AssignmentMethod.llm:
            missing = [
                name
                for name, value in (
                    ("model_name", self.model_name),
                    ("prompt_version", self.prompt_version),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"method=llm requires {', '.join(missing)} (invariant I7)"
                )
        elif self.model_name:
            raise ValueError(
                f"method={self.method.value} must leave model_name null"
            )
        return self

    @property
    def key(self) -> tuple[str, str, str]:
        """Primary key: ``(case_id, taxonomy_version, assignment_fingerprint)``."""
        return (self.case_id, self.taxonomy_version, self.assignment_fingerprint)
