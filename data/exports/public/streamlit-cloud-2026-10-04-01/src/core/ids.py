"""Deterministic identifiers, hashes, and cache keys.

Every identifier here is a pure function of content or of stable source keys.
None derives from insertion order, autoincrement, or wall-clock time, which is
what lets a re-run produce identical IDs (spec Section 26.1, ARCHITECTURE
Section 7).

The load-bearing constraint is in ``doc_id``: it takes no ``content_hash``
argument, so an import-time identifier cannot come to depend on a Phase 3 value.
See that function's docstring.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from typing import Any, Final, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SEP: Final[str] = "|"

#: Query parameters dropped by :func:`source_url_key`. Campaign and referrer
#: tags only — nothing that identifies *which* item is being addressed. YouTube's
#: ``v`` and ``lc`` and Reddit's path segments must survive, or two different
#: comments would collapse to one key.
TRACKING_PARAMS: Final[frozenset[str]] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_name",
        "utm_id",
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_src",
        "ref_url",
        "referrer",
        "source",
        "share_id",
        "usp",
        "sca_esv",
        "_branch_match_id",
    }
)

_URL_RE: Final[re.Pattern[str]] = re.compile(r"https?://\S+|www\.\S+")
_WS_RE: Final[re.Pattern[str]] = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #


def _join(parts: Iterable[Any]) -> str:
    """Join parts with the field separator, rendering ``None`` as empty.

    Positional and separator-delimited, so ``("a", "b")`` and ``("ab",)`` cannot
    collide.
    """
    return _SEP.join("" if p is None else str(p) for p in parts)


def sha1_short(*parts: Any, length: int = 12) -> str:
    """Truncated SHA-1 over separator-joined ``parts``.

    SHA-1 is used for identifiers, where the requirement is stable distribution
    rather than collision resistance against an adversary; nothing here is a
    security boundary. Content hashes use SHA-256.
    """
    digest = hashlib.sha1(_join(parts).encode("utf-8")).hexdigest()
    return digest[:length]


def sha256_hex(text: str) -> str:
    """Full SHA-256 hex digest of ``text``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def raw_text_sha256(raw_text: str) -> str:
    """SHA-256 of raw text exactly as collected.

    A pure function of collected text, therefore available at import time. This
    is *not* ``content_hash``, which canonicalizes first and belongs to Phase 3.
    """
    return sha256_hex(raw_text)


def canonicalize_for_hash(text: str) -> str:
    """Canonicalize text for content hashing: NFKC, lowercase, strip URLs and
    punctuation, collapse whitespace (spec Section 26.1).

    Order matters. URLs are stripped before punctuation, because stripping
    punctuation first would shred a URL into tokens that survive as noise.

    **"Stripped punctuation" is read as "replaced by a word boundary", not
    "deleted".** The specification does not say which, and the two differ: under
    deletion ``"photo,video"`` becomes ``"photovideo"``, merging two words into a
    token that matches neither. Replacement keeps token boundaries intact, at the
    cost of turning ``"can't"`` into ``"can t"``.

    That cost is acceptable because of what ``content_hash`` is for. It detects
    *exact* duplicates — the same item re-ingested, or identical canonical text
    from one author (spec Section 19.6 rules 1 and 2). It is not a similarity
    measure. ``"can't"`` and ``"cant"`` are two different typings, plausibly by
    two different people, so they *should* hash differently; catching them as
    related is ``simhash``'s job, under the review band and its safety conditions.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = _URL_RE.sub(" ", text)
    text = "".join(
        " " if unicodedata.category(ch).startswith("P") else ch for ch in text
    )
    return _WS_RE.sub(" ", text).strip()


def content_hash(text: str) -> str:
    """SHA-256 of canonicalized text (spec Section 26.1).

    This is a *hash* helper, not the normalizer. It deliberately does not produce
    or expose ``normalized_text``: that is ``DocumentDerived`` and belongs to
    Phase 3 (``src/normalize/text.py``). Two documents with the same
    ``content_hash`` are textually identical after canonicalization, which is
    what exact-duplicate detection needs and all it needs.
    """
    return sha256_hex(canonicalize_for_hash(text))


def author_hash(salt: str, source_platform: str, username: str) -> str:
    """HMAC-SHA256 author hash, truncated to 16 hex characters.

    HMAC rather than a plain salted digest so the salt is a key, not a prefix.
    Rotating the salt changes every hash in the corpus, which is why
    ``author_salt_id`` is recorded alongside (spec Section 15.1) and why the salt
    is set once per corpus.

    Raises ``ValueError`` on an empty salt: an unsalted author hash over a small
    public-username space would be trivially reversible, and silently accepting
    ``""`` would produce exactly that while looking hashed.
    """
    if not salt:
        raise ValueError("AUTHOR_SALT must be a non-empty value to hash an author")
    mac = hmac.new(
        salt.encode("utf-8"),
        _join((source_platform, username)).encode("utf-8"),
        hashlib.sha256,
    )
    return mac.hexdigest()[:16]


def author_salt_id(salt: str) -> str:
    """Identifier for a salt, derived from the salt but not reversible to it.

    Recorded on every document and in the manifest so a rotation is detectable.
    The salt value itself is never stored or exported (spec Section 12.1).
    """
    if not salt:
        raise ValueError("cannot derive author_salt_id from an empty salt")
    return sha256_hex(salt)[:12]


def source_url_key(url: str) -> str:
    """Import-time URL normalization (spec Section 15.1).

    Deliberately light: lowercase scheme and host, drop the fragment, drop known
    tracking parameters, sort the remaining query, collapse a trailing slash.

    It stays light because it feeds ``doc_id``. The heavier ``canonical_url`` in
    ``DocumentDerived`` may resolve share links and redirects, which can require
    a network call — and a network call cannot participate in an identifier that
    must be computable offline at import.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    query = urlencode(
        sorted(
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        )
    )

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit((scheme, netloc, path, query, ""))


# --------------------------------------------------------------------------- #
# Record identifiers
# --------------------------------------------------------------------------- #


def doc_id(
    source_platform: str,
    *,
    source_item_id: str | None = None,
    url_key: str | None = None,
    source_name: str | None = None,
    author_hash_value: str | None = None,
    published_at_iso: str | None = None,
    raw_text_hash: str | None = None,
) -> str:
    """Derive ``doc_id`` from collection-time values only (spec Section 26.1).

    Natural key, in order of preference:

    1. ``source_item_id`` — when the platform exposes one
    2. ``url_key`` — the import-time normalized URL
    3. ``sha1(source_name | author_hash | published_at | raw_text_sha256)``

    **This signature has no ``content_hash`` parameter, and that is the point**
    (ADR-20). The third fallback previously used ``content_hash``, a Phase 3
    output, which made ``doc_id`` undefinable at import: manual import could not
    assign an identifier without first running the normalizer, and a change to
    the canonicalization rules silently changed every manually imported row's
    identity. ``raw_text_sha256`` is a pure function of collected text, so it is
    available at import and stable under any later normalizer revision. Because
    the argument does not exist, the dependency cannot be reintroduced by a
    later edit without changing this signature.
    """
    if source_item_id:
        natural_key = source_item_id
    elif url_key:
        natural_key = url_key
    elif raw_text_hash:
        natural_key = sha1_short(
            source_name,
            author_hash_value or "anon",
            published_at_iso or "",
            raw_text_hash,
            length=40,
        )
    else:
        raise ValueError(
            "doc_id needs source_item_id, url_key, or raw_text_hash; "
            "all three were absent"
        )
    return f"{source_platform}-{sha1_short(source_platform, natural_key)}"


def case_id_ordered(document_id: str, ordinal: int) -> str:
    """``{doc_id}#cNN`` for a case whose evidence offsets resolved.

    The ordinal is 1-based and zero-padded to two digits (spec Section 26.3).
    """
    if ordinal < 1:
        raise ValueError(f"case ordinal is 1-based, got {ordinal}")
    return f"{document_id}#c{ordinal:02d}"


def case_id_unordered(document_id: str, canonical_payload: str) -> str:
    """``{doc_id}#u{sha1[:8]}`` for a case whose offsets could not be resolved.

    Such a case cannot be ordered by evidence position, and is never persisted as
    valid. It still needs a stable identifier so its failure record can be
    referenced from the review queue, where it lands with reason code
    ``evidence_offsets_unresolved`` (spec Section 26.3).
    """
    return f"{document_id}#u{sha1_short(canonical_payload, length=8)}"


def case_sort_key(
    start_char: int | None,
    end_char: int | None,
    quote: str,
    canonical_payload: str,
) -> tuple[int, int, str, str]:
    """Sort key that assigns case ordinals (spec Section 26.3).

    Four keys, in order: ``start_char``, ``end_char``, ``sha1(quote)``,
    ``sha1(canonical_payload)``.

    The last two are not theoretical. One sentence can support two distinct
    retrieval needs, so two cases can share a first-evidence span at identical
    offsets and position alone cannot order them. Without a tie-break the ordinal
    would fall back to whatever order the sort happened to receive — which is the
    model-output-order instability that position anchoring exists to remove,
    reintroduced through the back door.

    Phase 5 supplies the spans; this function only defines the ordering.
    """
    if start_char is None or end_char is None:
        raise ValueError(
            "a case with unresolved offsets cannot be ordered; "
            "use case_id_unordered() instead"
        )
    return (start_char, end_char, sha1_short(quote, length=40),
            sha1_short(canonical_payload, length=40))


def evidence_id(
    owner_id: str,
    field_name: str,
    quote: str,
    start_char: int | None = None,
    end_char: int | None = None,
) -> str:
    """Identifier for one evidence span on one named field (spec Section 26.1).

    ``field_name`` participates because evidence is field-level: the same quote
    supporting two different fields is two spans, and collapsing them would make
    the evidence-required map unenforceable (ADR-16).

    Offsets are omitted from the hash when unresolved, so an unresolved span
    still gets a stable id for its review item.
    """
    if start_char is None or end_char is None:
        return sha1_short(owner_id, field_name, sha1_short(quote, length=40))
    return sha1_short(
        owner_id, field_name, start_char, end_char, sha1_short(quote, length=40)
    )


def link_id(document_id: str, canonical_doc_id: str, method: str) -> str:
    """Identifier for a ``DuplicateLink`` (spec Section 26.1)."""
    return sha1_short(document_id, canonical_doc_id, method)


def event_id(
    run_id: str, stage: str, target_id: str, attempt: int, status: str
) -> str:
    """Identifier for a ``StageEvent`` (spec Section 26.1).

    ``attempt`` participates so a retry is a distinct event rather than an
    overwrite: append-only history is the whole mechanism (ADR-18).
    """
    return sha1_short(run_id, stage, target_id, attempt, status)


def canonical_doc_id(doc_ids: Iterable[str]) -> str:
    """Canonical document of a duplicate group: the lowest ``doc_id``.

    Byte-wise ascending comparison, total and order-independent (ADR-20).
    "First collected" was the previous rule and was not a property of the
    documents at all — it depended on which source ran first, how a batch
    paginated, whether a run resumed from a checkpoint, and for manual rows the
    order an analyst pasted them in. Two runs over one corpus could pick
    different canonical documents, changing which ``source_url`` an evaluator was
    shown for the same evidence.
    """
    ids = sorted(doc_ids)
    if not ids:
        raise ValueError("a duplicate group needs at least one doc_id")
    return ids[0]


# --------------------------------------------------------------------------- #
# Fingerprints and cache keys
# --------------------------------------------------------------------------- #


def decision_fingerprint(
    model: str,
    prompt_version: str,
    ruleset_version: str,
    schema_version: str,
    content_hash_value: str,
) -> str:
    """Fingerprint for a ``RelevanceDecision`` (spec Section 26.2).

    Includes ``ruleset_version`` because the deterministic prefilter and scope
    rules participate in the decision. Excludes ``taxonomy_version``.
    """
    return sha1_short(
        model, prompt_version, ruleset_version, schema_version,
        content_hash_value, length=10,
    )


def extraction_fingerprint(
    model: str,
    prompt_version: str,
    schema_version: str,
    content_hash_value: str,
) -> str:
    """Fingerprint for a ``RetrievalCase`` (spec Section 26.2).

    **No ``taxonomy_version``** (ADR-19). A case's extracted content does not
    change when the taxonomy is revised, so its fingerprint must not either.
    Including it meant publishing taxonomy v2 invalidated every cached extraction
    and re-ran the whole corpus through a paid model to produce identical output,
    which created a standing financial reason not to revise the taxonomy — in
    direct opposition to spec Section 20.
    """
    return sha1_short(
        model, prompt_version, schema_version, content_hash_value, length=10
    )


def assignment_fingerprint(
    model: str,
    prompt_version: str,
    schema_version: str,
    taxonomy_version: str,
    content_hash_value: str,
) -> str:
    """Fingerprint for a ``ClusterAssignment`` (spec Section 26.2).

    The only fingerprint carrying ``taxonomy_version``, because this is the only
    record whose meaning actually depends on it.
    """
    return sha1_short(
        model, prompt_version, schema_version, taxonomy_version,
        content_hash_value, length=10,
    )


def cache_key(
    *,
    provider: str,
    model: str,
    prompt_id: str,
    prompt_version: str,
    schema_version: str,
    content_hash_value: str,
    decoding_params: Mapping[str, Any] | None = None,
    ruleset_version: str | None = None,
    taxonomy_version: str | None = None,
) -> str:
    """SHA-256 cache key over canonical JSON of the call's inputs.

    Inputs per spec Section 19.5: content hash, provider, model, prompt id and
    version, schema version, and decoding parameters that affect output.

    ``ruleset_version`` is opt-in. Relevance classification passes it, because a
    ruleset change changes which documents are classified. Extraction does not.
    Spec Section 19.5 does not list it; ``decision_fingerprint`` already does
    (Section 26.2). Omitting it unless the caller asks keeps extraction keys
    stable.

    ``taxonomy_version`` is **opt-in** and must be passed only by the two
    taxonomy-dependent stages: candidate generation and assignment. It is absent
    from prefilter, relevance, extraction, and Ask synthesis keys (ADR-19).
    Making it an explicit keyword rather than reading the module constant is what
    keeps the default correct — a caller has to ask for it.
    """
    payload: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "content_hash": content_hash_value,
        "decoding_params": dict(decoding_params or {}),
    }
    if ruleset_version is not None:
        payload["ruleset_version"] = ruleset_version
    if taxonomy_version is not None:
        payload["taxonomy_version"] = taxonomy_version
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return sha256_hex(blob)
