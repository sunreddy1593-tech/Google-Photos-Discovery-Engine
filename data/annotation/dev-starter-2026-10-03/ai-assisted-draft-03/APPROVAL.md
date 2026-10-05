# Annotation revision 03: decisions recorded 2026-10-04

This revision preserves drafts 01 and 02. Proposed document labels now total
3 core, 3 adjacent, 4 out of scope, with six proposed retrieval cases. These
are AI-assisted annotations with scoped human review; official gold is unchanged.

## Latest decisions

- **Item 8, successful sleeping-video search** (`reddit-bde62ddef9b5`): core,
  one-case summary approved by Sunayana. Forgotten date, the delimited
  natural-language query and successful retrieval are supported. Subject type
  stays uncertain; no motive, impact or severity is added. The case values and
  quotes are unchanged.
- **Item 1, family photo inside an album** (`google_support-2a080da4b930`): core
  scope applied as directed by Sunayana. One proposed case is retained, with
  all case fields and quotes unchanged.

## Family-album scope exception

The source describes a known-item need and an album face-search limitation,
but no incomplete recall. Under the existing Section 9.1 criterion, that
evidence would ordinarily support adjacent scope. The user's core instruction
is recorded explicitly as a reviewer-directed scope exception, not evidence
of forgotten information or inability to formulate a query. The existing
`known_item_retrieval_journey_described` reason remains; the inclusion reason
group validates for core, but local validation does not establish consistency
with the substantive core definition. No definition or prompt was changed.

Source: "I'm trying to search for one of my family in a Google photos album. It is not a shared album. It seems you can't search for a face within a specific album, which means I have to scroll through hundreds of photos to find the one I want. Any tips?"

This exception is also in `scope_exceptions.json` and must remain visible when
the label is later evaluated or used in core comparisons.

## Earlier decisions preserved

- Item 3: Memories adjacent scope approved. The new reason, one-case count and
  case fields still await confirmation.
- Item 7: later first-person poodle search accepted as real evidence; illustrative
  quantities and other breed examples are excluded from measured counts/cases.
- Item 9: cat case severity 3 approved.
- Item 10: short YouTube insufficient-evidence exclusion with zero cases approved.

`human_decisions.jsonl` retains all six decision records without rewriting the
earlier four. Decisions are scoped and do not imply blanket approval of all
other document labels or every field. Original gold, split, source packets,
saved model output and quality reports are unchanged.

The two manifest-designated documents still require independent second human
reviews. There is no adjudication, fabricated second coder or agreement score.
Quality gates and M1 remain pending/incomplete. No model/API calls, evaluation,
holdout text access, commit or push occurred.

REVIEW.md contains the ten source texts, proposed fields and exact quotes.
