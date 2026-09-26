# Status

> Updated after each approved phase (spec Section 29.15).

| | |
|---|---|
| **Completed phase** | Phase 1 — schemas and evidence validation (hardened 2026-09-26) |
| **Current phase** | Phase 2 — manual import and pilot corpus (not started) |
| **Tests** | 509 passing, 0 failing (171 from Phase 0, 338 new) |
| **Coverage** | 100% of `src/models/` and `src/extract/validator.py` |
| **Last verified** | 2026-09-21 |
| **Blockers** | None |
| **Next command** | See "Next command" below |

---

## Phase 1 — complete

Exit criteria from `IMPLEMENTATION-PLAN.md` Phase 1, each verified by a command
rather than asserted:

| Criterion | Evidence |
|---|---|
| Every schema has positive and negative tests | `pytest tests/test_models.py -v` → 186 passed, at least one rejection test per contract |
| Fabricated evidence fails validation | `test_evidence.py::test_fabricated_quote_is_rejected` |
| `CollectedDocument` validates with no later-stage field present | `test_models.py::test_collected_document_validates_with_no_later_stage_module_imported` runs in a subprocess and asserts `sys.modules` never gained a derived contract |
| Every model field is classified evidence-required or evidence-exempt | `test_evidence_map.py::test_every_field_is_classified_exactly_once` iterates `model_fields` for both contracts |
| Missing facts stay null or empty with an observation status | `test_models.py::test_defaults_are_not_stated_rather_than_a_value` plus the status-gate parametrisation in `test_evidence_map.py` |
| No `unknown` placeholder exists | `test_models.py::test_no_enum_carries_a_placeholder_member` runs once per enum over every member |
| Synthetic fixtures are marked | `test_models.py::test_every_fixture_document_is_marked_synthetic` and `test_a_synthetic_fixture_cannot_be_mistaken_for_direct_user_evidence` |
| Invariants I2, I3, I6, I11, I12, I13 covered | I2/I3 in `test_evidence.py`, I6 in `test_models.py`, I11 in `test_models.py` and `test_architecture.py`, I12 in `test_evidence_map.py`, I13 in `test_models.py` |

### What exists

```text
src/models/   enums.py  evidence_map.py  base.py  evidence.py
              collected_document.py  document_derived.py  duplicate_link.py
              relevance.py  retrieval_case.py  stage_event.py
              cluster_assignment.py  gold.py  export.py
src/extract/  validator.py            span ladder, record gate, span union,
                                      analysis gate
tests/        synthetic.py  test_models.py  test_evidence.py  test_evidence_map.py
```

`src/models/__init__.py` re-exports through `__getattr__` rather than eager
imports. Eager imports would make `import src.models.collected_document` pull in
every later-stage contract, which is exactly what invariant I11's test forbids.

### What deliberately does not exist

No collectors, no normalizer, no deduplication, no `src/llm/`, no store layer, no
analysis, no retrieval, no `app.py`. No review queue either: Phase 1 produces
the routing decision, and ADR-24 builds the queue in Phase 3, when the first
review items exist. `src/extract/` holds the validator and nothing else; the
extraction prompt and its runner are Phase 5.

### The evidence ladder, as built

`validate_span` tries four rungs in order and records which one answered, so a
later report can separate clean extraction from salvaged extraction:

1. **Exact** — `quote == source_text[start_char:end_char]`. Accepted unchanged.
2. **Offset repair** — quote found verbatim elsewhere. One occurrence is
   repaired silently; several occurrences are resolved to the one nearest the
   claimed offset. A genuine tie is *not* guessed: the span becomes
   `ambiguous_tied` / `pending` and routes to human review.
3. **Whitespace repair** — found only after whitespace normalization. Offsets
   move to the real text; `quote` keeps the document's characters, not the
   normalized ones, so the displayed excerpt is still verbatim.
4. **Rejection** — not present at all. `fabricated`, and the **record** is
   invalidated. The affected field is never quietly dropped so the rest of the
   record can be accepted: dropping it would leave the field unevidenced, which
   the status gate rejects in turn, so both exits are closed and the only route
   forward is review.

A span overlapping a redaction is rejected at every rung, including when the
quote itself is exact, because the underlying text was destroyed by redaction
and cannot be re-verified.

### What happens after rung 4

Rejecting the span is only the first step. ARCHITECTURE Section 9.3 rung 4
continues: "the parent record is invalidated, the failure is logged, and the
document enters the review queue", and spec Section 17.12 adds that nothing
invalid reaches the analysis dataset. Each leg is now enforced rather than
described:

| Leg | Where it lives | Test |
|---|---|---|
| Record invalidated | `validate_record` fails on **any** non-valid span attached to the record, and `RecordValidation.apply` writes `validation_state` back onto it | `test_a_rejected_span_invalidates_the_record_it_belongs_to` |
| Error and field recorded | `RecordValidation.invalid_fields` and `.retained_spans` carry the affected fields and the surviving candidates as data | `test_the_invalid_candidate_is_retained_for_review` |
| Failure logged | `_log_invalidation` emits one structured warning carrying `review_reason_code`, `invalid_fields`, and `retained_span_ids` | `test_the_failure_is_logged_with_the_fields_a_report_filters_on` |
| Enters review | `RecordValidation.requires_review` and `.review_reason_code` are the routing decision as data; Phase 3 builds the queue that consumes it (ADR-24) | `test_an_invalidated_record_is_routed_to_review` |
| No analysis output | `gate_for_analysis` raises `EvidenceError`; `select_valid_for_analysis` omits the record | `test_no_invalid_candidate_appears_in_a_valid_output_query` |
| Until corrected | The same record passes once the fabricated span is removed | `test_correcting_the_fabrication_reopens_the_gate` |

**The affected field is never simply dropped.** This is the requirement that
shapes the rest: an invalid span cannot be resolved by discarding the field it
supports and accepting the remainder. Both exits are closed. The record cannot
be marked `valid` while the bad span is attached — a model-level rule on both
contracts, so a store bypassing the validator still cannot write one — and
detaching the span leaves the field unevidenced, which the status gate rejects
in turn. The only route forward is review.

Two filing details are deliberate. An unresolved `ambiguous_tied` span is filed
under `evidence_offsets_unresolved` rather than `evidence_validation_failed`,
because the quote is real and only its position is unknowable, so the review it
needs is a different job from adjudicating a fabrication. And a failing record
becomes `pending`, not `rejected`: it is unconfirmed rather than wrong.

`gate_for_analysis` returns the spans rather than a boolean on purpose. An
`is_eligible()` predicate is a call an aggregation can forget and still get its
data; making the gate the only route to the evidence means analysis code cannot
obtain its quotes without passing through it. `select_valid_for_analysis`
filters on `validation_state` rather than `needs_human_review`, because the two
differ on the reviewed-but-not-revalidated record and on the `pending` record
nobody has looked at.

### Inherited `scope_class` (spec 15.4)

`RetrievalCase.scope_class` is evidence-exempt on the grounds that it is
inherited from a decision that already evidenced it. That exemption is only
honest while the inheritance is real, so `validate_record` checks all three
conditions in `SCOPE_INHERITANCE_CONDITIONS` when the decision is supplied: same
`doc_id`, matching `scope_class`, and the decision's `validation_state` is
`valid`. Each fails for its own reason — a decision about another document is
borrowing a verdict, a differing value is overruling rather than inheriting, and
a `pending` decision has no validated evidence to lend.

The check runs only when the decision is passed in, because the case contract
carries no `decision_id` and the validator cannot fetch the decision itself.
Passing silently when it is absent is the honest behaviour; claiming to have
checked would be worse than not checking.

### The two summary fields

`reason_summary` stays an evidence-exempt paraphrase, and two things keep that
from becoming a loophole. It can never substitute for evidence — every `ok`
decision needs a non-empty `evidence` tuple, and the record gate needs at least
one of those spans to be *valid*, so a long plausible summary buys nothing. And
it can never be rendered as a quotation: `ExportedEvidenceSpan.field_name` must
be an evidence-required field, so the export cannot put the model's own prose in
quotation marks beside a real quote.

`problem_summary` looks like an inconsistency and is not. It is a paraphrase
*and* an evidence-required field, so its span quotes the source text supporting
the summary rather than the summary itself — which is why it remains exportable
while `reason_summary` does not.

---

## Research track — still the critical path

Unchanged by this phase, and now the only thing standing between the repository
and Phase 2 having anything to import.

- [ ] Collect 30–50 genuine public documents with direct permalinks and verbatim
      text. Manual import is the guaranteed baseline; the 300-document target
      must be reachable through manual import plus YouTube alone (Section 11.4).
- [ ] Do **not** start taxonomy naming. Spec Section 20 requires clusters to
      follow pilot evidence, and pre-reading the corpus with cluster names in
      mind is precisely the bias the rule prevents.

---

## Next command

```bash
pytest -q                                          # 480 tests, green
pytest -q --cov=src/models --cov=src/extract/validator --cov-report=term-missing
```

Then start Phase 2 using the paste-ready prompt in `IMPLEMENTATION-PLAN.md`.

## Known issues

None. Phase 1 interpretations and the four places where the specification's
field lists did not match its own model definitions are recorded in
`CHANGELOG.md` under "Interpretations" and "Conflicts found in the
specification"; the machine-readable version of the fourth lives in
`EXEMPT_ADDITIONS_RATIONALE` in `src/models/evidence_map.py`.
