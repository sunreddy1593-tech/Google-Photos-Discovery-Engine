"""Version registry.

Every versioned string the pipeline stamps onto a record lives here, so a bump is
one edit in one file and the cache-key consequences are visible beside the value.

Which versions enter which cache key and fingerprint is not uniform, and the
asymmetry is deliberate (spec Sections 19.5, 26.2; ADR-19):

    decision_fingerprint    model, prompt, ruleset, schema, content
    extraction_fingerprint  model, prompt,          schema, content
    assignment_fingerprint  model, prompt,          schema, content, TAXONOMY

``TAXONOMY_VERSION`` appears in exactly one fingerprint and in exactly two cache
keys (taxonomy candidate generation and taxonomy assignment). It is absent from
prefilter, relevance, extraction, and Ask synthesis. Extraction never reads the
taxonomy, so including it there would invalidate every cached extraction on a
taxonomy bump and force a full paid re-run to produce identical output.
"""

from __future__ import annotations

from typing import Final

#: Contract version stamped onto every record. Bump when any contract in spec
#: Section 15 changes shape. Participates in all three fingerprints.
SCHEMA_VERSION: Final[str] = "1.0.0"

#: Deterministic rule logic: the prefilter and the scope-class rules in
#: ``src/relevance/rules.py``. Participates in ``decision_fingerprint`` only.
RULESET_VERSION: Final[str] = "1.0.0"

#: Text normalization and length-preserving redaction (spec Section 15.6).
#: Stamped onto ``DocumentDerived``. Deliberately absent from every cache key:
#: model calls key on ``content_hash``, which already moves when normalization
#: changes the canonical text.
NORMALIZER_VERSION: Final[str] = "1.0.0"

#: Near-duplicate ruleset: 64-bit simhash, 3-word shingles, thresholds from
#: ``config/analysis.yaml``. Stamped onto ``DuplicateLink.method_version``.
DEDUPE_VERSION: Final[str] = "1.0.0"

#: The taxonomy does not exist yet and must not before the pilot review
#: (spec Section 20, invariant I10). ``config/taxonomy.yaml`` ships with this
#: same sentinel and an empty cluster list. Phase 8 replaces it.
TAXONOMY_VERSION: Final[str] = "0-unassigned"

#: Per-prompt versions, keyed by prompt id. A prompt edit bumps its own entry and
#: invalidates only its own cache, which is why these are separate from
#: ``SCHEMA_VERSION`` rather than folded into it.
#:
#: Empty at Phase 0: no prompt exists yet. Phase 4 adds ``relevance``, Phase 5
#: adds ``extraction``, Phase 8 adds the taxonomy prompts, Phase 9 adds ``ask``.
PROMPT_VERSIONS: Final[dict[str, str]] = {}


def prompt_version(prompt_id: str) -> str:
    """Return the registered version for ``prompt_id``.

    Raises ``KeyError`` rather than defaulting to ``"1.0.0"``. An unregistered
    prompt silently defaulting would produce a cache key that does not move when
    the prompt changes, which is the one failure the registry exists to prevent.
    """
    return PROMPT_VERSIONS[prompt_id]


def version_summary() -> dict[str, object]:
    """Versions as recorded in the run manifest (spec Section 26)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "ruleset_version": RULESET_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "prompt_versions": dict(PROMPT_VERSIONS),
    }
