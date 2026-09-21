"""Canonical content hashing for rebuild equality (spec Section 26.4, ADR-26).

``main.py rebuild`` asserts **identical canonical content hashes** for every
exported artifact. It does not assert byte-identical run manifests.

A manifest legitimately differs between runs: new run id, new timestamps, new
durations, possibly a different git commit, possibly different token counts
because some responses came from cache. Requiring byte equality would fail for
reasons unrelated to the data, and the predictable response to a test that cries
wolf is to weaken or skip it — at which point genuine non-determinism stops being
caught, which is the entire purpose of the check.

So artifacts are canonicalized first: records sorted by primary key, object keys
sorted, numbers normalized, and the volatile fields below removed. The exclusion
list is itself written into the manifest, so a reader knows exactly what was and
was not compared — otherwise the equality claim is unfalsifiable.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterable, Mapping, Sequence

#: Field names removed before hashing (spec Section 26.4, ARCHITECTURE 8.2).
#:
#: A naming collision worth stating, because getting it wrong would be silent and
#: damaging: the spec excludes LLM *usage* token counts, and this set therefore
#: names them precisely (``prompt_tokens``, ``total_tokens``, ...). It must never
#: contain ``token_count``, which is a genuine data field on ``DocumentDerived``
#: that the deduplication minimum-length rule reads (spec Section 19.6). Removing
#: it would drop a real value from the comparison and let non-determinism in
#: tokenization pass unnoticed.
VOLATILE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        # Run identity, and anything derived from it
        "run_id",
        "parent_run_id",
        # Execution timestamps. NOT collected_at or published_at: those are
        # properties of the document, not of the run, so they are data.
        "occurred_at",
        "derived_at",
        "decided_at",
        "extracted_at",
        "assigned_at",
        "validated_at",
        "reviewed_at",
        "exported_at",
        "cached_at",
        "run_started_at",
        "run_completed_at",
        "started_at",
        "completed_at",
        "generated_at",
        # Wall-clock durations and latencies
        "duration_ms",
        "duration_s",
        "elapsed_ms",
        "latency_ms",
        # LLM usage and cost — never DocumentDerived.token_count (see above)
        "prompt_tokens",
        "completion_tokens",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "tokens_used",
        "request_count",
        "api_call_count",
        "cost_usd",
        "cost_estimate_usd",
        # Execution environment
        "hostname",
        "pid",
        "process_id",
        "local_path",
        "absolute_path",
        "output_path",
        "cwd",
        # Cache provenance, not cache content
        "cache_hit",
        "cache_status",
        "from_cache",
    }
)


def _normalize(value: Any) -> Any:
    """Recursively drop volatile keys, sort mapping keys, normalize numbers.

    Integral floats become ints so ``1.0`` and ``1`` compare equal: a JSON
    round-trip can legitimately change which one a number is, and that difference
    is not a data difference.
    """
    if isinstance(value, Mapping):
        return {
            k: _normalize(v)
            for k, v in sorted(value.items())
            if k not in VOLATILE_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, bool):
        return value  # before the int branch: bool is a subclass of int
    if isinstance(value, float):
        if value == 0.0:
            return 0  # collapses -0.0
        if value.is_integer():
            return int(value)
        return value
    return value


def canonical_json(value: Any) -> str:
    """Canonical JSON text for ``value``, volatile fields removed."""
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def content_equivalence_hash(value: Any) -> str:
    """SHA-256 over :func:`canonical_json` of ``value``.

    Two runs producing the same hash agree on every non-volatile field. A
    mismatch means non-determinism leaked into the data and must be investigated;
    a difference confined to volatile fields just means a second run happened.
    """
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def artifact_hash(
    records: Iterable[Mapping[str, Any]], primary_key: str | Sequence[str]
) -> str:
    """Content-equivalence hash of a record collection, order-independent.

    Records are sorted by ``primary_key`` before hashing, so two runs that emit
    the same records in a different order still agree. Export order is not data.
    """
    keys = (primary_key,) if isinstance(primary_key, str) else tuple(primary_key)
    materialized = list(records)

    for record in materialized:
        missing = [k for k in keys if k not in record]
        if missing:
            raise KeyError(
                f"record is missing primary-key field(s) {missing}; "
                f"cannot order artifact deterministically"
            )

    ordered = sorted(
        materialized, key=lambda r: tuple(str(r[k]) for k in keys)
    )
    return content_equivalence_hash(ordered)


def exclusion_list() -> list[str]:
    """Sorted volatile-field list, for recording in the run manifest.

    Required by spec Section 26 so a reader comparing two runs can tell which
    fields were compared and which were deliberately ignored.
    """
    return sorted(VOLATILE_FIELDS)
