# Google Photos Remembered-Item Retrieval Discovery Engine

> NextLeap Product Manager Fellowship — Graduation Project, Part 1  
> Project owner: Sunayana Muppalla  
> Document role: Authoritative product, research, data, and engineering specification  
> Recommended runtime: Python 3.12  
> Status: Build specification — version 1.1 (specification-consistency revision)

---

## 1. How to Use This Document

Owner-authorized submission amendment, 2026-10-04 (ADR-36): collection
integration, semantic review and evidence browsing may proceed in parallel.
The original graduation assignment is analysis of real public feedback at
scale and comparison of retrieval problems using traceable evidence. The
300-document/four-source ambition and larger gold target are internal targets,
not an externally mandated submission threshold. Report actual corpus and
method limitations. The read-only demo may show approved reference assignments
separately from unapproved model predictions; this cannot complete a quality
gate by substituting reference labels. Prepare Cloud publication with minimum
public excerpts and preserve private source, privacy and evidence validation.
The new n8n collector must import original text rather than tags or summaries.
Optional chat synthesis, embeddings, composite scores, new collectors and
architectural refactoring remain deferred. No completed research is inferred
from the software demonstration. This amendment supersedes strict phase-order
wording below within these owner-authorized submission workstreams only.

This file is the source of truth for building the discovery engine in Cursor.

Cursor must read this document completely before proposing architecture or writing code. Implementation must follow the phased build order in Section 24. Cursor must not jump directly to the Streamlit interface, large-scale collection, RAG, or solution design.

When implementation decisions conflict with this document, this document wins unless the project owner explicitly changes the requirement and records the change in `DECISIONS.md`.

Two companion documents elaborate this one and are subordinate to it:

- `ARCHITECTURE.md` — system design and rationale.
- `IMPLEMENTATION-PLAN.md` — the executable build plan, with one paste-ready prompt per phase.

This project must maintain:

- `STATUS.md` — completed phase, current phase, test count, known blockers, and next command.
- `DECISIONS.md` — important scope, schema, taxonomy, model, source, and scoring decisions. Any claim that a source mechanism was verified must link its primary documentation here (Section 11.4).
- `CHANGELOG.md` — material implementation changes by date.

Section 24.0 separates MVP scope from stretch scope. When time is short, stretch items are cut; MVP scope is not reduced.

### 1.1 Assignment requirement and the 2026-10-01 schedule change

The graduation assignment is Section 5: analyze real public feedback and compare retrieval problems with traceable evidence. Source provenance, privacy, verbatim evidence, and honest limits on what the corpus can support are part of that requirement.

The numbered phases, the 300-document / four-source line, the gold-set quality gates, taxonomy, composite scores, embeddings, chat synthesis, and a deployed Streamlit app are **internal build targets**. They are not an external submission threshold. ADR-32 records the owner's change for the October 2026 deadline:

- A usable discovery-engine demonstration is aimed at **2026-10-03**. Submission is **2026-10-07**. User research and a product MVP are separate fellowship work and are not a reason to relax evidence rules or to design a Google Photos solution.
- Collection, extraction review, and a basic evidence browser may proceed in parallel. That does not mark any unfinished phase or Milestone 1 complete.
- At least 300 collected documents across four source types remains an ambition. The submission reports the actual corpus size and its limitations.
- The only automated collector to start is YouTube comments, into the existing `CollectedDocument` contract. Workbook import stays. Further collectors are deferred.
- Chat synthesis, embeddings, composite opportunity scores, and architectural refactoring are deferred.
- YouTube stays `documented, unexercised` until a bounded API call is separately authorized and then reported as exercised. A fixture-tested collector is not a verification claim.

As of 2026-10-02, the three parallel tracks exist only to the extent below. None of them completes a numbered phase or Milestone 1.

- `main.py collect --youtube` writes `CollectedDocument` rows through `commentThreads.list` and `comments.list`. Workbook import is unchanged. Tests mock the API. No live YouTube call has been made.
- `main.py run --research-batch` reuses normalization, deduplication, relevance, and extraction for at most 20 documents outside the frozen development/holdout split. The dry-run against the collected files selected nothing, because every collected `doc_id` is inside that split. No research-batch model call has been made. The five-document pilot is not the batch runner.
- `main.py browse` serves a local page over saved development outputs. It is not the Phase 10 application in Section 23, it does not read a public export, and it does not load holdout text. Automatic validity is shown as not semantic approval. No provisional problem group is proposed, because no extraction case is semantically approved.

### 1.2 Owner-authorized single-reviewer method, 2026-10-04

This is an individual project. The owner approved the reviewed annotation drafts
and authorized **Sunayana as the sole human reviewer** (ADR-33). AI drafting and
human review must both be disclosed. For this submission, independent second
coding and adjudication are not required; they are **not performed**, rather
than completed or passed. Raw agreement and Cohen's kappa remain unavailable.
This amendment supersedes the internal double-coding requirements below for the
individual submission. It does not change evidence validation, quality thresholds,
document IDs or frozen split assignments, and does not complete M1.

The original starter seating manifest and earlier drafts remain immutable. A new
review manifest records the authorized single-reviewer procedure and preserves
the original double-code flags for audit. Approved references retain AI-assistance
provenance. Reviewer-directed scope exceptions, including the family-album core
label without demonstrated incomplete recall, remain visible.

### 1.3 M1 verification record, 2026-10-04

The five checks in Section 28 are complete on the retained 35-document
development-corpus run, verified offline in
`data/exports/milestones/m1-2026-10-04/report.json` (ADR-34). The complete
field-evidence count is 61, combining 24 inline and 37 external spans. All
ten saved analysis cases pass the current record gate, and all 61 spans match
successful retained source-validation verdicts. Fresh checks of 20 spans use
only approved gold-development source packets; reserved holdout sources stay
closed. The current full suite has 1087 passed and five skipped tests.

This records completion against the existing M1 checklist; no threshold or
evidence rule changed. Automatic field/span validity does not establish semantic
correctness of model interpretations. Sunayana's ten approved reference
documents and six reference cases are separate from the saved model cases.
The Phase 6 quality gate remains pending; historical M1-incomplete statements
describe earlier verification states, not the current milestone status.

### 1.4 Final gold set, 2026-10-04

The owner closed further gold labelling. There is no time for the internal
75–100 document volume. The approved labels already stored as official gold
are the final gold set: **35 documents and 21 cases** (10 development
documents with 6 cases, and 25 holdout documents with 15 cases). ADR-37
records that decision.

Those labels are not edited to match model output, and no documents are added.
The earlier 75–100 figure in Section 11.1, Phase 6, and Section 27 is that
closed internal volume, not an open task. The set remains one reviewer's
AI-assisted labels. Agreement stays unavailable. Holdout prior exposure and
extraction coverage stay disclosed limits. Closing the volume does not approve
model cases or lower a quality threshold.

---

## 2. Product Context

Google Photos users accumulate thousands of photos, videos, screenshots, receipts, documents, and other visual records over many years.

Search is relatively straightforward when a user knows the exact person, object, date, place, album, or text they need. Retrieval becomes much harder when the user remembers that a particular visual item exists but can recall only incomplete, approximate, contextual, or associative details.

Examples include:

- “That small café we visited during our Goa trip.”
- “The medicine photo I took when I was sick last year.”
- “A screenshot of a restaurant recommendation someone sent me.”
- “The photo where my sister was wearing a yellow dress at a family event.”
- “A document I photographed before moving apartments.”

The user is not exploring their library casually. They are trying to retrieve a known item. However, their memory may contain approximate time, people, context, emotion, objects, activity, or visual appearance rather than the exact metadata or language expected by the search experience.

---

## 3. Strategic Goal

Increase the percentage of users who successfully retrieve a photo or other visual item that they remember exists but cannot precisely describe when they begin searching.

This project does not attempt to improve Google Photos search generally. It investigates a narrower problem:

> How do people attempt to retrieve a known visual item when their memory is incomplete, and where does the current retrieval experience break down?

---

## 4. Product Problem Statement

People often remember visual information episodically and associatively. They may remember who was present, an approximate period, a trip, an activity, the appearance of an object, the surrounding context, or why they captured something. They may not remember the exact date, location name, album, object name, text, or search term.

Existing retrieval experiences can fail when users cannot translate their remembered cues into searchable language, when the system does not recognize those cues, when results are excessively broad, or when the intended item is obscured by other content.

The team currently lacks reliable evidence about:

- Which incomplete-memory retrieval situations occur most often in public user feedback.
- What users explicitly remember about the intended item.
- What information they explicitly say they do not remember.
- How they formulate and reformulate searches.
- Which system responses create dead ends.
- Which workarounds users attempt.
- Which failures lead to prolonged effort, abandonment, or loss of trust.
- Which opportunity areas appear across multiple independent sources rather than within one unusually active thread.

This discovery engine will convert public user feedback into structured, auditable retrieval cases that can be compared without losing the original evidence.

---

## 5. Part 1 Objective

Build an AI-powered discovery engine that:

1. Collects public feedback relevant to remembered-item retrieval.
2. Preserves the original text and source provenance.
3. Filters unrelated Google Photos complaints.
4. Extracts structured retrieval signals using a strict schema.
5. Requires verbatim evidence for every substantive classification.
6. Separates direct user evidence from editorial or contextual material.
7. Marks duplicates without deleting source records.
8. Helps the researcher discover, refine, and compare opportunity areas.
9. Allows evaluators to inspect the underlying evidence.
10. Supports evidence-grounded questions without answering beyond the dataset.

The engine must go beyond sentiment analysis or review summarization. Its primary value is comparison of distinct retrieval problems using traceable evidence from real users.

---

## 6. Primary Research Questions

The engine should help answer:

1. What types of known visual items are users trying to retrieve?
2. What cues do users remember?
3. What details have they forgotten or cannot name?
4. How do users translate incomplete memory into a query or browsing strategy?
5. How many reformulations or alternate strategies do they attempt?
6. What does Google Photos return?
7. At which point does the retrieval journey break down?
8. What workarounds do users employ?
9. Which failures lead to manual scrolling, external tools, abandonment, or trust loss?
10. Which patterns repeat across different sources, time periods, and asset types?
11. Which apparent problems are caused by incomplete memory, and which are general search defects?
12. Which opportunity areas are sufficiently evidenced to investigate further through primary research?

---

## 7. Non-Goals

Part 1 will not:

- Design or prototype the final Google Photos product solution.
- Claim that corpus frequency represents all Google Photos users.
- Analyze Google Photos sentiment in general.
- Optimize backup, synchronization, storage, billing, deletion, corruption, sharing, or editing.
- Access private Google Photos accounts or personal photo libraries.
- Store private photos, private messages, email addresses, or unhashed usernames.
- Treat editorial examples as direct user evidence.
- Infer forgotten information merely because the information was not mentioned.
- Treat every search complaint as an incomplete-memory problem.
- Use synthetic comments as research evidence.
- Allow an LLM to generate unsupported quotes, queries, actions, outcomes, or severity.

---

## 8. Key Definitions

### 8.1 Known-item retrieval

A user is attempting to locate a particular photo, video, screenshot, document image, or other visual item that they believe exists in their library.

### 8.2 Incomplete recall

The user remembers some cues about the intended item but lacks or is uncertain about one or more details needed to locate or describe it precisely.

### 8.3 Remembered cue

A detail the user explicitly recalls and uses, or considers using, to identify the intended item.

Examples: a person, approximate time, approximate place, activity, event, visual appearance, surrounding object, or text fragment.

### 8.4 Forgotten information

A detail the user explicitly states they cannot remember, is unsure about, or had to guess.

Absence of a detail from a post does not prove that it was forgotten.

### 8.5 Retrieval case

A structured representation of one user's attempt or need to retrieve a known visual item. One collected document can contain zero, one, or multiple retrieval cases.

### 8.6 Evidence span

An exact, verbatim substring from `raw_text` that supports a specific named field on a specific record. A paraphrase is not an evidence span. Because redaction is length-preserving (Section 15.6), a span's offsets are equally valid against `raw_text_audit`, which is what models, evaluators, and exports see.

### 8.7 Direct user evidence

Text authored by a user describing their own experience, need, attempt, result, or workaround.

### 8.8 Contextual evidence

Editorial articles, product announcements, tutorials, or third-party summaries. These may provide context but must not be counted as user prevalence.

### 8.9 Opportunity area

A recurring combination of retrieval target, memory state, behavior, failure mode, and user impact supported by multiple independent retrieval cases.

---

## 9. Scope Classification

Every collected document must receive one of three scope classes.

### 9.1 `core_incomplete_recall`

Use when evidence indicates all four of the following:

1. A known visual item exists or is believed to exist.
2. The user wants or attempted to retrieve it.
3. The user has incomplete, approximate, uncertain, or difficult-to-express memory cues.
4. **Either** the retrieval journey, result, workaround, or outcome is described, **or** the user states they could not turn their memory into a search at all.

**A failure to formulate a query is a retrieval failure, not a missing case.** A user who says "I know I have a photo of that café somewhere but I have no idea what to even type" satisfies this class. Condition 4 previously required a described journey, which excluded exactly the users whose memory was *most* incomplete — the ones who never reached the search box. That was a systematic bias against the project's core population, and it is corrected here.

Record this pattern as:

| Field | Value |
|---|---|
| `query_strategies` | `no_query_formulated` (Section 16.3) |
| `query_strategies_observation` | `stated` — the user stated this behaviour |
| `exact_query` / `query_paraphrase` | null, with `observation = not_applicable` |
| `system_responses` | empty, with `observation = not_applicable` — the system produced no response because it was never asked |
| `reformulation_count` | null, with `observation = not_applicable` |
| `outcome` | `not_found`, `abandoned`, or `unresolved` as the evidence supports |
| `reason_code` | `known_item_query_unformulable` |

The evidence requirement is unchanged and unrelaxed: the inability to formulate a query must itself be supported by a verbatim span. Silence about how a user searched is still `not_stated`, not `no_query_formulated`.

### 9.2 `adjacent_known_item_retrieval`

Use when the user is retrieving a known item but incomplete recall is not demonstrated.

Examples:

- Exact keyword search unexpectedly returns nothing.
- Face grouping omits a known person despite a precise search.
- Ask Photos returns a summary rather than the requested asset.

These records may be used as contextual comparators but must be reported separately from the core dataset.

### 9.3 `out_of_scope`

Use for:

- Backup, synchronization, deletion, storage, billing, corruption, or account access.
- General dislike of AI without a retrieval attempt.
- Casual browsing, reminiscing, or content discovery without a known target.
- Editing, sharing, printing, or organization problems unrelated to retrieval.
- Product announcements, tutorials, and hypothetical examples without direct user experience.
- Search-engine or web-search problems unrelated to a user's Google Photos library.
- Posts without enough evidence to establish a retrieval case.

---

## 10. Evidence Hierarchy

Use the following hierarchy when evaluating evidence quality:

1. Direct first-person description with an exact query, result, and outcome.
2. Direct first-person description with remembered cues and a retrieval failure.
3. Direct first-person description of a known-item retrieval issue with partial journey details.
4. Direct feature request grounded in the author's own retrieval experience.
5. Second-hand account or quoted user experience.
6. Editorial summary of user complaints.
7. Product example, tutorial, or hypothetical scenario.

Only levels 1–4 count as direct user evidence in prevalence and opportunity analysis. Levels 5–7 may be retained as contextual evidence but must not be included in user counts.

---

## 11. Data Sources

Candidate public sources include:

- Google Play Store reviews.
- Apple App Store reviews.
- Reddit posts and individual comments.
- Google Photos Help Community discussions.
- Google Pixel and Android community discussions.
- YouTube comments on Google Photos search and Ask Photos videos.
- Relevant public technology forums.
- Public social media posts when collection is permitted and provenance is stable.

Editorial articles, product announcements, and tutorials may be collected into a separate contextual table. They must never be mixed into direct-user frequency calculations.

Candidacy is not feasibility. Section 11.4 states, per source, which collection mechanism is actually available and how confident the project is in it.

### 11.1 Initial sampling target

- Manual pilot: 30–50 collected documents.
- Gold evaluation set: the approved final set is 35 documents and 21 cases, split into development and frozen holdout (Section 1.4, ADR-37). The earlier internal volume of 75–100 documents is closed.
- Internal ambition: at least 300 collected public documents across at least four source types. ADR-32 makes this an internal target, not the assignment's completion rule. The submission reports the actual count and its limitations.
- Report the number of core, adjacent, contextual, excluded, duplicate, pending-review, and technically failed records separately.

The project must never describe collected documents as relevant retrieval cases unless they pass the relevance criteria.

**Document counts are targets; case counts are findings.** A corpus-size ambition is something the project controls. How many qualifying retrieval cases that corpus yields is a measurement, and it must never be treated as a target to hit. Section 28 states this as an operating rule. The October 2026 demonstration uses the corpus that exists and says so.

### 11.2 Sampling balance

The collection configuration should aim for source diversity. If one source contributes more than 40% of included cases, the imbalance must be disclosed and source-balanced views must be available.

Do not discard legitimate evidence solely to force artificial balance. Report both raw and source-balanced results.

### 11.3 Collection compliance

- Prefer official APIs, permitted exports, or documented public endpoints.
- Respect robots.txt, rate limits, platform terms, and access restrictions.
- Provide manual CSV or JSONL import for blocked or restricted sources.
- Do not bypass authentication, anti-bot controls, or access restrictions.
- Store the collection method and query for every document.

### 11.4 Source feasibility

Every source carries a feasibility tier and, where a tier claims an automated mechanism, a link to the primary vendor documentation recorded in `DECISIONS.md`. A source's tier may be raised only by adding that documentation, never by optimism about the build.

| Source | Tier | Mechanism | Documentation obligation |
|---|---|---|---|
| Manual CSV / JSONL import | **Guaranteed baseline** | Analyst-collected rows via `collect/manual.py` | None. This is the path that always works. |
| YouTube comments | **Supported automated** | YouTube Data API v3 (`commentThreads.list`, `comments.list`) | Primary docs linked in `DECISIONS.md`; quota is the volume limit, and video *discovery* is the binding constraint rather than comment reading |
| Reddit posts and comments | **Optional, credential-dependent** | Official Reddit Data API, read-only, registered OAuth credentials | Primary docs linked; the source is skipped cleanly when credentials are absent |
| Google Play Store reviews | **Experimental; inspected routes blocked** | Official publisher access is unavailable to this project; inspected free libraries use the robots-disallowed Play web RPC | No qualifying route exercised. Reassess only with route-specific access evidence; see the 2026-10-01 ADR-22 amendment. |
| Apple App Store reviews | **Experimental; inspected routes blocked** | Official publisher access is unavailable; inspected RSS routes are robots-disallowed. Current feed contents were not probed | Historical empty responses do not prove permanent closure. No qualifying route exercised; see the source audit. |
| Google Photos Help Community / Google support forums | **Access requirements unresolved** | Supplied thread URLs are not robots-disallowed; native search/internal API paths are. No documented public collection API was established | Resolve collection permission separately from URL addressability and discovery. No current thread probe or automated adapter is verified. |
| Other public forums, social posts | **Experimental** | Case by case | Per-source documentation required before any automated collection |

Rules that follow from this table:

1. **Manual import is the guaranteed baseline, not the fallback of last resort.** The internal corpus ambition in Section 11.1 must remain achievable through manual import alone. Every automated collector is an accelerator, and losing one changes the schedule, not the deliverable. ADR-32 starts only the YouTube accelerator.
2. **"Experimental" must never be labelled low risk.** A source with no documented permitted mechanism is the highest-risk kind of source, regardless of how easy an unofficial library makes it look. Availability is not permission.
3. **No source mechanism may be described as verified without a link to the primary vendor documentation in `DECISIONS.md`.** "Verified against current documentation" with no citation is an unverifiable claim, and this specification treats it as no claim at all.
4. **Documented does not mean exercised.** A source whose documentation is linked but whose access has not yet been run in this repository is recorded as `documented, unexercised`. The distinction is stated in the ADR and carried into the Phase 7 report.
5. A blocked or restricted source degrades to manual import and records the reason. It is never worked around.
6. **Assess routes, not permanent source closure.** Publisher APIs require authorized publisher access; a public app listing does not confer it. Alternative routes need their own endpoint, permission, robots, provenance, and reliability checks. Library availability does not establish access. The [2026-10-01 source audit](SOURCE-COLLECTION-AUDIT-2026-10-01.md) records the current blocked and unresolved routes; it does not enable collection.
7. **An undisallowed robots path is not a terms permission grant.** These checks are independent. Evaluate the applicable terms in context, record unresolved permission honestly, and do not fetch a robots-disallowed route. Supplied community thread URLs and automated discovery must be evaluated separately. See the ADR-22 amendment for the correction to the earlier blanket Google terms interpretation.

---

## 12. Privacy and Research Ethics

- Collect only publicly accessible text.
- Do not collect private photos or access a user's Google Photos account.
- Replace usernames with deterministic salted hashes.
- Do not expose author identifiers in evaluator-facing exports.
- Remove email addresses, phone numbers, and other unnecessary personal identifiers.
- Preserve source URLs for auditability while avoiding the replication of unrelated personal details.
- Store only the text necessary to evaluate the retrieval problem.
- Do not quote more text than necessary in the public interface.
- Add an exclusion mechanism for sensitive content that is unrelated to product research.
- Record source and collection dates.

### 12.1 Public-export profile

Two different artifacts, two different rules. Confusing them is how a privacy commitment gets broken by a convenience.

| Profile | Location | Contents | Committed or published |
|---|---|---|---|
| **Local research profile** | `data/raw/`, `data/interim/` | Complete collected data, including unredacted `raw_text`, full `raw_text_audit`, every span, every failure | Never. Gitignored, never pushed, never deployed. |
| **Public export profile** | `data/exports/public/` | Section 15.12 `PublicExportRecord` only | Yes — this is what the repository commits and the deployed app serves |

The public export profile must satisfy all of the following:

1. **No usernames, no credentials, no unredacted PII.** No author display names, no plaintext handles, no email addresses, no phone numbers, no API keys, and never the author salt. `author_key` is a truncated salted hash — enough to count distinct authors, not enough to identify one.
2. **Complete raw collection data stays local.** The full corpus remains on the project owner's machine. The public artifact is a derived subset, and the pipeline must be able to produce it without reaching for anything local at serve time.
3. **Minimum excerpt, not full text.** A public record carries the shortest redacted excerpt that contains every validated evidence span for that record, plus a configured context window on each side (default ±160 characters, in `config/analysis.yaml`). Full text is included **only** where the source's redistribution terms explicitly permit it, and that permission is recorded per source in `DECISIONS.md` with `excerpt_is_full_text = true` on the record.
4. **Provenance and links always travel.** `source_url`, `canonical_url`, `source_platform`, `source_type`, `evidence_tier`, `source_name`, and dates are always present. A reader who wants the full context goes to the original post, which is where the full text legitimately lives.
5. **Offsets are rebased and reversible.** Spans in a public record carry excerpt-relative offsets plus `excerpt_start_char`, so highlighting works in the app and a reviewer can map any span back to document coordinates.
6. **Enforced by a test over the artifact.** A test scans the generated export for username patterns, key patterns, email and phone patterns, and for any `excerpt` longer than the permitted window without `excerpt_is_full_text`. Reviewing the exporter's source code is not sufficient; the check runs against the bytes that get committed.

**Analysis reproduction and source re-collection are different things, and only one of them is promised.**

- **Analysis reproduction — promised.** Given the committed public export and the committed cached model responses, a third party can re-run normalization, validation, taxonomy assignment, aggregation, and export, and obtain identical canonical content hashes (Section 26.4). No API key and no credentials are required. Every evidence span in the export validates against the excerpt it ships with.
- **Source re-collection — not promised, and not possible.** A third party re-running collection will not reproduce this corpus. Public posts are edited and deleted, ranking and search results shift, store review feeds return different windows, and several sources require credentials the project cannot share. This is a property of public web data, not a defect in the build.

The README methodology section must state both of these plainly. Claiming end-to-end reproducibility when only the analysis is reproducible would be the same category of error as claiming corpus frequency represents all users.

---

## 13. System Architecture

The system should follow this flow:

```text
Collect or import            → CollectedDocument
    → preserve raw documents
    → normalize and redact   → DocumentDerived
    → link exact and near duplicates  → DuplicateLink
    → deterministic prefilter
    → classify scope and relevance    → RelevanceDecision
    → extract evidence-backed retrieval cases  → RetrievalCase + ObservedValue
    → validate schema and evidence spans
    → queue uncertain, ambiguous, or failed records for review
    → assign provisional taxonomy after pilot review  → ClusterAssignment
    → aggregate and compare
    → export public profile
    → serve deterministic evaluator views
    → optionally synthesize answers from retrieved evidence
```

Every stage emits `StageEvent` rows (Section 15.8). Progress is the append-only event history, not a status column on the document.

The evaluator interface is a presentation layer over committed, validated outputs. It is not the source of truth.

### 13.1 Separation of concerns

- Collection must not perform final classification.
- Normalization must not overwrite raw text.
- Deduplication must link rather than delete, and must not set a lifecycle state.
- Relevance filtering must run before full extraction.
- Extraction must not invent missing information.
- Extraction must not assign a cluster, and must not depend on a taxonomy version.
- Taxonomy discovery must follow the pilot rather than precede it.
- Analysis must operate on validated records only.
- Analysis must not define vocabularies; it reads the schema's.
- The deterministic application must work without an AI API key.
- Generative question answering must be optional and failure-safe.
- No contract may require a field produced by a later stage (Section 15.0).

---

## 14. Repository Structure

The target structure is:

```text
google-photos-retrieval-engine/
├── app.py
├── main.py
├── pyproject.toml
├── README.md
├── problem-statement.md
├── STATUS.md
├── DECISIONS.md
├── CHANGELOG.md
├── .env.example
├── .gitignore
├── config/
│   ├── sources.yaml
│   ├── taxonomy.yaml
│   └── models.yaml
├── data/
│   ├── manual/
│   ├── raw/                      # local only, never committed
│   ├── interim/                  # local only, rebuildable
│   ├── processed/
│   ├── gold/
│   │   ├── documents.jsonl       # GoldDocumentLabel, split dev | holdout
│   │   └── cases.jsonl           # GoldCase, zero to many per document
│   └── exports/
│       ├── public/               # PublicExportRecord, committed
│       └── runs/                 # run manifests
├── prototype/
│   └── original Claude-generated reference files
├── src/
│   ├── collect/
│   │   ├── base.py
│   │   ├── manual.py            # guaranteed baseline
│   │   ├── youtube.py           # supported automated
│   │   └── reddit.py            # optional, credential-dependent
│   │   # No play_store.py, app_store.py, or support_forum.py: both store APIs are
│   │   # publisher-gated and the forum has no permission basis (Section 11.4, ADR-22).
│   │   # These three sources are collected through manual.py.
│   ├── models/
│   │   ├── collected_document.py
│   │   ├── document_derived.py
│   │   ├── duplicate_link.py
│   │   ├── evidence.py
│   │   ├── relevance.py
│   │   ├── retrieval_case.py
│   │   ├── stage_event.py
│   │   ├── cluster_assignment.py
│   │   ├── gold.py
│   │   ├── export.py
│   │   ├── evidence_map.py
│   │   └── enums.py
│   ├── normalize/
│   │   ├── text.py
│   │   ├── privacy.py
│   │   └── canonicalize.py
│   ├── dedupe/
│   │   ├── exact.py
│   │   └── near_duplicate.py
│   ├── relevance/
│   │   ├── rules.py
│   │   ├── classifier.py
│   │   └── prompts.py
│   ├── extract/
│   │   ├── extractor.py
│   │   ├── prompts.py
│   │   ├── validator.py
│   │   └── cache.py
│   ├── taxonomy/
│   │   ├── candidates.py
│   │   └── assign.py
│   ├── analyze/
│   │   ├── funnel.py
│   │   ├── memory_map.py
│   │   ├── journeys.py
│   │   └── opportunities.py
│   ├── retrieve/
│   │   ├── rank.py
│   │   ├── answer.py
│   │   └── citations.py
│   └── store/
│       ├── database.py
│       ├── migrations.py
│       └── export.py
├── scripts/
│   ├── check_credentials.py
│   ├── validate_dataset.py
│   ├── audit_sources.py
│   └── build_exports.py
└── tests/
    ├── fixtures/
    ├── test_models.py
    ├── test_evidence.py
    ├── test_manual_import.py
    ├── test_normalize.py
    ├── test_dedupe.py
    ├── test_relevance.py
    ├── test_extraction.py
    ├── test_evidence_map.py
    ├── test_stage_events.py
    ├── test_gold.py
    ├── test_evaluation.py
    ├── test_analysis.py
    ├── test_retrieval.py
    ├── test_export_profile.py
    └── test_app.py
```

The precise module split may evolve, but the separation of collection, normalization, deduplication, relevance, extraction, taxonomy, analysis, retrieval, and presentation is required.

---

## 15. Data Contracts

All production records must validate through Pydantic models. Use strict enums where specified. Where a value is absent, record *why* it is absent using `DimensionObservationStatus` (Section 16.9) rather than inventing a placeholder value such as `unknown`.

### 15.0 Contract inventory and stage ownership

Each contract is written by exactly one stage. The governing rule:

> **A contract must never require a field that a later stage produces.**

This is what allows Phase 1 schemas and Phase 2 manual import to be complete and valid on their own, with no normalization, hashing, deduplication, classification, or extraction in place.

| Contract | First written by | Section |
|---|---|---|
| `CollectedDocument` | collection / manual import (Phase 2) | 15.1 |
| `EvidenceSpan` | relevance and extraction (Phases 4–5) | 15.2 |
| `RelevanceDecision` | relevance classification (Phase 4) | 15.3 |
| `RetrievalCase` | extraction (Phase 5) | 15.4 |
| `ObservedValue` | relevance and extraction (Phases 4–5) | 15.5 |
| `DocumentDerived` | normalization (Phase 3) | 15.6 |
| `DuplicateLink` | deduplication (Phase 3) | 15.7 |
| `StageEvent` | every stage, from import onward | 15.8 |
| `ClusterAssignment` | taxonomy assignment (Phase 8) | 15.9 |
| `GoldDocumentLabel`, `GoldCase` | gold labelling (Phase 6) | 15.11 |
| `PublicExportRecord` | export (Phase 10) | 15.12 |

### 15.1 `CollectedDocument`

Immutable collection-time provenance and raw text only. This record is complete the moment a document is imported. Nothing in it depends on normalization, canonical hashing, deduplication, classification, or extraction.

| Field | Type | Description |
|---|---|---|
| `schema_version` | string | Contract version that produced this record. |
| `doc_id` | string | Stable deterministic identifier, derivable at import time from collection-time values only (Section 26.1). |
| `ingest_batch_id` | string | Batch that imported this document. |
| `source_platform` | enum | `play_store`, `app_store`, `reddit`, `google_support`, `youtube`, `forum`, `social`, `editorial`, `manual_other`. |
| `source_type` | enum | `review`, `post`, `comment`, `support_thread`, `forum_reply`, `video_comment`, `editorial_article`, `other`. |
| `evidence_tier` | enum | `direct_user`, `second_hand`, `contextual_editorial`, `synthetic_test`. |
| `source_item_id` | string or null | Platform-native item, comment, or reply identifier. |
| `parent_thread_id` | string or null | Parent discussion identifier. |
| `source_url` | URL | Direct permalink wherever possible, stored exactly as collected. |
| `source_url_key` | string | Deterministic import-time URL normalization: lowercased scheme and host, fragment removed, known tracking parameters removed, trailing slash collapsed. Used for `doc_id` derivation and for detecting re-ingestion of the same source item. Distinct from the Phase 3 `canonical_url`, which may additionally resolve share-link and redirect forms. |
| `source_name` | string | Human-readable source name. |
| `title` | string or null | Post, thread, article, or video title. |
| `author_hash` | string or null | Salted deterministic author hash. A plaintext username must never be stored in this or any downstream record. |
| `author_salt_id` | string | Identifier of the salt used, never the salt value, so a salt rotation is detectable. |
| `published_at` | datetime or null | Original publication time when verifiable. |
| `collected_at` | datetime | Collection timestamp. |
| `language_reported` | string or null | Language as supplied by the source or by the importer. Language *detection* is a derived field (Section 15.6). |
| `raw_text` | string | Original collected text, verbatim. The only coordinate space for evidence offsets. |
| `raw_text_sha256` | string | SHA-256 of `raw_text` exactly as collected. A pure function of raw text, therefore available at import. This is **not** `content_hash`, which is a canonicalized Phase 3 value. |
| `collection_query` | string or null | Search query or source filter used to find the item. |
| `collection_method` | enum | `api`, `permitted_scraper`, `manual_csv`, `manual_jsonl`, `manual_copy`, `other`. |
| `rating` | number or null | Store rating where applicable. |
| `engagement` | object or null | Source-specific public engagement metadata. |
| `metadata` | object | Additional source-specific metadata. |

Fields that previously lived on `RawDocument` and now live where they are actually produced:

| Former `RawDocument` field | Now lives in |
|---|---|
| `normalized_text` | `DocumentDerived.normalized_text` (15.6) |
| `content_hash` | `DocumentDerived.content_hash` (15.6) |
| `redactions` | `DocumentDerived.redaction_spans` (15.6) |
| `language` (detected) | `DocumentDerived.language_detected` (15.6); the collected value is `language_reported` |
| `duplicate_of` | `DuplicateLink.canonical_doc_id` (15.7) |
| `duplicate_kind` | `DuplicateLink.duplicate_kind` (15.7) |

Rules:

- A `CollectedDocument` is written once. No `UPDATE` or `DELETE` is permitted against it.
- Validation of a `CollectedDocument` must succeed with **no** Phase 3 or later field present anywhere in the system. A test must assert this explicitly, because it is the property that keeps Phase 1 and Phase 2 independently completable.
- Manual CSV and JSONL import must never require a derived field. An importer that cannot produce `normalized_text` or `content_hash` is still a valid importer.
- Re-importing the same source item resolves to the same `doc_id` and must add no new document row (Section 26.1). It is recorded as a re-ingestion event, and if it arrives under a different natural key it becomes a `DuplicateLink` of kind `same_source_item` (Section 15.7).

### 15.2 `EvidenceSpan`

| Field | Type | Description |
|---|---|---|
| `evidence_id` | string | Deterministic identifier (Section 26.1). |
| `doc_id` | string | Document whose `raw_text` is the coordinate space. |
| `owner_type` | enum | `relevance_decision`, `retrieval_case`, `observed_value`, `severity`, `gold_case`. |
| `owner_id` | string | Identifier of the owning record. |
| `field_name` | string | The exact contract field this span supports. Must be a member of the evidence-required field map in Section 15.10. |
| `quote` | string | Exact substring from the document's `raw_text`. |
| `start_char` | integer or null | Starting character offset. Null only while unresolved (Section 26.3). |
| `end_char` | integer or null | Exclusive ending character offset. Null only while unresolved. |
| `speaker` | enum | `author`, `quoted_other`, `editorial_author`, `unattributed`. |
| `offset_state` | enum | `supplied_exact`, `repaired_unique`, `repaired_nearest`, `repaired_whitespace`, `missing_unresolved`, `ambiguous_tied`. |
| `validation_state` | enum | `pending`, `valid`, `rejected`. |
| `repair_applied` | boolean | True when any repair step changed the offsets. |

Validation requirements:

- `quote == raw_text[start_char:end_char]` must be true before `validation_state` may become `valid`.
- Whitespace-normalized matching may be used only as a repair step and must preserve the displayed original substring.
- A generated paraphrase must never be stored as `quote`.
- Evidence spans must be short enough to audit but long enough to justify the field.
- A span whose offsets cannot be resolved, or whose quote occurs at multiple positions with no way to choose between them, is handled by the rules in Section 26.3. It is never silently dropped and never guessed.
- The `unattributed` speaker value replaces the former `unknown`: it means the source text does not attribute the words, which is a statement about the source, not about an analysis gap.

### 15.3 `RelevanceDecision`

| Field | Type | Description |
|---|---|---|
| `decision_id` | string | Deterministic identifier. |
| `doc_id` | string | Parent document. |
| `scope_class` | enum or null | `core_incomplete_recall`, `adjacent_known_item_retrieval`, `out_of_scope`. Null **only** when `technical_state` is not `ok`. |
| `is_relevant` | boolean or null | **Derived, never predicted.** See the derivation rule below. |
| `reason_code` | enum | Controlled inclusion, exclusion, or review reason (Section 16.8). |
| `reason_summary` | string | Concise model or analyst explanation. Never displayed in quotation marks. |
| `confidence` | number or null | Value from 0 to 1. Null when no decision was produced. |
| `technical_state` | enum | `ok`, or a failure state from Section 16.10. |
| `evidence` | array of `EvidenceSpan` | Non-empty for every decision, including `out_of_scope`. Empty **only** when `technical_state` is not `ok`. |
| `decided_by` | enum | `rules`, `llm`, `human`. |
| `model_name` | string or null | Model identifier, null for `rules` and `human`. |
| `prompt_version` | string or null | Prompt version, null for `rules` and `human`. |
| `ruleset_version` | string or null | Deterministic ruleset version where applicable. |
| `schema_version` | string | Contract version. |
| `decision_fingerprint` | string | Section 26.2. |
| `decided_at` | datetime | Decision timestamp. |
| `needs_human_review` | boolean | True for uncertain, conflicting, or technically failed cases. |

**Derivation rule for `is_relevant`.** `is_relevant` is computed from `scope_class` and is never requested from a model or an analyst:

```text
is_relevant = scope_class in {core_incomplete_recall, adjacent_known_item_retrieval}
```

Any `is_relevant` value present in a model response is discarded before validation. The validator must reject a stored record whose `is_relevant` disagrees with its `scope_class`, and a test must cover that rejection. Predicting relevance separately from scope was the source of an internal contradiction: two fields could disagree about the same document with nothing to arbitrate between them.

**Evidence requirement covers all three classes.** An `out_of_scope` decision is a substantive claim about a document and needs a verbatim span that shows why — the storage complaint, the billing question, the editorial framing. "No evidence because nothing was relevant" is not acceptable; the evidence supports the *exclusion*.

**Technical failure is a separate state, not a scope class.** When the provider is unavailable, the response cannot be parsed, or the response fails schema validation, there is no decision. The record carries the failure in `technical_state`, leaves `scope_class`, `is_relevant`, and `confidence` null, leaves `evidence` empty, and sets `needs_human_review`. Such records are counted on their own funnel line (Section 21.1) and must never be counted as `out_of_scope`, because a provider outage is not a finding about a user.

| `technical_state` | `scope_class` | `is_relevant` | `evidence` | Counted as |
|---|---|---|---|---|
| `ok` | required | derived | non-empty | a classified document |
| anything else | null | null | empty | `relevance_unavailable` |

### 15.4 `RetrievalCase`

Every substantive field in this contract carries a paired `*_observation` field holding a `DimensionObservationStatus` (Section 16.9). The status determines whether a value and evidence are required, permitted, or forbidden — see the status contract in Section 15.10.

| Field | Type | Description |
|---|---|---|
| `case_id` | string | Stable case identifier (Section 26.1). |
| `doc_id` | string | Parent collected document. |
| `schema_version` | string | Contract version. |
| `scope_class` | enum | Inherited validated scope class. |
| `known_item_status` | enum or null | `explicit`, `probable`. |
| `known_item_status_observation` | enum | Observation status. `uncertain` replaces the former `unclear` value. |
| `target_asset_type` | enum or null | `photo`, `video`, `screenshot`, `document_image`, `mixed`, `other`. |
| `target_asset_type_observation` | enum | Observation status. Replaces the former `unknown` enum member. |
| `target_subjects` | array of `ObservedValue[SubjectType]` | Controlled subject type plus optional free-text `subject_detail` (Section 16.7). Subject is separate from asset type. |
| `target_subjects_observation` | enum | Observation status. |
| `retrieval_trigger` | string or null | Why the user needed the item, when explicitly stated. |
| `retrieval_trigger_observation` | enum | Observation status. |
| `remembered_cues` | array of `ObservedValue[RememberedCue]` | What the user explicitly remembers. |
| `remembered_cues_observation` | enum | Observation status. |
| `forgotten_information` | array of `ObservedValue[ForgottenInfo]` | What the user explicitly forgot or was unsure about. |
| `forgotten_information_observation` | enum | Observation status. `not_stated` is the default and must never be read as "forgot nothing"; `explicitly_none` is the only value that carries that meaning. |
| `exact_query` | string or null | Exact query only when directly quoted or clearly delimited in the source. |
| `exact_query_observation` | enum | Observation status. |
| `query_paraphrase` | string or null | Clearly labeled analyst or model summary when no exact query exists. Never rendered in quotation marks. |
| `query_paraphrase_observation` | enum | Observation status. |
| `query_strategies` | array of `ObservedValue[QueryStrategy]` | Search or browsing approaches supported by evidence. |
| `query_strategies_observation` | enum | Observation status. `explicitly_none` covers a user who states they could not formulate any query (Section 9.1). |
| `reformulation_count` | integer or null | Only when explicit or deterministically countable. |
| `reformulation_count_observation` | enum | Observation status. |
| `system_responses` | array of `ObservedValue[SystemResponse]` | Returned behavior or failure supported by evidence. |
| `system_responses_observation` | enum | Observation status. |
| `workarounds` | array of `ObservedValue[Workaround]` | Actions taken after failure. |
| `workarounds_observation` | enum | Observation status. `explicitly_none` replaces the former `none_stated` enum member. |
| `outcome` | enum or null | `found`, `partially_found`, `not_found`, `abandoned`, `unresolved`. |
| `outcome_observation` | enum | Observation status. Replaces the former `unknown` enum member; `unresolved` now means the user stated the attempt ended without resolution, which is a finding, not a gap. |
| `impact_signals` | array of `ObservedValue[ImpactSignal]` | Controlled impact signals (Section 16.6). |
| `impact_signals_observation` | enum | Observation status. |
| `severity` | integer or null | Evidence-based 1–5 rating using Section 18. |
| `severity_observation` | enum | Observation status. |
| `severity_evidence` | array of `EvidenceSpan` | Required and non-empty whenever `severity` is not null. |
| `problem_summary` | string | Concise interpretation, never presented as a user quote. |
| `all_evidence_spans` | array of `EvidenceSpan` | **Derived.** The de-duplicated union of every field-level evidence span on this case, including `severity_evidence` and every `ObservedValue.evidence`. Computed by the validator, never authored by a model or an analyst (Section 15.10). |
| `uncertainty_notes` | array | Missing, ambiguous, or conflicting details. |
| `extractor_type` | enum | `human`, `llm`, `rules`, `hybrid`. |
| `model_name` | string or null | AI model used. |
| `prompt_version` | string | Extraction prompt version. |
| `extraction_fingerprint` | string | Section 26.2. Does **not** include `taxonomy_version`. |
| `extracted_at` | datetime | Extraction time. |
| `needs_human_review` | boolean | Review flag. |

Fields deliberately **not** present on this contract:

| Removed field | Where it lives now | Why |
|---|---|---|
| `candidate_cluster` | `ClusterAssignment.cluster_id` (15.9) | A cluster label on the extraction record makes extraction depend on a taxonomy that Section 20 forbids until after pilot review. Extraction writes `problem_summary` and nothing else about grouping. |
| `cluster_confidence` | `ClusterAssignment.confidence` (15.9) | Same reason. |
| `taxonomy_version` | `ClusterAssignment.taxonomy_version` (15.9) | A case's extracted content does not change when the taxonomy is revised. Keeping the taxonomy version on the case forced every case to be re-extracted — at full model cost — for a change that only affects grouping. |

### 15.5 `ObservedValue` (evidence-backed label)

Every member of `target_subjects`, `remembered_cues`, `forgotten_information`, `query_strategies`, `system_responses`, `workarounds`, and `impact_signals` is an `ObservedValue`:

| Field | Type | Description |
|---|---|---|
| `value` | enum | A member of the controlled vocabulary for that dimension. |
| `detail` | string or null | Optional free text, used only where the dimension permits it (currently `target_subjects.subject_detail`). Treated as a paraphrase, never as a quote. |
| `evidence` | `EvidenceSpan` | Required. A value without evidence is not storable. |

```json
{
  "value": "approximate_time",
  "detail": null,
  "evidence": {
    "field_name": "remembered_cues",
    "quote": "I think it was sometime last summer",
    "start_char": 14,
    "end_char": 52,
    "speaker": "author",
    "offset_state": "supplied_exact"
  }
}
```

### 15.6 `DocumentDerived`

Produced by normalization (Phase 3). One row per document. Rebuildable at any time from the `CollectedDocument` plus the normalizer version — it holds no independent truth.

| Field | Type | Description |
|---|---|---|
| `doc_id` | string | Parent collected document. |
| `normalized_text` | string | NFKC, lowercased, whitespace-collapsed text used for matching, prefiltering, and lexical retrieval. Never used for evidence offsets. |
| `raw_text_audit` | string | `raw_text` with each detected PII span replaced by a mask of **identical character length**, so every evidence offset remains valid against it. This is the text sent to model providers and shown to evaluators. |
| `redaction_spans` | array | One entry per masked region: `start_char`, `end_char`, `redaction_type`, `detector_version`. |
| `canonical_url` | string | Canonicalized permalink: tracking parameters stripped, host normalized, known share-link and redirect forms resolved. May require a network lookup, which is why it is derived rather than collected. |
| `content_hash` | string | SHA-256 of the canonicalized text (NFKC, lowercased, whitespace collapsed, URLs and punctuation stripped). Used for exact-duplicate grouping and for cache and fingerprint keys. |
| `simhash` | string | 64-bit simhash over 3-word shingles of `normalized_text`, for near-duplicate blocking. |
| `token_count` | integer | Token count of `normalized_text`. Drives the minimum-length guard in Section 15.7. |
| `language_detected` | string or null | Detected language code. Null when detection is unavailable or inconclusive; the collected `language_reported` is not overwritten. |
| `language_detector_version` | string or null | Detector identifier and version. |
| `normalizer_version` | string | Version of the normalization ruleset that produced this row. |
| `derived_at` | datetime | Derivation timestamp. |

Rules:

- `len(raw_text_audit) == len(raw_text)` must hold. This assertion is what keeps every evidence offset valid, and it is a test, not a comment.
- An evidence span overlapping any `redaction_spans` entry is rejected. Evidence must never depend on personal data.
- Re-running normalization with the same `normalizer_version` must produce an identical row.

### 15.7 `DuplicateLink`

Produced by deduplication (Phase 3). Duplicate status is a **relationship between two documents**, not a state of either one, and not a lifecycle stage. A document with a `DuplicateLink` continues through every downstream stage and keeps its extracted cases; it is excluded at the analysis layer by the prevalence views (Section 21), which is what preserves auditability while preventing inflation.

| Field | Type | Description |
|---|---|---|
| `link_id` | string | Deterministic identifier. |
| `doc_id` | string | The duplicate document. |
| `canonical_doc_id` | string | The document chosen as canonical for this group (Section 26.1). |
| `duplicate_kind` | enum | `same_source_item`, `exact_text`, `near`, `cross_post`, `quoted_repeat` (Section 16.11). |
| `similarity` | number or null | Comparison score. Simhash Hamming distance is stored as a normalized similarity plus the raw distance in `method_detail`. |
| `method` | enum | `source_item_key`, `content_hash`, `simhash`, `human`. |
| `method_version` | string | Version of the detection ruleset and its thresholds. |
| `method_detail` | object | Raw comparison details, including the raw Hamming distance and both token counts. |
| `review_state` | enum | `auto_confirmed`, `pending_review`, `human_confirmed`, `human_rejected` (Section 16.11). |
| `decided_by` | enum | `rules`, `human`. |
| `decided_at` | datetime | Decision timestamp. |
| `review_reason_code` | enum or null | Why review was required, when `review_state` is not `auto_confirmed`. |

A link with `review_state = human_rejected` is retained. It records that a pair was considered and found distinct, which is exactly the evidence a reader needs to trust the duplicate rate.

### 15.8 `StageEvent`

Append-only processing status. This replaces the former single `doc_state` lifecycle column entirely.

| Field | Type | Description |
|---|---|---|
| `event_id` | string | Deterministic identifier. |
| `target_type` | enum | `document`, `case`, `batch`. |
| `target_id` | string | `doc_id`, `case_id`, or `ingest_batch_id`. |
| `stage` | enum | `import`, `normalize`, `dedupe`, `prefilter`, `relevance`, `extract`, `validate`, `taxonomy_assign`, `analyze`, `export`. |
| `status` | enum | `started`, `succeeded`, `failed`, `skipped`, `dropped`, `unavailable`. |
| `reason_code` | enum or null | Why, for every status other than `succeeded`. |
| `attempt` | integer | Attempt number within the run. |
| `run_id` | string | Run that emitted the event. |
| `occurred_at` | datetime | Event time. |
| `detail` | object | Stage-specific payload, for example prefilter matched rules or validation error classes. |

Rules:

- Events are **append-only**. A later event never rewrites an earlier one; the history of what the pipeline did is itself the audit trail.
- The current status of a document at a stage is the latest event for that `(target_id, stage)` pair. There is no single column that claims to summarize a document's position in the pipeline, because no single column can: a document is simultaneously imported, normalized, marked as a duplicate, prefilter-passed, classified, and extracted.
- Section 21.1's funnel is computed per stage from these events. Every document that reached a stage appears at that stage, and the same document correctly appears at every stage it reached.
- Failure and unavailability are ordinary statuses with reason codes, so they are countable on their own funnel lines rather than being inferred from an absence.

### 15.9 `ClusterAssignment`

Produced by taxonomy assignment (Phase 8), which is the only place a cluster label may exist.

| Field | Type | Description |
|---|---|---|
| `case_id` | string | Case being assigned. |
| `taxonomy_version` | string | Taxonomy version, part of the key. |
| `cluster_id` | string | Assigned cluster, including the permanent `other` and `uncertain` members. |
| `confidence` | number or null | Value from 0 to 1. |
| `method` | enum | `rules`, `llm`, `human`. |
| `model_name` | string or null | Model used, where applicable. |
| `prompt_version` | string or null | Prompt version, where applicable. |
| `assignment_fingerprint` | string | Section 26.2. This is the **only** fingerprint that includes `taxonomy_version`. |
| `assigned_at` | datetime | Assignment timestamp. |

Keyed by `(case_id, taxonomy_version, assignment_fingerprint)`, so re-assigning under a revised taxonomy adds rows and preserves earlier versions.

### 15.10 Evidence-required field map and exception list

Evidence enforcement is a table in configuration, not a habit. The validator reads this map and refuses any record that violates it; a test asserts that every field on `RelevanceDecision` and `RetrievalCase` appears in exactly one of the two lists below, so a newly added field cannot quietly escape enforcement.

**Evidence-required fields.** Each of these is a substantive claim about a user and requires at least one valid field-level `EvidenceSpan` whose `field_name` matches:

| Contract | Field | Evidence `field_name` |
|---|---|---|
| `RelevanceDecision` | `scope_class` | `scope_class` |
| `RetrievalCase` | `known_item_status` | `known_item_status` |
| `RetrievalCase` | `target_asset_type` | `target_asset_type` |
| `RetrievalCase` | `target_subjects` | `target_subjects` (per `ObservedValue`) |
| `RetrievalCase` | `retrieval_trigger` | `retrieval_trigger` |
| `RetrievalCase` | `remembered_cues` | `remembered_cues` (per `ObservedValue`) |
| `RetrievalCase` | `forgotten_information` | `forgotten_information` (per `ObservedValue`) |
| `RetrievalCase` | `exact_query` | `exact_query` |
| `RetrievalCase` | `query_paraphrase` | `query_paraphrase` |
| `RetrievalCase` | `query_strategies` | `query_strategies` (per `ObservedValue`) |
| `RetrievalCase` | `reformulation_count` | `reformulation_count` |
| `RetrievalCase` | `system_responses` | `system_responses` (per `ObservedValue`) |
| `RetrievalCase` | `workarounds` | `workarounds` (per `ObservedValue`) |
| `RetrievalCase` | `outcome` | `outcome` |
| `RetrievalCase` | `impact_signals` | `impact_signals` (per `ObservedValue`) |
| `RetrievalCase` | `severity` | `severity` (stored in `severity_evidence`) |
| `RetrievalCase` | `problem_summary` | `problem_summary` |

`query_paraphrase` is on this list deliberately. A paraphrase is still a claim that the user described a search, so it needs a span showing the described search. What makes it a paraphrase rather than a quote is how it is *displayed*, not whether it is evidenced.

**Evidence-exempt fields.** This list is closed. It contains only identifiers, provenance, versions, and uncertainty metadata — never a substantive claim about a user:

| Category | Fields |
|---|---|
| Identifiers | `case_id`, `doc_id`, `decision_id`, `link_id`, `event_id`, `evidence_id`, `ingest_batch_id`, `run_id`, `cluster_id` |
| Provenance | `extractor_type`, `decided_by`, `method`, `model_name`, `extracted_at`, `decided_at`, `assigned_at`, `derived_at`, `occurred_at`, `collected_at`, `collection_method`, `collection_query`, `source_*`, `author_hash`, `author_salt_id`, `ingest_batch_id` |
| Versions | `schema_version`, `prompt_version`, `ruleset_version`, `normalizer_version`, `taxonomy_version`, `method_version`, `language_detector_version`, `extraction_fingerprint`, `decision_fingerprint`, `assignment_fingerprint` |
| Uncertainty metadata | every `*_observation` field, `confidence`, `needs_human_review`, `uncertainty_notes`, `technical_state`, `validation_state`, `offset_state`, `review_state`, `reason_code`, `review_reason_code` |
| Derived | `is_relevant`, `all_evidence_spans` |

**How observation status gates the requirement.** For every evidence-required field:

| `*_observation` | Value | Field-level evidence | Meaning |
|---|---|---|---|
| `stated` | required | **required**, ≥ 1 valid span | The user said it. |
| `explicitly_none` | must be null or empty | **required**, ≥ 1 valid span | The user affirmatively said there was none — they remembered everything, tried no workaround, ran no search. This is a finding and needs proof. |
| `uncertain` | optional, flagged | **required**, ≥ 1 valid span | The user said something, but it is ambiguous or self-contradictory. The span is the ambiguous text. |
| `not_stated` | must be null or empty | **must be empty** | The source is silent. The default. Never an inference. |
| `not_applicable` | must be null or empty | **must be empty** | The field cannot apply to this case, for example `reformulation_count` where no query was ever formulated. |

**`all_evidence_spans` is derived, not primary.** It is the de-duplicated union of every field-level span on the case. Three consequences:

1. The validator computes it; a model-supplied value is discarded.
2. A span present in `all_evidence_spans` but attached to no field is a contradiction and fails validation. This closes the loophole where a model could satisfy a bulk evidence check by attaching a pile of plausible quotes to nothing in particular.
3. Removing a field's evidence must change `all_evidence_spans`. A test asserts the union property directly.

### 15.11 Gold-set contracts

Document-level relevance labelling and case-level extraction labelling are separate records, because they answer different questions and are measured with different metrics (Section 24, Phase 6).

`GoldDocumentLabel` — exactly one per gold document:

| Field | Type | Description |
|---|---|---|
| `doc_id` | string | Labelled document. |
| `split` | enum | `dev` or `holdout` (Section 24, Phase 6). |
| `scope_class` | enum | Gold scope class. |
| `is_relevant` | boolean | Derived from `scope_class` by the same rule as Section 15.3. |
| `reason_code` | enum | Gold inclusion or exclusion reason. |
| `prefilter_should_pass` | boolean | Whether a correct high-recall prefilter must let this document through. Measures prefilter recall independently of the classifier. |
| `expected_case_count` | integer | 0, 1, or more. Zero is a valid and expected label. |
| `labeler_id` | string | Pseudonymous reviewer identifier. |
| `labeled_at` | datetime | Label timestamp. |
| `adjudicated` | boolean | True when a disagreement was resolved. |
| `pre_adjudication_labels` | array | Every independent reviewer label, retained. Inter-reviewer agreement is computed from these, before adjudication (Section 24, Phase 6). |
| `notes` | string or null | Reviewer notes, especially boundary reasoning. |

`GoldCase` — zero, one, or many per document:

| Field | Type | Description |
|---|---|---|
| `gold_case_id` | string | `{doc_id}#g{ordinal:02d}`. |
| `doc_id` | string | Parent document. |
| `expected_values` | object | Per-field expected `{observation, value}` pairs using the same vocabularies as Section 15.4. |
| `expected_evidence` | array | Verbatim quotes the reviewer considers sufficient support, per field. |
| `labeler_id` | string | Reviewer. |
| `adjudicated` | boolean | Disagreement resolved. |
| `notes` | string or null | Reviewer notes. |

Rules:

- A document with `expected_case_count = 0` has no `GoldCase` rows and is still a full participant in relevance metrics. Case-level metrics simply have nothing to compare, which is correct rather than a gap.
- A document with several `GoldCase` rows is matched to extracted cases before scoring, by evidence-span overlap, so a correct extraction that emits cases in a different order is not penalized. The matching rule is part of the evaluation script and is versioned with it.
- `GoldCase` `expected_evidence` quotes are validated against `raw_text` by the same validator as production evidence. A gold label containing a paraphrase is a defect in the gold set.

### 15.12 `PublicExportRecord`

The contract for the public, committed export. See Section 12.1 for the policy this implements.

| Field | Type | Description |
|---|---|---|
| `case_id`, `doc_id` | string | Identifiers. |
| `source_platform`, `source_type`, `evidence_tier`, `source_name` | enum / string | Provenance. |
| `source_url`, `canonical_url` | string | Source links, so a reader can go to the original. |
| `published_at`, `collected_at` | datetime or null | Dates. |
| `author_key` | string or null | Truncated `author_hash`, sufficient to count distinct authors, insufficient to identify one. Never a username, never the salt. |
| `excerpt` | string | The **minimum redacted excerpt** that contains every validated evidence span for this record, plus the configured context window. Not the full document, unless Section 12.1's redistribution condition is met. |
| `excerpt_start_char` | integer | Offset of `excerpt` within `raw_text_audit`, so excerpt-relative offsets can be mapped back to document coordinates. |
| `excerpt_is_full_text` | boolean | True only when redistribution terms explicitly permit full text. |
| `evidence_spans` | array | Validated spans with offsets **rebased to the excerpt**, plus their original document offsets. |
| extracted fields | various | The Section 15.4 values, observation statuses, and `ObservedValue` values. |
| `cluster_id`, `taxonomy_version` | string or null | Current assignment, when a taxonomy exists. |
| versions | string | Schema, prompt, normalizer, and dataset versions. |

Forbidden in a public export, enforced by a test over the generated artifact rather than by review: plaintext usernames, author display names, the author salt, API keys or credentials, unredacted PII, email addresses, phone numbers, and raw text outside the permitted excerpt.

---

## 16. Controlled Dimensions

These values are initial extraction dimensions, not the final opportunity taxonomy.

**Absence is recorded by status, not by a vocabulary member.** No dimension below contains an `unknown` or `none_stated` member. When a dimension is not observed, the paired `*_observation` field carries the reason (Section 16.9) and the value stays null or empty. This keeps one meaning per value: every member of every vocabulary below is something a user actually said. The specific members removed for this reason are `QueryStrategy.unknown`, `SystemResponse.unknown`, `Workaround.none_stated`, `TargetAssetType.unknown`, `Outcome.unknown`, `KnownItemStatus.unclear`, and `Speaker.unknown`.

`other` remains available in every vocabulary, because "the user said something this list does not cover" is genuinely different from "the user said nothing."

### 16.1 Remembered cues

- `person_identity`
- `relationship`
- `approximate_time`
- `approximate_place`
- `event_or_occasion`
- `activity`
- `object_or_subject`
- `visual_appearance`
- `text_fragment`
- `surrounding_context`
- `emotion_or_feeling`
- `sequence_or_before_after`
- `source_or_device`
- `other`

### 16.2 Forgotten or uncertain information

- `exact_date`
- `exact_time`
- `place_name`
- `person_name`
- `object_name`
- `exact_text`
- `album`
- `capture_device`
- `file_type`
- `search_term`
- `storage_location`
- `other`

Do not infer a forgotten value from non-mention.

### 16.3 Query strategies

- `single_keyword`
- `multiple_keywords`
- `natural_language_description`
- `person_or_face_search`
- `date_filter`
- `place_filter`
- `album_browsing`
- `category_browsing`
- `manual_scrolling`
- `repeated_reformulation`
- `external_app_or_search`
- `asked_another_person`
- `no_query_formulated`
- `other`

`no_query_formulated` records a user who wanted to retrieve a known item and states they could not turn their memory into a search at all. It is a behaviour, not an absence of one, and Section 9.1 depends on it.

### 16.4 System responses and failure modes

- `no_results`
- `irrelevant_results`
- `too_many_results`
- `partial_results`
- `known_item_not_surfaced`
- `summary_instead_of_asset`
- `face_mismatch_or_omission`
- `text_not_recognized`
- `filter_or_scope_mismatch`
- `could_not_form_query`
- `inconsistent_results`
- `other`

### 16.5 Workarounds

- `rephrased_query`
- `guessed_date`
- `manual_scrolling`
- `browsed_album`
- `used_people_view`
- `used_map_or_location_view`
- `added_caption_or_label`
- `used_external_app`
- `asked_someone_else`
- `disabled_ai_feature`
- `saved_or_reorganized_content`
- `gave_up`
- `other`

### 16.6 Impact signals

`ImpactSignal` describes a demonstrated or explicitly stated effect of the retrieval difficulty. It is the input to the severity rubric in Section 18, and it must never be inferred from tone.

- `time_loss` — the user states the attempt consumed meaningful time.
- `repeat_effort` — the user returned to the same search across separate sittings.
- `task_failure` — the user could not complete the task the item was needed for.
- `task_delay` — the task completed late because of the retrieval difficulty.
- `external_dependency` — the user had to rely on another app, service, or person.
- `urgency_or_deadline` — the user states a time constraint.
- `trust_loss` — the user states reduced confidence in the product or its search.
- `stated_distress` — the user explicitly describes frustration, anxiety, or upset. A negative adjective alone is not this signal; the user must describe the effect on themselves.
- `considered_or_made_switch` — the user states they looked at, or moved to, an alternative product.
- `believed_data_lost` — the user concluded the item no longer exists, whether or not it does.
- `abandoned_goal` — the user gave up on the retrieval need itself.
- `financial_or_material_consequence` — the user states a concrete cost.
- `other`

`none_stated` is deliberately absent: use `impact_signals_observation = not_stated`, or `explicitly_none` when the user says the difficulty did not matter to them.

### 16.7 Subject types

`SubjectType` is what the remembered item *is about*, and it is independent of `target_asset_type`, which is what kind of file it is. A screenshot of a receipt is `target_asset_type = screenshot` with `SubjectType = receipt_or_invoice`.

- `person`
- `pet_or_animal`
- `document_or_paperwork`
- `receipt_or_invoice`
- `medicine_or_medical`
- `id_card_or_credential_image`
- `message_or_chat_capture`
- `app_or_web_capture`
- `food_or_meal`
- `place_or_venue`
- `event_or_occasion`
- `vehicle`
- `product_or_object`
- `artwork_whiteboard_or_notes`
- `text_or_handwriting`
- `nature_or_scenery`
- `clothing_or_appearance`
- `other`

Each `target_subjects` entry may carry an optional free-text `subject_detail`, for the specificity the controlled list cannot hold — `"the small café in Goa"`, `"my sister's yellow dress"`. Rules for `subject_detail`:

- It is a **paraphrase field**. It is never rendered in quotation marks and is never treated as an evidence quote.
- It is still evidence-required: the parent `ObservedValue.evidence` must support the subject.
- It must not contain a person's name, a full address, or any other identifier that Section 12 requires removing. Redaction applies to it exactly as to any other exported text.
- It is excluded from controlled-vocabulary aggregation. It appears in the evidence browser and in qualitative reading, never in a distribution chart, because free text cannot be counted honestly.

### 16.8 Reason codes

`ReasonCode` is one controlled vocabulary used by `RelevanceDecision.reason_code`, `DuplicateLink.review_reason_code`, `StageEvent.reason_code`, and the review queue. It has three groups, and a code from the wrong group is a validation error.

**Inclusion reasons** — valid when `scope_class` is `core_incomplete_recall` or `adjacent_known_item_retrieval`:

- `known_item_with_incomplete_recall` — the core pattern.
- `known_item_query_unformulable` — a known item the user cannot turn into a query at all (Section 9.1).
- `known_item_cue_not_recognized` — remembered cues exist but the system does not act on them.
- `known_item_with_precise_recall_failure` — adjacent: recall is precise, retrieval still fails.
- `known_item_retrieval_journey_described` — adjacent: a described journey without demonstrated incomplete recall.

**Exclusion reasons** — valid only when `scope_class` is `out_of_scope`:

- `no_known_item_target`
- `no_retrieval_need_or_attempt`
- `storage_backup_or_sync`
- `billing_or_subscription`
- `deletion_or_corruption`
- `account_access`
- `editing_sharing_or_printing`
- `organization_unrelated_to_retrieval`
- `general_ai_objection_without_retrieval`
- `casual_browsing_without_known_target`
- `editorial_or_hypothetical_example`
- `web_search_not_user_library`
- `insufficient_evidence_for_a_case`
- `out_of_scope_language`
- `other_out_of_scope`

**Review and processing reasons** — valid on review-queue items, duplicate links, and stage events; never valid as a `RelevanceDecision.reason_code` for a completed decision:

- `low_confidence`
- `prefilter_classifier_conflict`
- `evidence_validation_failed`
- `repair_ladder_exhausted`
- `severity_without_evidence`
- `observation_status_conflict`
- `near_duplicate_in_review_band`
- `short_text_below_dedupe_minimum`
- `different_authors_identical_text`
- `quoted_repeat_ambiguous`
- `multi_case_offset_tie`
- `evidence_offsets_unresolved`
- `provider_unavailable`
- `response_parse_failed`
- `schema_validation_failed`
- `rate_limited`
- `source_blocked`

### 16.9 Dimension observation status

`DimensionObservationStatus` is the single vocabulary for *why* a value is present or absent. It replaces every per-dimension `unknown` member and every analysis-layer invention of the same idea.

| Status | Meaning | Value | Evidence |
|---|---|---|---|
| `stated` | The user said it. | present | required |
| `not_stated` | The source is silent. This is the default and must never be read as a negative finding. | empty | forbidden |
| `explicitly_none` | The user affirmatively said there was none. A finding in its own right. | empty | required |
| `uncertain` | The user said something ambiguous, hedged, or self-contradictory. | optional | required |
| `not_applicable` | The dimension cannot apply to this case. | empty | forbidden |

Two rules make this load-bearing:

1. **`not_stated` and `explicitly_none` are never merged.** Merging them converts silence into a finding, which is the exact error Section 8.4 forbids. Both appear as separate, visible rows in every cross-tab, including the memory map.
2. **Analysis may not invent statuses.** The analysis layer reads this vocabulary; it does not define its own. A status that matters to a chart must exist in the schema, be produced by extraction, and be evidenced.

### 16.10 Decision technical state

`DecisionTechnicalState` records whether a decision or extraction attempt actually happened. It is orthogonal to the finding and must never be encoded as a scope class, an outcome, or an observation status.

- `ok` — a real decision or extraction was produced.
- `provider_unavailable` — no key configured, or the provider is unreachable.
- `provider_error` — the provider returned an error.
- `timeout`
- `rate_limited`
- `response_parse_failed` — output was not parseable, after safe syntax cleanup.
- `schema_validation_failed` — parseable but not schema-valid, after the repair ladder.
- `evidence_validation_failed` — schema-valid but the evidence did not validate.
- `skipped_dry_run`

Any value other than `ok` means no finding exists. Such records are reported on their own funnel lines and are excluded from every prevalence, precision, and recall calculation, with the count of excluded records stated alongside.

### 16.11 Duplicate kinds and review states

`DuplicateKind`:

- `same_source_item` — the same platform item reached the corpus under two natural keys.
- `exact_text` — identical canonical content hash, different source items.
- `near` — high textual similarity below identity.
- `cross_post` — the same author posting substantially the same text to more than one venue.
- `quoted_repeat` — one document quotes another's text.

`DuplicateLink.review_state`:

- `auto_confirmed` — the rules were confident and the safety conditions in Section 19.6 were all satisfied.
- `pending_review` — flagged, awaiting a human. **Not** counted as a duplicate in any analysis until resolved; counted on its own funnel line.
- `human_confirmed`
- `human_rejected` — considered and found distinct. The row is retained as evidence that the pair was examined.

---

## 17. Evidence Integrity Rules

These rules are non-negotiable.

1. Every substantive extracted field must be supported by a verbatim span, as enumerated in the evidence-required field map in Section 15.10. The map is the authority; a field is enforced because it is in the map, not because someone remembered to check it.
2. The validator must confirm that every evidence quote occurs in `raw_text` at its stated offsets.
3. Exact queries must be stored only if directly quoted or clearly delimited in the source.
4. Paraphrases must be labeled as paraphrases and never displayed in quotation marks.
5. If the user does not state what they forgot, set `forgotten_information_observation = not_stated`, leave the list empty, and attach no evidence. Do not infer a forgotten value, and do not record `explicitly_none` unless the user affirmatively said they remembered everything relevant.
6. If the user does not state an outcome, set `outcome_observation = not_stated` and leave `outcome` null. `unresolved` is reserved for a user who states the attempt ended without resolution — it is a finding, not a placeholder for silence.
7. If severity cannot be justified, leave it null with `severity_observation = not_stated`.
8. Editorial examples must not be rewritten as first-person user problems.
9. One article describing multiple hypothetical scenarios does not create multiple user records.
10. Multiple comments in one thread may be separate documents only when each has a comment-level ID or permalink.
11. Duplicate or quoted text must not inflate frequency.
12. Model output that fails schema or evidence validation must be logged and sent to repair or review; it must not silently enter the analysis dataset.
13. Synthetic fixtures must be marked `synthetic_test` and excluded from every research output.
14. Every relevance decision requires evidence, including `out_of_scope`. Excluding a document is a claim about that document and must be supportable.
15. `is_relevant` is derived from `scope_class` and is never independently predicted (Section 15.3). A model-supplied value is discarded before validation.
16. `all_evidence_spans` is the derived union of field-level spans (Section 15.10). It is never the only evidence relationship, never authored directly, and never a substitute for field-level evidence. A span belonging to no field fails validation.
17. A value and its observation status must agree. A `stated` status with no value, a `not_stated` status with a value, or any status other than `stated`, `explicitly_none`, or `uncertain` carrying evidence, is a validation error routed to review — not a coercion.
18. A technical failure is never a finding. Provider unavailability, parse failure, and schema failure are recorded in `technical_state` (Section 16.10) and excluded from every precision, recall, and prevalence calculation, with the excluded count stated.
19. Free-text detail fields, including `subject_detail`, `reason_summary`, `problem_summary`, and `query_paraphrase`, are paraphrases. They are never quoted, never used as evidence, and never counted in a distribution.

---

## 18. Severity Rubric

Severity describes demonstrated retrieval impact, not the emotional tone of the post or the perceived importance of the content.

| Score | Evidence-based definition |
|---|---|
| 1 | Minor inconvenience; the item is found with little additional effort. |
| 2 | One or two reformulations or a short alternate path; retrieval succeeds. |
| 3 | Multiple attempts, meaningful manual browsing, or an inconvenient workaround; outcome may remain unresolved. |
| 4 | Prolonged effort, repeated failure, external-tool dependence, or inability to complete the intended task. |
| 5 | Explicit abandonment, repeated high-impact failure, or a clearly stated serious consequence caused by unsuccessful retrieval. |

Rules:

- Content about medicine, identity, finance, or travel is not automatically severity 5.
- A negative adjective is not sufficient severity evidence.
- Severity should be assigned using demonstrated behavior or consequence.
- Null severity is better than unsupported precision.

---

## 19. Relevance and Extraction Pipeline

### 19.1 Stage A — deterministic prefilter

Use high-recall keyword and structural rules to remove obvious unrelated content and prioritize likely retrieval discussions. The deterministic stage must not make final research claims.

### 19.2 Stage B — relevance classification

The classifier determines core, adjacent, or out-of-scope status. It returns a strict `RelevanceDecision` with evidence for **every** class, including `out_of_scope` (Section 15.3).

`is_relevant` is derived from `scope_class` after the response is parsed. The prompt must not ask for it, and any value the model supplies for it is discarded.

When no decision could be produced — provider unavailable, response unparseable, schema or evidence validation exhausted — the record carries the reason in `technical_state`, leaves `scope_class` null, and is counted as `relevance_unavailable`. A technical failure is never recorded as `out_of_scope`.

Low-confidence decisions, prefilter/classifier contradictions, and technically failed attempts enter the human-review queue.

### 19.3 Stage C — structured extraction

Run full extraction only for relevant core and adjacent documents. Require strict structured output and validate it through Pydantic.

### 19.4 Stage D — repair ladder

Use this order:

1. Parse original structured response.
2. Apply safe JSON cleanup without changing semantic values.
3. Request schema repair with validation errors.
4. Re-run extraction once with the original text and explicit error feedback.
5. If still invalid, log the failure and require human review.

Never silently drop or coerce an unsupported value.

### 19.5 Caching and resumption

Every model call's cache key must include:

- Document content hash.
- Model provider and model name.
- Prompt identifier and prompt version.
- Schema version.
- Decoding parameters that affect output.

**`taxonomy_version` appears in the cache key only for taxonomy-dependent stages.** Concretely, it is part of the taxonomy-assignment cache key and part of `assignment_fingerprint`, and it is absent from the prefilter, relevance, extraction, and Ask synthesis keys.

The reason is that extraction does not read the taxonomy. Including `taxonomy_version` in the extraction cache key meant that publishing taxonomy `v2` invalidated every cached extraction and re-ran the entire corpus through a paid model to produce byte-identical results. Worse, it created a real incentive to avoid revising the taxonomy, which is in direct tension with Section 20's requirement that the taxonomy be refined against evidence.

| Stage | Cache key includes `taxonomy_version`? |
|---|---|
| Prefilter | no |
| Relevance classification | no |
| Extraction | no |
| Taxonomy candidate generation | yes |
| Taxonomy assignment | yes |
| Ask synthesis | no — it keys on dataset version, which already moves when assignments change |

The same rule applies to record fingerprints (Section 26.2): `extraction_fingerprint` excludes `taxonomy_version`; `assignment_fingerprint` includes it.

The pipeline must support checkpointing, resumption, small-batch testing, and dry-run mode.

### 19.6 Deduplication rules and safety conditions

Deduplication protects prevalence counts from inflation. It carries a matching risk in the other direction: collapsing two genuinely different users into one erases real evidence and is invisible once done. These rules are written so that the reversible error is preferred over the irreversible one.

**What is a duplicate:**

1. **Re-ingestion of the same source item is a duplicate.** The same platform item collected twice is one document, not two, however it arrives. When the natural key matches, it resolves to the same `doc_id` and adds no row (Section 26.1). When the same item arrives under a different natural key — a different URL form, an `m.` host, a share link — it becomes a `DuplicateLink` of kind `same_source_item` and is `auto_confirmed`. This is the one case where automatic collapsing is always safe, because platform identity, not textual similarity, establishes it.
2. **Identical canonical content from the same author** is `exact_text` and `auto_confirmed`.
3. **High textual similarity** below identity is `near`, subject to the safety conditions below.
4. **Cross-posts** — the same author posting substantially the same text to more than one venue — are `cross_post`.
5. **Quoted repeats** — one document reproducing another's text, typically a reply quoting a parent — are `quoted_repeat` and always enter review.

**Safety conditions for an automatic near-duplicate or exact-text decision.** All must hold; otherwise `review_state = pending_review` with the relevant reason code:

| Condition | Rule | Reason code when it fails |
|---|---|---|
| Minimum length | Both documents have `token_count >= dedupe_min_tokens`, configurable in `config/analysis.yaml`, default **25 tokens** | `short_text_below_dedupe_minimum` |
| Author distinctness | Not (both `author_hash` values non-null and different) | `different_authors_identical_text` |
| Similarity confidence | Similarity is above the confident band, not inside the review band (Section 26.5) | `near_duplicate_in_review_band` |
| Not a quoted repeat | The overlap is not one document quoting another | `quoted_repeat_ambiguous` |

**Identical short text from different users must never be collapsed automatically.** Two people independently writing "Can't find my photos" or "search is useless now" are two users with the same complaint, which is the strongest possible prevalence signal — and automatic collapsing would delete precisely that signal while reporting a healthy-looking duplicate rate. When author hashes are present and differ, the pair goes to review regardless of similarity.

**The minimum token length is a configuration value with a documented default, not a magic number.** Short store reviews collide at low simhash distance without being duplicates, because there is not enough text for the hash to discriminate. Below `dedupe_min_tokens` the near-duplicate signal is not trustworthy and the decision belongs to a human.

**Review is a state, not a delay.** A `pending_review` link is excluded from the duplicate count *and* from the canonical-collapse logic until resolved. It appears on its own funnel line so an unreviewed backlog is visible rather than silently biasing the numbers in either direction.

---

## 20. Taxonomy Discovery

The final problem taxonomy must not be hard-coded before examining the pilot evidence.

Candidate hypotheses may include:

- Difficulty translating associative memories into searchable language.
- Approximate time or place that cannot be converted into useful filters.
- Person or face cues that fail to surface the intended item.
- Text fragments that are incomplete or not recognized.
- Utility content buried among personal photos.
- Broad or irrelevant results that force manual scrolling.
- Conversational or AI responses that replace direct asset retrieval.
- Repeated reformulation without feedback about why a query failed.

These are hypotheses, not confirmed opportunity areas.

### 20.1 Taxonomy process

1. Extract granular problem summaries without final cluster labels. `RetrievalCase` has no cluster field at all (Section 15.4), so this is structural rather than a matter of discipline.
2. Review the first 50–100 qualifying cases.
3. Group cases by target, memory cue, behavior, failure, and impact.
4. Create provisional clusters with definitions and boundaries.
5. Test inter-cluster overlap and merge or split as needed.
6. Require evidence from at least five independent documents across at least two source types before presenting a cluster as established.
7. Assign a taxonomy version.
8. Re-run assignment against the full validated corpus. This writes `ClusterAssignment` rows only (Section 15.9) and re-runs **no extraction**, because `extraction_fingerprint` and the extraction cache key exclude `taxonomy_version` (Section 19.5). Revising the taxonomy therefore costs an assignment pass, not a full re-extraction.
9. Preserve prior versions for reproducibility. Assignments are keyed by `(case_id, taxonomy_version, assignment_fingerprint)`, so a revision adds rows rather than rewriting history.

`other` and `uncertain` categories must remain available so the model is never forced into a known cluster.

Cluster labels exist in exactly one place: `ClusterAssignment`. No cluster label may appear on a `RetrievalCase`, in `config/taxonomy.yaml` before the pilot review, or hard-coded in analysis or presentation code.

---

## 21. Analysis Requirements

The analysis layer must produce:

### 21.1 Corpus funnel

**The funnel is computed per stage from `StageEvent` records (Section 15.8), never from a single lifecycle column.** A document that was imported, normalized, linked as a duplicate, passed the prefilter, was classified as core, and was extracted appears correctly at *every* one of those steps. A single-state column forced each document into one bucket and made the funnel silently wrong: a duplicate document that was also successfully extracted had to be reported as one or the other.

For each stage, report `succeeded`, `failed`, `skipped`, `dropped`, and `unavailable` counts with their reason codes:

| Funnel line | Source |
|---|---|
| Documents imported | `StageEvent(stage=import, status=succeeded)` |
| Import failures, by reason | `StageEvent(stage=import, status=failed)` |
| Documents normalized | `StageEvent(stage=normalize)` |
| Duplicate links by kind and review state | `DuplicateLink`, grouped — **not** a lifecycle state |
| Duplicate links pending review | `DuplicateLink(review_state=pending_review)` |
| Prefilter passed / dropped, with drop reasons | `StageEvent(stage=prefilter)` |
| Relevance decided | `RelevanceDecision(technical_state=ok)` |
| Relevance unavailable, by technical state | `RelevanceDecision(technical_state != ok)` |
| Core incomplete-recall documents | `scope_class = core_incomplete_recall` |
| Adjacent known-item documents | `scope_class = adjacent_known_item_retrieval` |
| Out-of-scope documents, by exclusion reason | `scope_class = out_of_scope` |
| Extraction attempted / valid / failed | `StageEvent(stage=extract)`, `StageEvent(stage=validate)` |
| Cases pending human review | `review_queue` |
| Cases resolved by human override | `human_overrides` |
| Direct-user versus contextual evidence | `evidence_tier`, cross-cut against every line above |
| Final included cases | the prevalence view (Section 21) |

Two properties this gives that the previous design could not:

- **Duplicate status is orthogonal to progress.** A duplicate document still flows through classification and extraction, and its cases are excluded at the analysis layer, not dropped at ingest. The funnel shows both facts at once.
- **Failures are countable per stage rather than terminal for a document.** A document whose first extraction attempt failed and whose second succeeded shows one failure and one success, which is the truth and is what the quality report needs.

### 21.2 Memory map

Cross-tab remembered cues against explicitly forgotten or uncertain information.

Observation statuses must remain visible rather than being excluded silently. `not_stated` and `explicitly_none` occupy separate, labelled rows and columns and are never merged into a single "none" bucket (Section 16.9). The analysis layer reads these statuses from the schema; it must not define its own.

### 21.3 Retrieval journey

Analyze:

```text
retrieval need
→ remembered cue
→ initial query or browse strategy
→ system response
→ reformulation or workaround
→ outcome
→ impact
```

### 21.4 Problem comparison

For every opportunity cluster, show:

- Unique cases.
- Unique authors where available.
- Unique parent threads.
- Source distribution.
- Asset-type distribution.
- Remembered-cue distribution.
- Failure-mode distribution.
- Outcome distribution.
- Average evidence-based severity.
- Abandonment or unresolved rate.
- Recent versus historical occurrence.
- Representative verbatim evidence.
- Uncertainty and sample limitations.

### 21.5 Ranking principles

Do not rely only on `count × average severity`.

Default views should expose the components separately. If a composite opportunity score is used:

- Publish the formula and weights.
- Use unique cases rather than raw row count.
- Control for duplicate threads and source concentration.
- Make weights configurable.
- Include sensitivity analysis showing whether the ranking changes under reasonable alternative weights.
- Never present the score as objective truth.

### 21.6 Claims discipline

Use language such as:

- “Within the analyzed corpus…”
- “Observed across three source types…”
- “This pattern appeared in 18 of 126 qualifying cases…”

Do not say:

- “18% of Google Photos users…”
- “Most users…” unless the statement is clearly limited to the analyzed corpus.
- “This causes…” when the evidence demonstrates only association.

---

## 22. Evidence Retrieval and Ask Experience

The evaluator-facing question experience must be retrieval-grounded.

### 22.1 Retrieval

- Apply structured filters before free-text ranking where relevant.
- Use TF-IDF, BM25, or an equivalent auditable baseline before introducing embeddings.
- Index raw text, problem summaries, evidence spans, and controlled labels.
- Remove stopwords and handle simple variants.
- Require a minimum relevance threshold.
- Return no evidence for unrelated questions.
- Preserve diversity across sources where possible.

### 22.2 Synthesis

- The model receives only retrieved records and evidence spans.
- The answer must cite record IDs inline.
- Citation IDs must be parsed and validated.
- The interface must display only records actually cited.
- Unsupported IDs must cause answer rejection or repair.
- If evidence is insufficient or mixed, the response must say so.
- The system must not answer questions outside the dataset.

### 22.3 Failure-safe behavior

- The core app must work without an AI key.
- If no key exists, display deterministic retrieved evidence instead of crashing.
- If the AI call fails, retain the question and show retrieved evidence.
- Cache identical grounded questions using dataset and model versions in the key.
- Apply reasonable per-session usage limits to a public deployment.

---

## 23. Evaluator-Facing Application

The final Streamlit application should provide:

### 23.1 Overview

- Strategic question.
- Corpus date range.
- Source mix.
- Processing funnel.
- Direct-user versus contextual evidence.
- Key limitations.

### 23.2 Opportunity comparison

- Ranked problem clusters.
- Transparent component metrics.
- Source-balanced toggle.
- Core versus adjacent scope toggle.
- Filters by asset type, remembered cue, failure mode, source, and date.

### 23.3 Memory map

- Remembered cues × forgotten information.
- Cue combinations.
- Unknown-value visibility.

### 23.4 Retrieval journeys

- Query or browse strategy.
- System response.
- Reformulation or workaround.
- Outcome and impact.

### 23.5 Evidence browser

- Raw source excerpt.
- Highlighted evidence spans.
- Direct source link.
- Scope decision.
- Extracted dimensions.
- Model and prompt version.
- Human-review status.
- Downloadable validated dataset.

### 23.6 Ask the evidence

- Free-text evaluator questions.
- Evidence-first results.
- Grounded synthesis when configured.
- Validated record citations.
- Honest insufficient-evidence responses.

### 23.5.1 Evidence browser and the public profile

The Phase 10 evidence browser renders the excerpt from the public export profile (Section 12.1), with spans highlighted from stored excerpt-relative offsets. It must not re-search for the quote at render time, because that would be a second, unvalidated matching implementation. Where the excerpt is a subset of the document, the surface says so and links to the original.

The local page at `main.py browse` is not that surface. It reads saved development JSONL, shows a redacted audit excerpt, and highlights stored document offsets. It does not write `data/exports/`, does not load holdout text, and does not satisfy this section.

### 23.7 Quality report

- Gold-set size and composition, split into development and frozen holdout sets.
- Which split each reported number comes from. Prompt-iteration numbers and final numbers are never shown in the same column without labels.
- Prefilter recall, against the gate in Section 24, Phase 6.
- End-to-end relevance precision, recall, and F1 on the holdout split.
- Scalar-field accuracy and multi-label precision, recall, and F1, reported separately (Section 24, Phase 6).
- Unsupported inference rate.
- Evidence-span validation rate.
- Observation-status distribution per field, so `not_stated` coverage is visible.
- Inter-reviewer agreement on the double-coded subset, reported **before** adjudication.
- Technical-failure counts by `technical_state`, excluded from the metrics above with the excluded count stated.
- Failure and human-review rates.
- Duplicate rate, broken down by kind and review state, including links still pending review.
- Known limitations.

The first six deterministic views must load without an external API key. Only optional synthesis may require a key.

---

## 24. Phased Build Plan and Acceptance Criteria

Cursor must implement one phase at a time, except for the three parallel tracks authorized in Section 1.1 and ADR-32: YouTube collection into `CollectedDocument`, extraction review, and a basic evidence browser.

### 24.0 MVP versus stretch scope

Part 1 has a defensible core and a set of genuinely optional extensions. Separating them now prevents the failure mode where an optional feature consumes the time the core needed.

**MVP — required for submission. Part 1 is not complete without all of these:**

| MVP capability | Phase |
|---|---|
| Manual CSV / JSONL import | 2 |
| Contracts and schemas (Section 15) | 1 |
| Evidence validator and the evidence-required field map | 1, 5 |
| Normalization, length-preserving redaction, canonical URLs, hashing | 3 |
| Deduplication with review states | 3 |
| Relevance classification with evidence for every class | 4 |
| Structured extraction with per-field evidence | 5 |
| Gold-set evaluation with development and holdout splits | 6 |
| Taxonomy discovery and assignment after pilot review | 8 |
| Deterministic analysis: funnel, memory map, journeys, opportunity components | 8 |
| Evidence browser | 10 |
| Quality report | 10 |
| Public-export profile | 10 |
| Streamlit deployment | 11 |

**Stretch — build only when the MVP is complete and verified. Each may be dropped without weakening a single research claim:**

| Stretch capability | Why it is optional |
|---|---|
| Second provider adapter | ADR on provider choice already commits to one provider; the second adapter proves neutrality and hedges rate limits, neither of which is a research requirement |
| Ask-the-evidence synthesis | Section 22's evidence panel is deterministic and complete on its own; synthesis is a convenience over it |
| Automated support-forum collector | Section 11.4 makes this manual by default; automation is a throughput improvement |
| Automated store-review collectors | Section 11.4 marks these experimental with no documented mechanism |
| Composite opportunity score with sensitivity analysis | Section 21.5 requires components to be shown separately and makes any composite opt-in |
| Static `explorer.html` generation | A backup artifact, not a deliverable |
| Embeddings or semantic retrieval | Section 22.1 explicitly requires an auditable lexical baseline first |

A stretch item may never be started while an MVP item is unfinished, and a stretch item may never become a dependency of an MVP item. If the schedule compresses, stretch items are cut — the MVP scope is not reduced.

ADR-32 amends that sequencing rule for the October 2026 demonstration only. YouTube collection, extraction review, and a basic local evidence browser may proceed while gold evaluation, taxonomy, the quality report, public export, and deployment are unfinished. Those unfinished items stay unfinished. The deferred items in Section 1.1 are not started. The basic browser does not complete Phases 10 or 11. The commands that exist for those tracks, and the limits on what they have done, are in Section 1.1.

### Phase 0 — project scaffold

Build:

- Repository structure.
- `pyproject.toml` with pinned or bounded dependencies.
- `.gitignore` and `.env.example`.
- Config loading.
- Logging.
- `STATUS.md`, `DECISIONS.md`, and `CHANGELOG.md`.
- Minimal test framework.

Acceptance criteria:

- Python 3.12 environment works.
- `pytest` executes successfully.
- Secrets and local data are excluded from Git.
- No Streamlit, collectors, or LLM calls are implemented yet.

### Phase 1 — schemas and evidence validation

Build:

- `CollectedDocument`.
- `DocumentDerived`.
- `DuplicateLink`.
- `EvidenceSpan`.
- `ObservedValue`.
- `RelevanceDecision`, with `is_relevant` derived from `scope_class`.
- `RetrievalCase`, with paired observation-status fields and no cluster or taxonomy fields.
- `StageEvent`.
- `ClusterAssignment`.
- Gold contracts (`GoldDocumentLabel`, `GoldCase`) and `PublicExportRecord`.
- Every controlled vocabulary in Section 16, including `ReasonCode`, `ImpactSignal`, `SubjectType`, `DimensionObservationStatus`, `DecisionTechnicalState`, and `DuplicateKind`.
- The evidence-required field map and the closed exception list (Section 15.10), as data rather than as scattered checks.
- Schema versioning.
- Evidence substring and offset validation.
- Derivation of `all_evidence_spans` as a union, and rejection of a span attached to no field.
- Tests for valid records, invalid records, every observation status, and fabricated evidence.

Acceptance criteria:

- Every schema has positive and negative tests.
- Fabricated evidence fails validation.
- A `CollectedDocument` validates with **no** `DocumentDerived`, `DuplicateLink`, or later-stage value present anywhere — asserted by a test, because this is what keeps manual import independent of Phase 3.
- `is_relevant` disagreeing with `scope_class` is rejected.
- An `out_of_scope` decision without evidence is rejected.
- Every field on `RelevanceDecision` and `RetrievalCase` appears in exactly one of the two lists in Section 15.10 — asserted by a test over the model definitions, so a new field cannot escape enforcement.
- A `stated` status without a value, a `not_stated` status with a value, and a `not_stated` status carrying evidence are each rejected.
- `all_evidence_spans` equals the union of field-level spans; a model-supplied value is ignored.
- Missing facts remain null or empty with an observation status; nothing is defaulted into a value.
- Schema-valid synthetic fixtures are clearly marked and excluded from analysis.

### Phase 2 — manual import and pilot corpus

Build:

- CSV and JSONL manual import, the guaranteed baseline collection path (Section 11.4).
- Source metadata validation.
- Author hashing.
- `doc_id` derivation from collection-time values only (Section 26.1).
- Immutable raw storage.
- `StageEvent` emission for import success and failure.
- Import warnings and failure logs.

Research task:

- Collect 30–50 genuine public user documents.
- Preserve direct permalinks and raw text.
- Label a small seed set manually.

Acceptance criteria:

- Import is idempotent; re-importing the same source item adds no row and resolves to the same `doc_id`.
- Import succeeds with **no** normalization, hashing, deduplication, or classification code present. A `CollectedDocument` requires nothing that Phase 3 produces.
- Invalid rows are reported with row numbers and reasons.
- No plaintext usernames appear in processed exports.
- At least 30 collected pilot documents are available.

### Phase 3 — normalization and deduplication

Build:

- Text normalization, producing `DocumentDerived`.
- Length-preserving privacy redaction.
- Canonical URLs.
- Stable content hashing and simhash.
- Token counting, for the minimum-length guard.
- Exact duplicate detection, including re-ingestion of the same source item under a different natural key.
- Near-duplicate detection with the Section 19.6 safety conditions.
- **The review queue.** Duplicate review items are created in this phase, so they need somewhere to live in this phase. The queue is not a Phase 4 component that Phase 3 has to write into before it exists.
- Parent-thread tracking.
- `StageEvent` emission for normalize and dedupe.

Acceptance criteria:

- Raw text remains unchanged.
- Duplicates are linked, not deleted, and duplicate status is a `DuplicateLink`, not a lifecycle state.
- Re-running produces identical IDs and identical duplicate assignments.
- The canonical document of a duplicate group is selected by the stable rule in Section 26.1 and does not depend on collection or insertion order.
- Identical short text from different authors is routed to review rather than collapsed.
- Documents below `dedupe_min_tokens` are never automatically marked as near duplicates.
- Quoted repeats enter review.
- Duplicate review items exist in the review queue and are inspectable.
- Analysis can exclude duplicates without losing auditability.

### Phase 4 — relevance classification

Build:

- Deterministic prefilter, with drop reasons stored for recall measurement.
- Strict AI relevance classifier.
- Scope classes, with `is_relevant` derived.
- `DecisionTechnicalState` handling for provider unavailability and parse failure.
- Confidence thresholds.
- Extension of the Phase 3 review queue with relevance review reasons.
- Cache, retry, repair, checkpoint, and dry-run behavior.

Acceptance criteria:

- **Every** decision has evidence, including `out_of_scope`.
- `is_relevant` is derived and never read from the model response.
- A provider-unavailable or parse-failed record carries a technical state, a null scope class, and no evidence, and is counted separately from `out_of_scope`.
- Low-confidence items are reviewable.
- Obvious storage, backup, billing, and deletion complaints are excluded, with counts by exclusion reason code.
- A known item the user could not formulate a query for classifies as `core_incomplete_recall` with reason code `known_item_query_unformulable` (Section 9.1).
- Core and adjacent cases remain separate.

### Phase 5 — structured extraction

Build:

- Strict extraction prompt.
- Provider-neutral model interface.
- Pydantic validation.
- Evidence-span validation.
- Repair ladder.
- Failure log.
- Human override support.

Acceptance criteria:

- No invalid record enters processed data.
- Exact queries are never fabricated.
- Evidence quotes validate against raw text.
- Every evidence-required field has field-level evidence, or an observation status that permits its absence (Section 15.10).
- `all_evidence_spans` is derived and matches the union of field-level spans.
- Absent facts carry an observation status and a null or empty value; no field is defaulted into a value.
- No case carries a cluster label or a taxonomy version.
- Model, prompt, and schema versions are stored on every record. `taxonomy_version` is deliberately absent from the case and from its fingerprint.

### Phase 6 — gold-set evaluation

Build:

- Two separate gold label formats: `GoldDocumentLabel` for document-level relevance and `GoldCase` for case-level extraction (Section 15.11).
- Deterministic **development** and **frozen holdout** splits.
- Case-matching logic for documents with multiple gold cases.
- Evaluation scripts for the metric families below.
- Confusion matrix and per-field metrics.
- Inter-reviewer agreement calculation over pre-adjudication labels.
- Error-analysis export.

Research task:

- The final document-level gold set is the 35 approved labels (Section 1.4, ADR-37). Do not add documents to reach the former 75–100 volume.
- For each relevant document, label **zero, one, or several** gold cases. Zero is a valid and expected label: a document can be relevant at the document level and still yield no extractable case, and a gold set that cannot express this cannot measure over-extraction.
- Include both relevant and excluded examples.
- Include multiple sources and difficult boundary cases.
- Double-code at least 20% with another reviewer, retaining every independent label.

**Split discipline.** The gold set is split deterministically by a hash of `doc_id`, roughly 40% development and 60% holdout, with stratification across source platform and scope class.

- The **development split** is the only data used for prompt iteration, threshold tuning, and error analysis. It may be read as often as needed.
- The **holdout split** is frozen. It is read once per reported configuration, and every number in the final quality report and the submission comes from it. Iterating against the holdout turns a measurement into a fitting exercise, which is the same error as relabelling gold documents to match the model.
- The split assignment is recorded in the gold files and in the run manifest, so a reader can confirm which split produced which number.

**Metric definitions.** Field types are measured differently, because a single "accuracy" number over mixed field types is not interpretable.

| Metric family | Applies to | Definition |
|---|---|---|
| Scalar accuracy | `scope_class`, `known_item_status`, `target_asset_type`, `outcome`, `severity`, `reformulation_count`, and every `*_observation` field | Share of cases where the predicted `(observation, value)` pair exactly equals the gold pair. Both parts must match: a correct value with the wrong observation status is wrong. |
| Multi-label precision / recall / F1 | `target_subjects`, `remembered_cues`, `forgotten_information`, `query_strategies`, `system_responses`, `workarounds`, `impact_signals` | Set comparison per case. Report **micro** (pooled over all values) and **macro** (mean over vocabulary members) separately, since macro exposes rare-label failure that micro hides. |
| Prefilter recall | documents | `passed ∧ prefilter_should_pass` ÷ `prefilter_should_pass`. Measured against the gold label, not against the classifier, because a prefilter drop is invisible to every later stage. |
| End-to-end relevance precision | documents | Of documents the pipeline marked relevant, the share whose gold label is relevant. End-to-end means prefilter and classifier together — a document dropped by the prefilter counts as predicted not-relevant. |
| End-to-end relevance recall | documents | Of documents whose gold label is relevant, the share the pipeline marked relevant. |
| Unsupported inference rate | fields | Of extracted field values with a non-empty value, the share whose supporting evidence is missing, fails validation, or on adjudication does not support the value. This is the direct measurement of the failure mode Section 17 exists to prevent, and it is reported per field as well as overall. |
| Evidence-span validation rate | spans | Share of spans reaching `validation_state = valid`. |
| Inter-reviewer agreement | double-coded documents | Raw agreement and Cohen's kappa on `scope_class`, computed on pre-adjudication labels and reported **before** adjudication. Adjudication removes the disagreement from the data; reporting only post-adjudication numbers hides how ambiguous the definitions actually were. |

Records with `technical_state != ok` are excluded from every metric above, and the excluded count is reported beside the metrics.

**Quality gates:**

- 100% of processed records pass schema validation.
- 100% of evidence spans pass exact-source validation.
- **Prefilter recall ≥ 0.90.**
- **End-to-end relevance precision ≥ 0.85.**
- **End-to-end relevance recall ≥ 0.80.**
- Scalar accuracy and multi-label precision, recall, and F1 reported per field.
- Unsupported inference rate reported per field and overall.
- Inter-reviewer agreement reported before adjudication.
- Every failure category has documented corrective action or accepted limitation.

A recall gate sits beside the precision gate deliberately. Precision alone is trivially satisfied by a classifier that admits almost nothing, which would produce an excellent-looking quality report over a corpus that had silently discarded most of the evidence.

If a gate is missed: iterate on the **development** split, bump the prompt or ruleset version, and re-measure. Do not lower a threshold, do not relabel gold documents to match the model, and do not iterate against the holdout.

### Phase 7 — source collectors and scaled run

Build one collector at a time, in the order set by Section 11.4's feasibility tiers. Each collector must produce `CollectedDocument` records and have mocked tests over recorded fixtures.

| Order | Source | Tier | Precondition |
|---|---|---|---|
| — | Manual CSV / JSONL | guaranteed baseline | already built in Phase 2; remains available throughout |
| 1 | YouTube Data API v3 | supported automated | primary documentation linked in `DECISIONS.md` |
| 2 | Reddit Data API | optional, credential-dependent | credentials present; skipped cleanly when absent |
| 3 | Google support forums | manual by default | **no collector.** Thread URLs are addressable and not robots-disallowed, but the terms bar scraping other users' content, so automated collection needs a permission basis rather than a working URL |
| — | Play Store / App Store | experimental | **closed, never built.** Both official APIs authenticate the app's publisher, so no quota increase or paid tier reaches reviews of an app this project does not publish (`DECISIONS.md` ADR-22) |

Acceptance criteria:

- Collector behavior is independently testable.
- Rate limits and failures are handled safely; a blocked source stops, records the reason, and degrades to manual import.
- Manual import remains available and tested as the guaranteed path, not merely as a fallback.
- No collector is described as verified without primary documentation linked in `DECISIONS.md`, and a documented-but-unexercised mechanism is reported as such.
- The full funnel is recorded by source.
- The run reports actual document counts by source. The internal ambition of 300 documents across four source types is not a completion rule (Section 1.1, ADR-32). Manual import counts toward whatever corpus is actually processed.

`src/collect/youtube.py` implements the YouTube row. On 2026-10-04 it was exercised: 40 comment-read requests, 266 new documents. The deduped corpus is 318 documents across five platforms, with YouTube above the 40% concentration line. Reddit's live client exists and skips when credentials are absent. The owner directed the project to skip Reddit on 2026-10-04 because self-service API keys are no longer issued; no access request will be filed, no Reddit request has been made, and Reddit stays `documented, unexercised`. The recorded funnel is the collection import. Relevance and extraction were not run on this corpus.

### Phase 8 — taxonomy and analysis

Build:

- Provisional cluster review workflow.
- Taxonomy versioning.
- Corpus funnel.
- Memory map.
- Journey analysis.
- Problem comparison.
- Source-balanced analysis.
- Opportunity components and optional sensitivity-tested score.

Acceptance criteria:

- No cluster is presented as established without sufficient independent evidence.
- Core and adjacent cases can be analyzed separately.
- Duplicate-thread inflation is controlled.
- All displayed metrics can be reproduced from committed processed data.

### Phase 9 — evidence retrieval

Build:

- Deterministic filter and lexical-ranking baseline.
- Minimum relevance threshold.
- Source-diverse results.
- Optional grounded synthesis.
- Citation validation.
- Unrelated-query refusal.

Acceptance criteria:

- An unrelated query returns no evidence rather than arbitrary records.
- Only cited records appear under “Evidence used.”
- AI failure falls back to deterministic evidence.
- Retrieval and citation tests pass.

### Phase 10 — Streamlit application

Build the surfaces in Section 23, plus the public-export profile in Section 12.1 that they read from. `main.py browse` is the local demonstration page from Section 1.1. It does not meet the criteria below.

Acceptance criteria:

- The public export satisfies every rule in Section 12.1, verified by a test over the generated artifact.
- The evidence browser highlights spans from stored excerpt-relative offsets and never re-searches for the quote.
- App launches from a clean environment.
- Deterministic views work without secrets.
- Missing AI keys do not crash the app.
- Empty filters and empty datasets are handled.
- Source links and downloads work.
- App tests cover critical paths.

### Phase 11 — deployment and submission QA

Complete:

- Public Streamlit deployment.
- Public or evaluator-accessible GitHub repository.
- Committed public-profile export (Section 12.1) plus its run manifest. Unredacted raw data stays local.
- README setup and methodology instructions, stating plainly that analysis reproduction is supported and source re-collection is not.
- Working source links.
- One-slide explanation for the final deck.
- Screenshots and backup evidence export.

Acceptance criteria:

- Public link opens without login.
- No secrets are committed.
- All deterministic features work without evaluator setup.
- Dataset, app, README, and methodology numbers agree.
- Links are verified.
- Claims are limited to the analyzed corpus.

---

## 25. Required Tests

At minimum, test:

### Schemas

- Valid `CollectedDocument`.
- A `CollectedDocument` validates with no derived, duplicate, or later-stage field present anywhere.
- Invalid URL, datetime, enum, and empty text.
- Valid and invalid retrieval cases.
- Null and observation-status behavior for every status in Section 16.9.
- A `stated` status with no value is rejected; a `not_stated` status with a value is rejected; a `not_stated` status carrying evidence is rejected.
- `RetrievalCase` has no cluster or taxonomy field.
- Schema-version presence.

### Evidence

- Exact quote and offsets succeed.
- Fabricated quote fails.
- Wrong offsets fail.
- Duplicate quote occurrence is handled explicitly: unique match repairs, nearest match with a positional hint repairs and flags, ambiguous tie enters review rather than guessing.
- Missing offsets with a unique occurrence are recovered; missing offsets with several occurrences and no hint are not.
- Normalized-whitespace repair preserves original displayed text.
- A span overlapping a redaction is rejected.
- Every field in the Section 15.10 required map is enforced; removing a field's evidence fails validation.
- Every field on `RelevanceDecision` and `RetrievalCase` appears in exactly one of the required or exempt lists.
- `all_evidence_spans` equals the union of field-level spans; a model-supplied value is discarded; a span attached to no field fails validation.

### Import

- Valid CSV and JSONL.
- Missing fields.
- Malformed rows.
- Duplicate imports.
- Stable IDs.

### Privacy

- Author hashing is deterministic with the same salt.
- Plaintext author does not appear in processed exports.
- Common email and phone patterns are redacted.

### Deduplication

- Exact duplicates.
- Re-ingestion of the same source item under a different URL form links as `same_source_item`.
- Near duplicates.
- Cross-posts.
- Quoted text inside replies routes to review.
- Identical short text from two different author hashes is **not** collapsed automatically.
- Documents below `dedupe_min_tokens` are never automatically marked near-duplicate.
- Review-band pairs open review items and are excluded from the duplicate count until resolved.
- Duplicate linking without deletion, and without setting any lifecycle state.
- Canonical selection is the lowest `doc_id` and is unchanged by shuffling ingestion order.

### Stage events and funnel

- Stage events are append-only; no event is rewritten.
- One document appears at every stage it reached, including simultaneously as a duplicate and as a successfully extracted document.
- Per-stage funnel counts reconcile with the stage-event table and with the manifest.
- A document with a failed then a successful extraction attempt reports one of each.

### Relevance

- Core incomplete-recall case.
- A known item with no formulable query classifies as core with reason code `known_item_query_unformulable`.
- Adjacent exact-recall search defect.
- Backup, billing, storage, deletion, and editing exclusions.
- Editorial capability example exclusion.
- An `out_of_scope` decision without evidence is rejected.
- `is_relevant` is derived; a conflicting model-supplied value is discarded and a stored conflict is rejected.
- Provider unavailable and parse-failed attempts produce a technical state, a null scope class, and no evidence, and are excluded from precision and recall.
- Uncertain case routed to review.

### Extraction

- Exact query preserved.
- Missing query remains null with `not_stated`.
- Forgotten information is not inferred from silence; `not_stated` and `explicitly_none` are distinguishable in storage.
- Unsupported severity is rejected.
- Invalid model response enters repair or failure handling.
- Cache key changes with model, prompt, schema, or content — and does **not** change with taxonomy version.
- The taxonomy-assignment cache key **does** change with taxonomy version.
- A multi-case document produces stable, position-ordered case IDs, with tie-breaking exercised.

### Gold set and evaluation

- Document-level and case-level labels load independently.
- A document with zero gold cases participates in relevance metrics and contributes no case metrics.
- A document with several gold cases matches extracted cases by evidence overlap, order-independently.
- Split assignment is deterministic and stratified; the same `doc_id` always lands in the same split.
- Scalar accuracy requires both value and observation status to match.
- Multi-label micro and macro precision, recall, and F1 computed correctly on a tiny synthetic set.
- Prefilter recall computed from gold `prefilter_should_pass`, not from classifier output.
- Unsupported inference rate computed per field.
- Inter-reviewer agreement computed from pre-adjudication labels.
- An empty gold set produces an honest "pending" result rather than zeros or a crash.

### Analysis

- Duplicates excluded from prevalence.
- Pending-review duplicate links excluded from the duplicate count and reported separately.
- Contextual sources excluded from direct-user counts.
- Unique thread and author counts.
- Every observation status visible; `not_stated` and `explicitly_none` never merged.
- No analysis module defines a status value absent from the schema.
- Records with a non-`ok` technical state excluded from metrics, with the excluded count reported.
- Source-balanced calculations.
- Deterministic output.

### Export profile

- A generated public export contains no username pattern, no key pattern, no email, and no phone number.
- No excerpt exceeds the configured window unless `excerpt_is_full_text` is true and the source permits redistribution.
- Excerpt-relative offsets highlight correctly and map back to document offsets.
- Local raw paths are absent from the export and gitignored.

### Reproducibility

- Rebuild reproduces identical canonical content hashes for every exported artifact.
- Manifests differing only in run ID, timestamps, durations, and token counts still pass the equivalence check.
- A deliberately introduced non-determinism in a data field fails the equivalence check.
- `doc_id` is derivable with no derived field present.

### Retrieval and synthesis

- Relevant question ranks expected evidence.
- Unrelated question returns no evidence.
- Minimum score enforced.
- Invalid model citation rejected.
- Displayed evidence equals actually cited evidence.
- Missing API key falls back without crashing.

### Application

- Clean launch.
- No-secret launch.
- Empty dataset and empty filter states.
- Download content matches displayed dataset version.
- Critical navigation and filtering.

---

## 26. Reproducibility and Configuration

All changeable choices should live in configuration rather than source code:

- Enabled sources.
- Collection queries.
- Date ranges.
- Language filters.
- Model provider and model names.
- Confidence thresholds.
- Deduplication threshold.
- Taxonomy version.
- Opportunity-score weights if used.
- Retrieval top-k and minimum score.

Required environment variables should be documented in `.env.example`. Real secrets must remain in `.env` or deployment secrets and must never be committed.

Every pipeline run should create a run manifest containing:

- Run ID.
- Start and completion time.
- Git commit where available.
- Configuration hash.
- Source counts.
- Model and prompt versions.
- Schema and taxonomy versions.
- Gold split assignment rule and seed.
- Per-stage funnel counts from `StageEvent`.
- Failure counts by reason code and technical state.
- Output file canonical content hashes.
- The volatile-field exclusion list used for content hashing.

### 26.1 Identifier construction

Every identifier is derived from content or from stable source keys, never from insertion order, autoincrement, or wall-clock time.

**`doc_id` must be derivable at import from collection-time values only.** It may not depend on any value a later stage produces.

```text
doc_id = {source_platform}-{sha1(source_platform | natural_key)[:12]}

natural_key, in order of preference:
  1. source_item_id                 when the platform exposes one
  2. source_url_key                 import-time normalized URL (Section 15.1)
  3. sha1(source_name | author_hash_or_"anon"
          | published_at_iso_or_""
          | raw_text_sha256)        manual rows with neither
```

The third fallback uses `raw_text_sha256` — a pure function of the collected raw text — and specifically **not** `content_hash`, which is a canonicalized value produced by Phase 3 normalization. A `doc_id` that depended on `content_hash` could not be assigned at import, which made manual import depend on normalization and made the identifier change if the normalizer changed. Both are corrected here.

| Identifier | Construction |
|---|---|
| `doc_id` | as above |
| `raw_text_sha256` | `sha256(raw_text)`, available at import |
| `content_hash` | `sha256` of canonicalized text: NFKC, lowercase, collapsed whitespace, stripped URLs and punctuation. Phase 3. |
| `simhash` | 64-bit simhash over 3-word shingles of `normalized_text`. Phase 3. |
| `author_hash` | `HMAC-SHA256(AUTHOR_SALT, source_platform \| username)[:16]`; the salt lives only in `.env`, and `author_salt_id` records which salt was used |
| `case_id` | Section 26.3 |
| `evidence_id` | `sha1(owner_id \| field_name \| start_char \| end_char \| sha1(quote))[:12]`, falling back to `sha1(owner_id \| field_name \| sha1(quote))[:12]` when offsets are unresolved |
| `link_id` | `sha1(doc_id \| canonical_doc_id \| method)[:12]` |
| `event_id` | `sha1(run_id \| stage \| target_id \| attempt \| status)[:12]` |

**Canonical document selection in a duplicate group uses the lowest `doc_id`.** Specifically, the canonical document is the one whose `doc_id` sorts first under byte-wise ascending comparison across the whole group.

"First collected" was the previous rule and it was not stable. Collection order depends on which source ran first, how a batch was paginated, whether a run was resumed, and which documents an analyst happened to paste in first — none of which are properties of the documents. Re-running the pipeline against the same corpus could legitimately produce a different canonical document, changing which `source_url` an evaluator was shown for the same evidence. Because `doc_id` values are content- or key-derived and unique, the lowest-`doc_id` rule is total, order-independent, and reproducible. Ties are impossible by construction, and a test asserts that shuffling ingestion order leaves every `canonical_doc_id` unchanged.

### 26.2 Record fingerprints

Fingerprints let several versions of a decision or extraction coexist without overwriting history or double-counting.

| Fingerprint | Inputs |
|---|---|
| `decision_fingerprint` | `sha1(model \| prompt_version \| ruleset_version \| schema_version \| content_hash)[:10]` |
| `extraction_fingerprint` | `sha1(model \| prompt_version \| schema_version \| content_hash)[:10]` |
| `assignment_fingerprint` | `sha1(model \| prompt_version \| schema_version \| taxonomy_version \| content_hash)[:10]` |

`taxonomy_version` appears **only** in `assignment_fingerprint`, for the reasons given in Section 19.5. A case's extracted content does not change when the taxonomy is revised, so its fingerprint must not change either.

### 26.3 Case identifiers and evidence offsets

`case_id` is ordered by evidence position rather than by model output order, because a model may emit two cases from one document in either order across runs and `case_id` is what the Ask surface cites and what evaluators bookmark.

```text
case_id = {doc_id}#c{ordinal:02d}
```

The ordinal is assigned by sorting the document's cases on this key, in order:

1. `start_char` of the case's first valid evidence span, ascending.
2. `end_char` of that span, ascending.
3. `sha1(quote)` of that span, ascending — resolves a genuine tie where two cases are evidenced by spans at identical offsets, which happens when one sentence supports two distinct retrieval needs.
4. `sha1` of the case's canonical field payload, ascending — resolves the remaining pathological case.

**Cases with no resolvable offsets.** A case whose spans cannot be offset-resolved cannot be ordered, and it also cannot be valid. It still needs a stable identifier so its failure record can be referenced:

```text
case_id = {doc_id}#u{sha1(canonical_case_payload)[:8]}
```

The `#u` prefix marks it unordered. Such a case is never persisted as valid, never enters analysis, and always enters the review queue with reason code `evidence_offsets_unresolved`.

**Missing offsets.** When a model supplies a quote with no offsets, the validator locates it:

| Situation | Action | `offset_state` |
|---|---|---|
| Exactly one occurrence in `raw_text` | Adopt those offsets | `repaired_unique` |
| Several occurrences, model supplied an approximate position | Choose the occurrence nearest the supplied position, set `repair_applied` | `repaired_nearest` |
| Several occurrences, no positional hint | **Do not guess.** Span is unresolved; case enters review | `ambiguous_tied` |
| No occurrence, matches ignoring whitespace runs | Recover offsets from the original text and store the **original** substring | `repaired_whitespace` |
| No occurrence at all | Reject as fabrication | — |

The ambiguous-tied case is deliberately routed to a human rather than resolved by a heuristic. Picking the first occurrence would be arbitrary, and an arbitrary offset that validates is worse than a visible gap, because it looks verified.

### 26.4 Rebuild equality

`main.py rebuild` replays the corpus from immutable raw files plus the cached model responses and must reproduce the dataset. The equality claim is precise:

> **Rebuild equality means identical canonical content hashes for every exported artifact. It does not mean byte-identical run manifests.**

A run manifest legitimately differs between runs: it records a new run ID, new start and completion timestamps, new durations, possibly a different git commit, and possibly different token counts if some responses came from cache. Requiring byte-identical manifests would make the reproducibility test fail for reasons that have nothing to do with the data, and the predictable result is that the test gets weakened or ignored — at which point real non-determinism stops being caught.

**Content-equivalence hashing.** Each exported artifact is hashed after canonicalization: records sorted by primary key, object keys sorted, numbers normalized, and the volatile fields below removed. The exclusion list is itself recorded in the manifest, so a reader knows exactly what was and was not compared.

Excluded from content-equivalence hashes:

- `run_id` and any field derived from it.
- Execution timestamps: run start and end, stage start and end, `occurred_at`, `derived_at`, `decided_at`, `extracted_at`, `assigned_at`, cache-write times.
- Wall-clock durations and latencies.
- Token counts, request counts, and cost estimates.
- Hostname, process ID, and local absolute paths.
- Cache hit or miss status.

Deliberately **not** excluded, because these are data: `collected_at` and `published_at` (properties of the document, not of the run), every content hash, every identifier, every extracted value, every observation status, and every evidence offset.

A mismatch in a content-equivalence hash means non-determinism leaked into the data and must be investigated. A difference in a manifest's volatile fields means a second run happened, which is expected.

### 26.5 Deduplication thresholds

These live in `config/analysis.yaml` and are reported in the manifest:

| Setting | Default | Purpose |
|---|---|---|
| `dedupe_simhash_duplicate_max` | Hamming ≤ 3 | Confident near-duplicate band |
| `dedupe_simhash_review_band` | Hamming 4–6 | Routed to human review |
| `dedupe_min_tokens` | 25 | Below this, no automatic near-duplicate decision (Section 19.6) |
| `dedupe_allow_cross_author_auto` | `false` | Must stay false: identical text from different authors never collapses automatically |

---

## 27. Definition of Done

Part 1 is complete only when:

- [ ] Every MVP capability in Section 24.0 is built and verified. Stretch items are explicitly marked as included or dropped.
- [ ] Actual corpus size, source mix, and limitations are reported. The internal ambition of 300 documents across four source types (Section 11.1, ADR-32) is not an assignment completion rule and is not claimed unless the count is real.
- [ ] Per-stage funnel counts are reported from stage events, with duplicate, contextual, core, adjacent, excluded, pending-review, technically failed, reviewed, and included counts separate.
- [ ] Every processed record validates against the schema.
- [ ] Every evidence quote is verified against raw text.
- [ ] Every evidence-required field has field-level evidence or a permitting observation status.
- [ ] Direct-user and contextual sources are separated.
- [x] The final gold set is the 35 approved documents and 21 cases, with document-level and case-level labels separated and development and holdout splits defined (Section 1.4, ADR-37). The former 75–100 volume is closed.
- [ ] Prefilter recall ≥ 0.90, end-to-end relevance precision ≥ 0.85, and end-to-end relevance recall ≥ 0.80 on the holdout split.
- [ ] Scalar accuracy, multi-label precision/recall/F1, unsupported inference rate, and evidence validation are reported.
- [ ] Inter-reviewer agreement is reported before adjudication.
- [ ] The problem taxonomy was derived and refined after pilot review, and exists only in `ClusterAssignment`.
- [ ] Opportunity areas are supported by independent cases across multiple source types.
- [ ] Duplicate and source concentration are controlled in comparisons.
- [ ] The evaluator can inspect evidence excerpts and open source links.
- [ ] The deterministic app works without an API key.
- [ ] Unrelated Ask queries return no evidence or an honest refusal, where Ask is included.
- [ ] Generative answers cite only validated record IDs, where Ask is included.
- [ ] A public evaluator link works without setup.
- [ ] The public export satisfies Section 12.1, verified by a test over the artifact.
- [ ] Rebuild reproduces identical canonical content hashes (Section 26.4).
- [ ] The GitHub repository contains README, methodology, tests, configuration examples, and a reproducible analysis build process.
- [ ] No secrets or plaintext author identities are committed.
- [ ] Claims are explicitly limited to the analyzed corpus, and the difference between analysis reproduction and source re-collection is stated.
- [ ] Every source mechanism described as verified links primary documentation in `DECISIONS.md`.

---

## 28. First Milestone

Before scaling or building the interface, achieve:

> 30 genuine public documents → the full pipeline run end to end → every extracted claim backed by a validated verbatim span → per-stage funnel counts reported → all schema and evidence tests passing.

**The case count is an observation, not a target.** Earlier drafts of this milestone required 15–25 qualifying cases from 30 documents. That number must not be treated as a gate, because the only way to move it reliably is to change the prompts until the count lands in the band — which is fitting the instrument to a desired reading. The evidence rules in Section 17 are exactly the thing that would get quietly relaxed, and the result would be a corpus that hit its number and could not be trusted.

Report the case count with its full funnel and investigate it. An unexpected count is diagnostic information about a specific stage, and the four candidate stages have different symptoms and different fixes:

| If the count is lower than expected | Diagnose | Evidence to look at |
|---|---|---|
| Sampling | Did collection find retrieval discussions at all? | Collection log: results scanned versus kept, per query and per source. A low keep rate is a query problem, not a pipeline problem. |
| Prefilter | Is the high-recall stage dropping real cases? | Prefilter drop reasons, and prefilter recall against the gold `prefilter_should_pass` labels (Section 24, Phase 6). This is the most common cause and the most invisible, because a dropped document never gets a classifier opinion. |
| Classification | Are core documents being classified `out_of_scope`? | Exclusion reason-code distribution, and the `out_of_scope` evidence spans — which now exist for every exclusion, and are readable. |
| Extraction | Are relevant documents yielding zero cases? | Extraction failures, repair-ladder exhaustion, and unresolved-offset review items. |

| If the count is higher than expected | Diagnose | Evidence to look at |
|---|---|---|
| Classification | Are adjacent or out-of-scope documents leaking into core? | Inclusion reason codes, and scope-class precision on the development split. |
| Extraction | Is one document being split into several cases that are really one? | Multi-case documents, and whether each case's spans are genuinely distinct. |

Fix the stage the evidence implicates, bump that stage's version, record the reasoning in `DECISIONS.md`, and re-measure. Do not tune prompts to move the count into a band.

This milestone demonstrates that the engine can produce trustworthy research data. A polished dashboard without this foundation does not satisfy the project objective.

---

## 29. Cursor Operating Instructions

Cursor must follow these rules throughout implementation:

1. Read this file completely before acting.
2. Inspect the existing repository before proposing edits.
3. Preserve user-created files and unrelated changes.
4. Work on only the explicitly requested phase.
5. Show a short implementation plan before editing.
6. Add or update tests with each behavior change.
7. Run the relevant tests before completing a phase.
8. Do not state that something works without showing the command and result.
9. Do not insert fabricated research data to make the interface look complete.
10. Synthetic fixtures must be obviously labeled and excluded from analysis.
11. Do not hard-code credentials, model names, local paths, dates, or opportunity conclusions.
12. Do not silently relax validation to make model output pass.
13. When evidence is missing, leave the value null or empty and set the paired observation status (Section 16.9). Never invent an `unknown` placeholder value.
14. Log invalid inputs and model failures.
15. Update `STATUS.md` after each approved phase.
16. Record material deviations from this specification in `DECISIONS.md`.
17. Report created or changed files, test results, assumptions, and next steps.

---

## 30. First Prompt to Paste into Cursor

This prompt implements **Phase 0 only**. Section 29 item 4 requires working on one explicitly requested phase, and Phase 1 is the phase that every later number depends on — it carries the contract split, the evidence-required field map, the observation-status rules, and the derived-field rules. Bundling it into the first prompt alongside scaffolding is how it gets rushed. `IMPLEMENTATION-PLAN.md` carries a separate paste-ready prompt for every phase, including Phase 1.

```text
Read problem-statement.md completely, then ARCHITECTURE.md and
IMPLEMENTATION-PLAN.md. Treat problem-statement.md as the authoritative product,
research, data, and engineering specification for this repository.

Inspect the current repository, including the reference prototype, but do not edit
anything inside it. The prototype files are references only and their sample
records are not validated research evidence.

Implement only Phase 0 from problem-statement.md, following IMPLEMENTATION-PLAN.md
Phase 0:

- project scaffold and directory tree
- pyproject.toml with bounded dependencies, .gitignore, .env.example
- configuration loading and structured logging
- core identifier and hashing helpers, and the version registry
- STATUS.md, DECISIONS.md and CHANGELOG.md
- the Phase 0 tests only

Do not implement models, schemas, the evidence validator, collectors, LLM calls,
retrieval, analysis, Streamlit, or deployment. Phase 1 is a separate prompt.
Do not create realistic-looking research records.

Before editing files:
1. Show the repository state you found.
2. Propose the exact file tree and implementation plan.
3. Identify assumptions or conflicts with problem-statement.md.
4. Wait for my approval.

After approval, implement Phase 0, run pytest, and report:
- files created or changed
- test command and complete result
- unresolved assumptions
- confirmation that no Phase 1 code was written
```

---

## 31. Product and Research Principle

The engine is successful only if an evaluator can move from an opportunity claim to the exact user evidence that supports it.

When evidence is incomplete, the system should expose uncertainty rather than manufacture completeness.
