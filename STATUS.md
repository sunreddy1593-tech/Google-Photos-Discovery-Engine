# Status

> Updated after each approved phase (spec Section 29.15).

| | |
|---|---|
| **Completed phase** | Phase 1 — schemas and evidence validation |
| **Current phase** | Phase 2 — manual import and pilot corpus (not started) |
| **Tests** | 467 passing, 0 failing (171 from Phase 0, 296 new) |
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
src/extract/  validator.py            span ladder, record gate, span union
tests/        synthetic.py  test_models.py  test_evidence.py  test_evidence_map.py
```

`src/models/__init__.py` re-exports through `__getattr__` rather than eager
imports. Eager imports would make `import src.models.collected_document` pull in
every later-stage contract, which is exactly what invariant I11's test forbids.

### What deliberately does not exist

No collectors, no normalizer, no deduplication, no `src/llm/`, no store layer, no
analysis, no retrieval, no `app.py`. `src/extract/` holds the validator and
nothing else; the extraction prompt and its runner are Phase 5.

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
4. **Rejection** — not present at all. `fabricated`, and the field it supports
   is dropped rather than kept with weaker provenance.

A span overlapping a redaction is rejected at every rung, including when the
quote itself is exact, because the underlying text was destroyed by redaction
and cannot be re-verified.

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
pytest -q                                          # 467 tests, green
pytest -q --cov=src/models --cov=src/extract/validator --cov-report=term-missing
```

Then start Phase 2 using the paste-ready prompt in `IMPLEMENTATION-PLAN.md`.

## Known issues

None. Phase 1 interpretations and the four places where the specification's
field lists did not match its own model definitions are recorded in
`CHANGELOG.md` under "Interpretations" and "Conflicts found in the
specification"; the machine-readable version of the fourth lives in
`EXEMPT_ADDITIONS_RATIONALE` in `src/models/evidence_map.py`.
