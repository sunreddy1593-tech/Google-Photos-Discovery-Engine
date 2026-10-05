# Development annotation pack

Further gold labelling is closed. The approved official set, 35 documents and
21 cases, is the final gold set (ADR-37). The notes below are the original
starter instructions. They are not a request for more labels.

This pack is a starter batch for gold labelling. The label fields were blank
when the pack was created. Those ten documents are not a request to label
more. The quality gate and milestone M1 are separate from this pack.

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
.\.venv\Scripts\python.exe scripts\validate_annotations.py --pack data/annotation/dev-starter-2026-10-03
```

Write a draft gold directory from complete reviews, then score that draft on
the development split only:

```text
.\.venv\Scripts\python.exe scripts\validate_annotations.py --pack data/annotation/dev-starter-2026-10-03 --emit data/annotation/dev-starter-2026-10-03/gold-draft
.\.venv\Scripts\python.exe scripts\evaluate.py --gold data/annotation/dev-starter-2026-10-03/gold-draft --split dev --out data/annotation/dev-starter-2026-10-03/evaluation
```

The official reports stay pending until labels exist in `data/gold/`:

```text
.\.venv\Scripts\python.exe scripts\evaluate.py --gold data/gold --split dev --out data/exports/quality/dev/
.\.venv\Scripts\python.exe scripts\evaluate.py --gold data/gold --split holdout --out data/exports/quality/holdout/
```

Holdout error analysis stays refused. Do not lower a gate.
