"""Write a blank development annotation pack. Does not label or call a provider.

Text is loaded only for documents that are in the Phase 4 development split and
that ``gold-split/v1`` seats in gold ``dev``. Phase 4 holdout rows are discarded.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.gold.annotate import blank_case, blank_document, reviewer_checks
from src.gold.split import GOLD_SPLIT_RULE, GOLD_SPLIT_SEED, SplitMember, assign_gold_splits
from src.models.enums import (
    EXCLUSION_REASON_CODES,
    INCLUSION_REASON_CODES,
    DimensionObservationStatus,
    ReasonCode,
    ScopeClass,
)
from src.models.relevance import RelevanceDecision
from src.pipeline.extraction_development import development_ids, holdout_ids
from src.relevance.split import SPLIT_VERSION

DEFAULT_PACK = Path("data/annotation/dev-starter-2026-10-03")
SEED = Path("data/interim/phase4/relevance_seed_review.csv")
COLLECTED = Path("data/processed/pilot-import/collected_documents.jsonl")
DERIVED = Path("data/interim/phase3/documents_derived.jsonl")
DECISIONS = Path("data/interim/phase4/development/01455c8aab03/relevance_decisions.jsonl")
CORPUS = Path("data/interim/phase5/development-corpus/3dc346ec030a")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a blank development annotation pack.")
    parser.add_argument("--out", default=str(DEFAULT_PACK))
    args = parser.parse_args(argv)
    destination = Path(args.out)
    if destination.exists():
        print(f"{destination} already exists; refusing to overwrite it", file=sys.stderr)
        return 1
    development = set(development_ids())
    holdout = set(holdout_ids())
    labels = _development_labels(SEED, development)
    assigned = assign_gold_splits(
        [
            SplitMember(doc_id, labels[doc_id][0], labels[doc_id][1])
            for doc_id in sorted(development)
        ]
    )
    wanted = {doc_id for doc_id, split in assigned.items() if split.value == "dev"}
    if wanted & holdout:
        raise SystemExit("refusing to put a Phase 4 holdout document in the pack")
    collected = _rows_for(COLLECTED, wanted)
    derived = _rows_for(DERIVED, wanted)
    decisions = _decisions_for(DECISIONS, wanted, holdout)
    _length_check(collected, derived)
    destination.mkdir(parents=True)
    _write_pack(destination, wanted, assigned, labels, collected, derived, decisions, holdout)
    print(f"documents            {len(wanted)}")
    print(f"phase4 holdout       {len(holdout)} not copied")
    print(f"gold holdout reserved {sum(split.value == 'holdout' for split in assigned.values())} not copied")
    return 0


def _development_labels(path: Path, development: set[str]) -> dict[str, tuple[str, str, str]]:
    labels: dict[str, tuple[str, str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            doc_id = row["doc_id"]
            if doc_id not in development:
                continue
            labels[doc_id] = (
                row["source_platform"],
                row["human_scope_class"],
                row["human_reason_code"],
            )
    if set(labels) != development:
        missing = development - set(labels)
        raise SystemExit(f"development documents without a seed label: {sorted(missing)}")
    return labels


def _rows_for(path: Path, wanted: set[str]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        doc_id = row.get("doc_id")
        if doc_id not in wanted:
            continue
        found[str(doc_id)] = row
    if set(found) != wanted:
        raise SystemExit(f"{path} is missing {sorted(wanted - set(found))}")
    return found


def _decisions_for(path: Path, wanted: set[str], holdout: set[str]) -> dict[str, RelevanceDecision]:
    found: dict[str, RelevanceDecision] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = RelevanceDecision.model_validate_json(line)
        if row.doc_id in holdout:
            raise SystemExit("relevance decisions contain a Phase 4 holdout id")
        if row.doc_id in wanted:
            found[row.doc_id] = row
    return found


def _length_check(collected: dict[str, dict], derived: dict[str, dict]) -> None:
    for doc_id, row in collected.items():
        audit = derived[doc_id]["raw_text_audit"]
        if len(row["raw_text"]) != len(audit):
            raise SystemExit(f"{doc_id} audit length differs from raw_text")
        if derived[doc_id].get("redaction_spans"):
            raise SystemExit(f"{doc_id} has redactions; the pack would need a separate offset note")


def _write_pack(
    destination: Path,
    wanted: set[str],
    assigned: dict,
    labels: dict[str, tuple[str, str, str]],
    collected: dict[str, dict],
    derived: dict[str, dict],
    decisions: dict[str, RelevanceDecision],
    holdout: set[str],
) -> None:
    disagreements = {
        doc_id
        for doc_id in wanted
        if decisions.get(doc_id) is not None
        and decisions[doc_id].technical_state.value == "ok"
        and (decisions[doc_id].scope_class.value if decisions[doc_id].scope_class else None)
        != labels[doc_id][1]
    }
    packets = destination / "packets"
    packets.mkdir()
    (destination / "labels").mkdir()
    (destination / "adjudicated").mkdir()
    (destination / "predictions").mkdir()
    manifest_rows = []
    selection_rows = []
    for doc_id in sorted(wanted):
        platform, scope, reason = labels[doc_id]
        decision = decisions.get(doc_id)
        model_scope = None if decision is None or decision.scope_class is None else decision.scope_class.value
        double_code = doc_id in disagreements
        manifest_rows.append(
            {
                "doc_id": doc_id,
                "gold_split": "dev",
                "phase4_split": "development",
                "double_code": double_code,
            }
        )
        selection_rows.append(
            {
                "doc_id": doc_id,
                "source_platform": platform,
                "source_type": collected[doc_id]["source_type"],
                "seating_scope_class": scope,
                "seating_reason_code": reason,
                "model_scope_class": model_scope,
                "model_technical_state": None if decision is None else decision.technical_state.value,
                "double_code": double_code,
                "seating_labels_copied_into_packet": False,
            }
        )
        packet = _packet(doc_id, collected[doc_id], derived[doc_id], double_code)
        (packets / f"{doc_id}.json").write_text(
            json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        prediction = _prediction(doc_id, decision)
        (destination / "predictions" / f"{doc_id}.json").write_text(
            json.dumps(prediction, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    manifest = {
        "split_rule": GOLD_SPLIT_RULE,
        "split_seed": GOLD_SPLIT_SEED,
        "phase4_split_version": SPLIT_VERSION,
        "documents": manifest_rows,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    selection = {
        "role": "selection_record_not_a_gold_label",
        "phase4_development_documents": len(labels),
        "phase4_holdout_documents": len(holdout),
        "phase4_holdout_text_copied": False,
        "gold_rule": GOLD_SPLIT_RULE,
        "stratified_by": ["source_platform", "existing_human_scope_class"],
        "gold_dev_copied": len(wanted),
        "gold_holdout_reserved_without_text": sum(item.value == "holdout" for item in assigned.values()),
        "reserved_development_doc_ids": sorted(
            doc_id for doc_id, split in assigned.items() if split.value == "holdout"
        ),
        "documents": selection_rows,
        "limitations": [
            "Strata of one or two documents receive no gold-dev seat, so some platforms and scope classes are absent.",
            "The existing human scope seated the split. It is not the gold label and it is not written into the packets.",
            "Ten starter documents are not the final gold set. ADR-37 closes further labelling at the approved 35 documents and 21 cases.",
        ],
    }
    (destination / "selection.json").write_text(
        json.dumps(selection, indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "vocabularies.json").write_text(
        json.dumps(_vocabularies(), indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "README.md").write_text(_readme(), encoding="utf-8")
    (destination / "labels" / "README.md").write_text(_labels_readme(), encoding="utf-8")
    (destination / "predictions" / "README.md").write_text(_predictions_readme(), encoding="utf-8")


def _packet(doc_id: str, collected: dict, derived: dict, double_code: bool) -> dict:
    return {
        "doc_id": doc_id,
        "phase4_split": "development",
        "gold_split": "dev",
        "split_rule": GOLD_SPLIT_RULE,
        "double_code": double_code,
        "provenance": {
            "source_platform": collected["source_platform"],
            "source_type": collected["source_type"],
            "evidence_tier": collected["evidence_tier"],
            "source_name": collected["source_name"],
            "title": collected.get("title"),
            "source_url": collected["source_url"],
            "canonical_url": derived["canonical_url"],
            "published_at": collected.get("published_at"),
            "collected_at": collected["collected_at"],
            "collection_method": collected["collection_method"],
            "collection_query": collected.get("collection_query"),
            "language_reported": collected.get("language_reported"),
            "language_detected": derived.get("language_detected"),
            "ingest_batch_id": collected["ingest_batch_id"],
        },
        "source_text_field": "raw_text_audit",
        "source_text": derived["raw_text_audit"],
        "offset_note": (
            "start_char is inclusive and end_char is exclusive. "
            "They index source_text. This audit text has the same length as raw_text "
            "and this document has no redaction spans."
        ),
        "gold_document": blank_document(doc_id, "dev"),
        "gold_cases": [],
        "case_template": blank_case(doc_id),
        "reviewer_checks": reviewer_checks(),
    }


def _prediction(doc_id: str, decision: RelevanceDecision | None) -> dict:
    extraction = _extraction(doc_id)
    relevance = None
    if decision is not None:
        relevance = {
            "scope_class": None if decision.scope_class is None else decision.scope_class.value,
            "reason_code": None if decision.reason_code is None else decision.reason_code.value,
            "technical_state": decision.technical_state.value,
            "validation_state": decision.validation_state.value,
            "decided_by": decision.decided_by.value,
        }
    return {
        "role": "model_prediction_not_a_gold_label",
        "doc_id": doc_id,
        "open_after_your_own_label_is_written": True,
        "relevance": relevance,
        "extraction": extraction,
    }


def _extraction(doc_id: str) -> dict:
    inputs = _matching(CORPUS / "extraction_inputs.jsonl", doc_id)
    failures = _matching(CORPUS / "extraction_failures.jsonl", doc_id)
    cases = _matching(CORPUS / "retrieval_cases.jsonl", doc_id)
    spans = _matching(CORPUS / "evidence_spans.jsonl", doc_id)
    input_row = inputs[0] if inputs else {}
    failure = failures[0] if failures else {}
    return {
        "eligible": input_row.get("eligible"),
        "technical_state": input_row.get("technical_state"),
        "scope_class_used": input_row.get("scope_class"),
        "stored_cases": len(cases),
        "failure_error_class": failure.get("error_class"),
        "invalid_fields": failure.get("invalid_fields"),
        "cases": [_public_case(case, spans) for case in cases],
    }


def _public_case(case: dict, spans: list[dict]) -> dict:
    kept = {
        key: value
        for key, value in case.items()
        if key not in {"extraction_fingerprint", "all_evidence_spans"}
    }
    kept["evidence_spans"] = [
        {
            "field_name": span.get("field_name"),
            "quote": span.get("quote"),
            "start_char": span.get("start_char"),
            "end_char": span.get("end_char"),
            "validation_state": span.get("validation_state"),
        }
        for span in spans
        if span.get("owner_id") == case.get("case_id")
    ]
    return kept


def _matching(path: Path, doc_id: str) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("doc_id") == doc_id:
            rows.append(row)
    return rows


def _vocabularies() -> dict:
    return {
        "scope_class": [item.value for item in ScopeClass],
        "inclusion_reason_code": sorted(item.value for item in INCLUSION_REASON_CODES),
        "exclusion_reason_code": sorted(item.value for item in EXCLUSION_REASON_CODES),
        "review_reason_codes_are_not_gold_labels": sorted(
            item.value
            for item in ReasonCode
            if item not in INCLUSION_REASON_CODES and item not in EXCLUSION_REASON_CODES
        ),
        "observation": [item.value for item in DimensionObservationStatus],
    }


def _readme() -> str:
    return """# Development annotation pack

This pack is a starter batch for gold labelling. The label fields are blank.
Ten starter documents are not the final gold set. ADR-37 closes further
labelling at the approved 35 documents and 21 cases. This starter does not
by itself complete the quality gate or milestone M1.

The packets use the existing `GoldDocumentLabel` and `GoldCase` contracts.
`data/gold/` is unchanged and still empty. Quality-gate reports stay pending
until real labels are written there and the holdout split is measured.

## What was selected

`gold-split/v1` was applied to the 35 Phase 4 development documents. Inside
each source-and-scope stratum, documents are ordered by the hash of
`gold-split/v1` and `doc_id`. The first two of every five seats are gold
`dev`. This pack copies only those gold-`dev` seats.

The stratum scope is the existing human seed label. That label seated the
split. It is not a gold label, and it is not copied into a packet. A later
gold scope does not move the stored split: evaluation reads the split on the
label.

Strata with one or two documents get no gold-`dev` seat. Those platforms and
scope classes are missing here. The other Phase 4 development documents are
gold `holdout` for this seating and their text was not copied. The 15 Phase 4
holdout documents were not moved and their text was not copied.

`selection.json` is the seating record. Do not copy it into a label.

## How to label

Read `packets/{doc_id}.json`. Use `source_text` only. Record quotes as exact
slices: `source_text[start_char:end_char]` must equal `quote`.

Write your label to `labels/{your-labeler-id}/{doc_id}.json` before you open
`predictions/` or another reviewer's file. Leave `adjudicated` false and
`pre_adjudication_labels` empty. Your file is the independent label.

A document label needs `scope_class`, `reason_code`, `prefilter_should_pass`,
and `expected_case_count`. `prefilter_should_pass` is your own judgement of
whether a correct high-recall filter must keep the document. Zero cases is a
complete label when the source has no extractable retrieval episode: set
`expected_case_count` to 0 and use `"cases": []`.

For each episode, copy `case_template` into `cases`. Set `ordinal` to 1, 2, …
and give every supporting quote a `field_name`, the exact `quote`, and the
offsets. `expected_values` uses `{"observation", "value"}`. Leave an unobserved
field's observation null; the validator drops those fields. Values use the
vocabularies in `vocabularies.json`.

Answer `reviewer_checks` from the source. `retrieval_trigger` is why the item
was needed. Impact and severity need a quote that states them. A summary needs
a continuous quote for every factual clause. Do not invent, shorten, or splice
a quote. An empty model response is not evidence that no episode exists.

## Two reviewers, then adjudication

Documents with `double_code: true` need a second reviewer. That reviewer uses a
different `labeler_id` and a separate file. Do not edit the first file.

When both files exist, write `adjudicated/{doc_id}.json` with the resolved
document fields, `adjudicated: true`, and `pre_adjudication_labels` containing
both independent labels unchanged. Agreement is computed from those retained
labels, not from the resolved label.

## Commands

Validate completed files. This does not write `data/gold/` and does not score
the quality gate:

```text
.\\.venv\\Scripts\\python.exe scripts\\validate_annotations.py --pack data/annotation/dev-starter-2026-10-03
```

Write a draft gold directory from complete reviews, then score that draft on
the development split only:

```text
.\\.venv\\Scripts\\python.exe scripts\\validate_annotations.py --pack data/annotation/dev-starter-2026-10-03 --emit data/annotation/dev-starter-2026-10-03/gold-draft
.\\.venv\\Scripts\\python.exe scripts\\evaluate.py --gold data/annotation/dev-starter-2026-10-03/gold-draft --split dev --out data/annotation/dev-starter-2026-10-03/evaluation
```

The official reports stay pending until labels exist in `data/gold/`:

```text
.\\.venv\\Scripts\\python.exe scripts\\evaluate.py --gold data/gold --split dev --out data/exports/quality/dev/
.\\.venv\\Scripts\\python.exe scripts\\evaluate.py --gold data/gold --split holdout --out data/exports/quality/holdout/
```

Holdout error analysis stays refused. Do not lower a gate.
"""


def _labels_readme() -> str:
    return """# Independent labels

Create `labels/{labeler_id}/{doc_id}.json` from the matching packet.

One reviewer, one file. A second reviewer creates another directory. Neither
file is an adjudication. Copy the packet's `gold_document` fields that you
filled, plus `cases`. Do not include `source_text` or model predictions.

`split` stays `dev`. The validator reads the packet's seated split and rejects
any other document.
"""


def _predictions_readme() -> str:
    return """# Model predictions

Open a prediction only after `labels/{your-labeler-id}/{doc_id}.json` exists.

These files are saved model output. They are not gold labels, not semantic
approval, and not something to copy into a review. `stored_cases: 0` does not
mean the source has no retrieval episode.
"""


if __name__ == "__main__":
    raise SystemExit(main())
