"""Normalization: text, redaction, canonical URLs, and stable hashes."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.core.ids import content_hash
from src.extract.validator import validate_span
from src.models.enums import ValidationState
from src.normalize.canonicalize import canonical_url
from src.normalize.derive import derive_document
from src.normalize.privacy import redact
from src.normalize.text import normalized_text
from src.pipeline.runner import RULESET_INSTANT
from tests.synthetic import RAW_TEXT, make_document, make_span

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _document(**overrides: object):
    text = str(overrides.get("raw_text", RAW_TEXT))
    from src.core.ids import raw_text_sha256, source_url_key

    url = str(
        overrides.get(
            "source_url",
            "https://www.reddit.com/r/googlephotos/comments/t3_synthetic/",
        )
    )
    fields: dict[str, object] = {
        "raw_text": text,
        "raw_text_sha256": raw_text_sha256(text),
        "source_url": url,
        "source_url_key": source_url_key(url),
    }
    fields.update(overrides)
    return make_document(**fields)


def test_raw_text_is_unchanged_by_normalization() -> None:
    original = "ﬁ\u00a0Keep this EXACTLY.\n\nLine two."
    document = _document(raw_text=original, doc_id="doc-raw", source_item_id="raw-1")
    before = document.raw_text
    derived = derive_document(document, derived_at=RULESET_INSTANT)

    assert document.raw_text == before
    assert document.raw_text.encode("utf-8") == original.encode("utf-8")
    assert "normalized_text" not in document.model_dump()
    assert derived.normalized_text != document.raw_text


def test_nfkc_and_whitespace_normalization() -> None:
    raw = "ﬁ  PHOTO\u00a0\n\nNext"
    assert normalized_text(raw) == "fi photo next"
    assert raw == "ﬁ  PHOTO\u00a0\n\nNext"


def test_length_preserving_redaction_covers_each_pattern() -> None:
    raw = (
        "Email me@example.com, call 555-123-4567, mention @someuser, "
        "and the code 1234567890 stays masked."
    )
    audit, spans = redact(raw)

    assert len(audit) == len(raw)
    kinds = {span.redaction_type.value for span in spans}
    assert kinds == {"email", "phone", "handle", "digit_run"}
    for span in spans:
        assert audit[span.start_char:span.end_char] == "#" * span.length
        assert span.end_char - span.start_char == len(raw[span.start_char:span.end_char])


def test_overlapping_redaction_keeps_the_longer_email() -> None:
    raw = "write 12345678@example.com today"
    audit, spans = redact(raw)

    assert len(audit) == len(raw)
    assert len(spans) == 1
    assert spans[0].redaction_type.value == "email"
    assert audit[spans[0].start_char:spans[0].end_char] == "#" * spans[0].length
    assert "12345678@example.com" not in audit


def test_evidence_offsets_stay_valid_against_both_texts() -> None:
    text = "See me@example.com about the photo I lost yesterday."
    document = _document(raw_text=text, doc_id="doc-offsets", source_item_id="off-1")
    derived = derive_document(document, derived_at=RULESET_INSTANT)
    derived.check_length_preserved(text)

    quote = "the photo I lost"
    start = text.index(quote)
    end = start + len(quote)
    assert text[start:end] == derived.raw_text_audit[start:end]
    kept = make_span("problem_summary", quote, text=text)
    assert validate_span(kept, text, derived.redaction_spans).ok
    assert validate_span(kept, derived.raw_text_audit, derived.redaction_spans).ok

    hidden = make_span("problem_summary", "me@example.com", text=text)
    rejected = validate_span(hidden, text, derived.redaction_spans)
    assert not rejected.ok
    assert rejected.span.validation_state is ValidationState.rejected


def test_canonical_url_drops_tracking_and_keeps_comment_ids() -> None:
    watched = canonical_url(
        "https://www.YouTube.com/watch?v=abcdefghijk&lc=Ugxyz&utm_source=share&utm_medium=ios#t=10"
    )
    short = canonical_url("https://youtu.be/abcdefghijk?lc=Ugxyz&fbclid=abc")

    assert watched == short
    assert "utm_source" not in watched
    assert "fbclid" not in short
    assert "lc=Ugxyz" in watched
    assert "v=abcdefghijk" in watched
    assert watched.startswith("https://youtube.com/watch?")


def test_content_hash_is_stable_and_independent_of_run_time() -> None:
    document = _document(doc_id="doc-hash", source_item_id="hash-1")
    first = derive_document(document, derived_at=RULESET_INSTANT)
    later = derive_document(
        document, derived_at=datetime(2030, 1, 1, tzinfo=UTC)
    )

    assert first.content_hash == later.content_hash == content_hash(document.raw_text)
    assert first.simhash == later.simhash
    assert first.normalized_text == later.normalized_text
    assert first.language_detected == "en"
    assert first.language_detector_version is None
    assert document.language_reported == "en"


def test_collected_language_is_kept_when_detection_is_absent() -> None:
    document = _document(
        doc_id="doc-lang",
        source_item_id="lang-1",
        language_reported="fr",
    )
    derived = derive_document(document, derived_at=RULESET_INSTANT)
    assert derived.language_detected == "fr"
    assert document.language_reported == "fr"


def test_normalize_does_not_import_later_stages() -> None:
    script = """
import sys
import src.normalize
import src.dedupe
import src.review
forbidden = [
    name
    for name in sys.modules
    if name.startswith((
        "src.relevance",
        "src.llm",
        "src.taxonomy",
        "src.analyze",
        "src.retrieve",
        "src.store",
    ))
]
assert not forbidden, forbidden
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


@pytest.mark.synthetic
def test_redaction_does_not_copy_a_secret_into_the_audit_text() -> None:
    secret = "me@example.com"
    audit, _spans = redact(f"contact {secret} please")
    assert secret not in audit
