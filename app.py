"""Read-only submission view of prepared discovery-engine exports.

Launch with the project virtual environment. This file does not read collection
files, credentials, or provider payloads, and it does not call a model.
"""

from __future__ import annotations

from pathlib import Path
import json

import streamlit as st

from community_insights import render_community_insights, render_live_analyse
from src.export.compare import ADJACENT, CORE, comparison
from src.export.load import (
    FILTER_ALL,
    RECORD_ALL,
    browser_cards,
    filter_cards,
    load_submission,
)
from src.export.present import highlight_excerpt
from src.export.reference import load_reference, reference_comparison

LOCAL_DEMO = Path(__file__).parent / "data/exports/submission/demo-2026-10-04-03"
DEFAULT_EXPORT = LOCAL_DEMO if (LOCAL_DEMO / "index.json").is_file() else Path(__file__).parent / "data/exports/submission"
SECTIONS = (
    "Overview",
    "Evidence browser",
    "Problem comparison",
    "Reviewed reference evidence",
    "Memory map and journeys",
    "Quality report",
    "Ask the evidence",
    "Methodology and limitations",
    "Community insights",
)
ASK_QUESTION_CAP = 8
NAV_LABELS = {
    "Overview": "Overview",
    "Evidence browser": "Explore evidence",
    "Problem comparison": "Compare problems",
    "Reviewed reference evidence": "Reviewed reference",
    "Memory map and journeys": "Memory map",
    "Quality report": "Quality report",
    "Ask the evidence": "Ask the evidence",
    "Methodology and limitations": "Methodology and quality",
    "Community insights": "Community insights",
}


def _open_section(name: str) -> None:
    st.session_state["section"] = name


st.set_page_config(page_title="Photo Discovery Lab", layout="wide", initial_sidebar_state="expanded")
st.title("Photo Discovery Lab")
st.caption("Qualitative feedback workbench. These counts describe this sample only.")


@st.cache_data(show_spinner=False)
def _load(export_dir: str) -> dict:
    return load_submission(Path(export_dir))


def _export_dir() -> str:
    selected = st.session_state.get("export_dir")
    if isinstance(selected, str) and selected.strip():
        return selected
    return str(DEFAULT_EXPORT)


def _options(cards: list[dict], field: str) -> list[str]:
    values = sorted({str(card.get(field) or "") for card in cards if card.get(field)})
    return [FILTER_ALL, *values]


def _pairs(rows: tuple[tuple[str, object], ...]) -> None:
    """Render label-value rows without importing a dataframe library."""
    for label, value in rows:
        st.markdown(f"- **{label}:** {value}")


def _metrics(summary: dict) -> None:
    rows = (
        ("Documents", summary.get("documents", 0), "Unique documents in this dataset."),
        ("Extraction attempts", summary.get("extraction_attempts", 0), "Model extraction attempts, not documents."),
        ("Stored cases", summary.get("stored_cases", 0), "Cases retained by the extraction run."),
        ("Automatically valid", summary.get("automatically_valid_cases", 0), "Evidence gate passed. Not approval."),
        ("Semantically approved", summary.get("semantically_approved_cases", 0), "Recorded human approval of a case."),
        ("Failed attempts", summary.get("failed_attempts", 0), "Not included in conclusions."),
        ("Empty responses", summary.get("empty_responses", 0), "A finished response with no case."),
        ("Unresolved reviews", summary.get("unresolved_review_items", 0), "Open review-queue items for this dataset."),
    )
    for start in (0, 4):
        columns = st.columns(4)
        for column, (label, value, note) in zip(columns, rows[start : start + 4], strict=True):
            column.metric(label, value, help=note, border=True)


def _overview(dataset: dict, index: dict) -> None:
    summary = dataset["summary"]
    st.subheader("Overview")
    with st.container(border=True):
        st.markdown("**Photo retrieval and discovery analysis**")
        st.write(
            summary.get("description")
            or "Qualitative pain points and query breakdowns from remembered-photo retrieval, grounded in saved community excerpts."
        )
        st.caption("Automatic validity is not semantic approval. Public visitors cannot start collection or a model.")
        actions = st.container(horizontal=True)
        with actions:
            st.button(
                "Explore evidence",
                type="primary",
                icon=":material/travel_explore:",
                on_click=_open_section,
                args=("Evidence browser",),
                key="go_evidence",
            )
            st.button(
                "Methodology and quality",
                icon=":material/menu_book:",
                on_click=_open_section,
                args=("Methodology and limitations",),
                key="go_method",
            )
    render_live_analyse()
    st.info(
        "Document counts, extraction attempts, and stored cases are separate. "
        "Other datasets are not added to these numbers."
    )
    _metrics(summary)
    reference, _records = _reference_bundle()
    if reference:
        st.info(f"Separate approved development reference: {reference['documents']} documents and {reference['cases']} cases. Open Reviewed reference evidence or Problem comparison. These are human reference labels, not successful model extractions.")
    left, right = st.columns(2)
    with left:
        st.markdown("**Collection and processing**")
        _pairs(
            (
                ("Analysis documents after confirmed duplicates", summary.get("analysis_documents")),
                ("Confirmed duplicate links", summary.get("confirmed_duplicate_links")),
                ("Pending duplicate links", summary.get("pending_duplicate_links")),
                ("Withheld evaluation documents", summary.get("withheld_evaluation_documents")),
                ("Frozen-split rows excluded from this dataset", summary.get("frozen_split_overlap_excluded")),
                ("Relevance attempts", summary.get("model_relevance_attempts")),
                ("Extraction attempts by state", summary.get("extraction_by_state")),
            )
        )
    with right:
        st.markdown("**Exclusions and approval**")
        _pairs(
            (
                ("Human-labeled out of scope", summary.get("human_labeled_out_of_scope")),
                ("Model relevance out of scope", summary.get("model_relevance_out_of_scope")),
                ("Human relevance labels", summary.get("human_relevance_labels")),
                ("Recorded semantic findings", summary.get("recorded_semantic_findings")),
                ("Recorded corrections", summary.get("corrections")),
            )
        )
        st.caption(
            "A human relevance label is not extraction approval. "
            "A model flag that does not request review is not semantic approval."
        )
    if summary.get("missing_inputs"):
        st.warning("Some prepared inputs were missing: " + ", ".join(summary["missing_inputs"]))
    st.markdown("**Known semantic risks**")
    for risk in index.get("semantic_risks") or []:
        st.write("- " + risk)
    corrections = dataset.get("corrections") or []
    st.markdown("**Recorded corrections**")
    if corrections:
        for row in corrections:
            st.markdown(
                f"`{row.get('case_id')}` · {row.get('field')}: "
                f"{row.get('original_value')} → {row.get('corrected_value')}"
            )
        st.caption("Displayed as saved. This app does not create or edit approvals.")
    else:
        st.info("No human extraction corrections are recorded for this dataset.")


def _card(card: dict) -> None:
    title = card.get("case_id") or card.get("doc_id")
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(
            f"{card.get('record_label')} · {card.get('source_platform')} · "
            f"{card.get('source_name')}"
        )
        if card.get("source_url"):
            st.link_button("Open source", card["source_url"])
        _pairs(
            (
                ("Human relevance label", card.get("human_relevance_label") or "none recorded"),
                ("Model scope", card.get("model_scope_class") or "none stored"),
                ("Model relevance scope", card.get("model_relevance_scope") or "not attached"),
                ("Review status", card.get("review_status") or ""),
                ("Automatically valid", card.get("automatically_valid")),
                ("Semantically approved", card.get("semantically_approved")),
                ("Enters conclusions", card.get("enters_conclusions")),
            )
        )
        if card.get("excerpt"):
            st.markdown("**Redacted excerpt**")
            if card.get("excerpt_kind") == "capped_audit_not_a_validated_window":
                st.caption("Opening of the redacted audit, capped. Not a validated evidence window.")
            st.html(highlight_excerpt(card["excerpt"], card.get("evidence_spans") or []))
            st.caption(
                f"Excerpt starts at document offset {card.get('excerpt_start_char', 0)}. "
                "Highlights use those stored offsets."
            )
        support = card.get("span_support") or []
        spans = card.get("evidence_spans") or []
        if spans:
            st.markdown("**Supporting quotes**")
            for index, span in enumerate(spans):
                note = support[index]["support_label"] if index < len(support) else ""
                st.markdown(f"`{span.get('field_name')}`")
                st.markdown("> " + span.get("quote", ""))
                if note:
                    st.caption(note)
        assigned = card.get("assigned_values") or {}
        if assigned:
            st.markdown("**Assigned values**")
            _pairs(tuple((name, payload) for name, payload in assigned.items()))
        if card.get("problem_summary"):
            st.markdown("**Model summary, not a quotation**")
            st.text(card["problem_summary"])
        if card.get("reason_summary"):
            st.markdown("**Model reason summary, not a quotation**")
            st.text(card["reason_summary"])
        if card.get("rejected_model_text"):
            with st.expander("Rejected model text, not a source quotation"):
                for quote in card["rejected_model_text"]:
                    st.text(quote)
        if card.get("diagnostic"):
            with st.expander("Allowlisted failure diagnostic"):
                _pairs(tuple(card["diagnostic"].items()))
        for finding in card.get("findings") or []:
            st.warning(f"{finding.get('field')}: {finding.get('summary')}")


def _evidence(dataset: dict) -> None:
    _reference_evidence()
    st.subheader("Evidence browser")
    st.caption(
        "Failed attempts and empty responses stay visible here and stay out of conclusions. "
        "Human relevance labels are not extraction approval."
    )
    cards = browser_cards(dataset)
    dataset_id = str(dataset["summary"].get("dataset_id") or "dataset")
    filters = st.container(horizontal=True)
    with filters:
        record = st.selectbox(
            "Record",
            [RECORD_ALL, *sorted({card["record_label"] for card in cards})],
            key=f"record_filter_{dataset_id}",
        )
        source = st.selectbox(
            "Source",
            _options(cards, "source_platform"),
            key=f"source_filter_{dataset_id}",
        )
        scope = st.selectbox(
            "Model scope",
            _options(cards, "model_scope_class"),
            key=f"scope_filter_{dataset_id}",
        )
        human = st.selectbox(
            "Human relevance label",
            _options(cards, "human_relevance_label"),
            key=f"human_filter_{dataset_id}",
        )
        status = st.selectbox(
            "Review status",
            _options(cards, "review_status"),
            key=f"review_filter_{dataset_id}",
        )
    shown = filter_cards(
        cards,
        source=source,
        model_scope=scope,
        human_label=human,
        review_status=status,
        record=record,
    )
    st.caption(f"{len(shown)} of {len(cards)} records in this dataset.")
    if not shown:
        st.info("No records match these filters.")
        return
    for card in shown:
        _card(card)


def _dimension_table(bucket: dict) -> None:
    st.markdown(f"**{bucket['scope_class']}** · {bucket['case_count']} case(s)")
    if bucket["case_ids"]:
        st.caption("Cases: " + ", ".join(bucket["case_ids"]))
    for dimension in bucket["dimensions"]:
        st.markdown(dimension["label"])
        if not dimension["rows"]:
            st.caption("No stated value in this group.")
            continue
        for row in dimension["rows"]:
            st.markdown(
                f"- `{row['value']}` — {row['count']} case(s): {', '.join(row['cases'])}"
            )


def _comparison(dataset: dict) -> None:
    st.subheader("Problem comparison")
    _reference_analysis()
    cards = browser_cards(dataset)
    approved = comparison(cards, approved_only=True)
    st.markdown("**Conclusions**")
    st.caption("Only semantically approved cases are compared here. Core and adjacent stay separate.")
    if approved["case_count"] == 0:
        st.info(
            "No extraction case is semantically approved, so this dataset supports no conclusion "
            "and no problem group."
        )
    else:
        left, right = st.columns(2)
        with left:
            _dimension_table(approved["core"])
        with right:
            _dimension_table(approved["adjacent"])
    st.markdown("**Inspection view: unapproved model output**")
    st.caption(
        "These are stored model assignments. They are not findings, not a taxonomy, "
        "and not prevalence in the population."
    )
    inspection = comparison(cards, approved_only=False)
    if inspection["case_count"] == 0:
        st.info("No automatically valid, unapproved extraction case is stored in this dataset.")
        return
    left, right = st.columns(2)
    with left:
        _dimension_table(inspection["core"])
    with right:
        _dimension_table(inspection["adjacent"])
    if inspection["core"]["case_count"] == 0:
        st.caption(f"No unapproved {CORE} case is stored.")
    if inspection["adjacent"]["case_count"] == 0:
        st.caption(f"No unapproved {ADJACENT} case is stored.")


def _quality_result() -> None:
    """Show aggregate evaluation metadata; never load holdout source or predictions."""
    selected = st.session_state.get("quality_metadata_path")
    path = Path(selected) if isinstance(selected, str) else Path(__file__).parent / "data/exports/quality/CURRENT.json"
    st.markdown("**Latest frozen quality measurement**")
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st.info("A saved quality measurement summary is not available here.")
        return
    if current.get("status") != "measured":
        st.info("The quality measurement is pending.")
        return
    state = "passed" if current.get("all_numeric_thresholds_passed") is True else "did not pass"
    st.write(f"The five numeric thresholds {state} on {current.get('holdout_documents')} holdout documents.")
    st.write(f"Recovered reference cases: {current.get('matched_cases')} of {current.get('reference_cases')}.")
    if current.get("development_reference_cases") is not None:
        precision = current.get("development_relevance_precision")
        precision_text = "not recorded" if precision is None else f"{float(precision):.4f}"
        if current.get("development_relevance_precision_passed") is True:
            precision_state = "passed"
        elif current.get("development_relevance_precision_passed") is False:
            precision_state = "missed"
        else:
            precision_state = "was not scored against"
        label = current.get("development_configuration") or "extract/v3"
        st.write(
            f"Development {label} recovered {current.get('development_matched_cases')} of "
            f"{current.get('development_reference_cases')} reference cases. "
            f"Development relevance precision {precision_text} {precision_state} the 0.85 threshold."
        )
        if current.get("development_relevance_precision_passed") is False:
            st.caption(
                "The development precision miss stays visible. Holdout threshold passage does not replace it "
                "or certify extraction quality."
            )
        else:
            st.caption(
                "Development precision met 0.85 on this sample. Case coverage is separate and does not "
                "certify extraction quality."
            )
    st.caption("This separate evaluation does not change the prepared dataset counts or approve its model cases.")
    if current.get("m1_status") == "complete":
        st.caption("M1 is complete as a technical pipeline milestone; extraction semantic quality and the full research programme are separate.")
    for limitation in current.get("limitations") or []:
        st.write("- " + limitation)


def _quality_report() -> None:
    """Split-labeled aggregates only. This view does not load source text."""
    st.subheader("Quality report")
    st.caption("Every number below names the split it came from. This is not full quality certification.")
    selected = st.session_state.get("quality_metadata_path")
    path = Path(selected) if isinstance(selected, str) else Path(__file__).parent / "data/exports/quality/CURRENT.json"
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st.info("A saved quality measurement summary is not available here.")
        return
    splits = current.get("splits") or []
    if not splits:
        st.info("This summary has no split-labeled gate table.")
        _quality_result()
        return
    for row in splits:
        split = row.get("split") or "unlabeled"
        configuration = row.get("configuration")
        st.markdown(f"**{split}{' / ' + configuration if configuration else ''}**")
        _pairs((
            (f"{split} documents", row.get("documents")),
            (f"{split} reference cases recovered", f"{row.get('matched_cases')} of {row.get('reference_cases')}"),
            (f"{split} schema validation", row.get("schema_validation_rate")),
            (f"{split} span validation", row.get("span_validation_rate")),
            (f"{split} prefilter recall", row.get("prefilter_recall")),
            (f"{split} relevance precision", row.get("relevance_precision")),
            (f"{split} relevance recall", row.get("relevance_recall")),
            (f"{split} gate status", row.get("quality_gate_status")),
            (f"{split} excluded technical failures", row.get("excluded_technical_failures")),
        ))
    st.markdown("**Accepted limitations**")
    limitations = current.get("accepted_limitations") or []
    if not limitations:
        st.info("No accepted-limitation list is stored with this summary.")
    for item in limitations:
        st.write(f"- {item.get('split', 'unlabeled')}: {item.get('text', '')}")
    approved = current.get("semantically_approved_cases") or []
    if approved:
        st.caption(
            f"Owner approval is recorded for {len(approved)} named development cases. "
            "The rejected cat summary quote and the schema failure were accepted and were not repaired. "
            "Agreement is null because there is one reviewer."
        )
    else:
        st.caption("Semantic approval of model cases is still absent. Agreement is null because there is one reviewer.")


def _evidence_hits(cards: list[dict], question: str) -> list[dict]:
    words = [word.lower() for word in question.split() if len(word) > 2]
    if not words:
        return []
    hits = []
    for card in cards:
        text = " ".join((
            str(card.get("excerpt") or ""),
            str(card.get("problem_summary") or ""),
        )).lower()
        if all(word in text for word in words):
            hits.append(card)
    return hits


def _ask(cards: list[dict]) -> None:
    """Saved-excerpt search. Synthesis is absent, so no provider is called."""
    st.subheader("Ask the evidence")
    st.caption(
        "Grounded synthesis is not available. A reply quotes a saved excerpt from this dataset. "
        "It is not a new model conclusion and it does not approve the case."
    )
    question = st.text_input("Question about this dataset", key="ask_question")
    if not st.button("Search saved evidence", key="ask_search"):
        st.info("Enter a question and search. An empty search shows no evidence.")
        return
    count = int(st.session_state.get("ask_count") or 0)
    if count >= ASK_QUESTION_CAP:
        st.info(f"This session has reached {ASK_QUESTION_CAP} questions.")
        return
    if not question.strip():
        st.info("Enter a question. An empty question has no evidence to show.")
        return
    st.session_state["ask_count"] = count + 1
    hits = _evidence_hits(cards, question)
    if not hits:
        st.info(
            "The saved excerpts in this dataset do not contain those words. "
            "That is insufficient evidence, not a negative finding about Google Photos."
        )
        return
    st.write(f"Saved excerpts: {len(hits)}. These belong to the prepared sample on this page, not to the holdout measurement.")
    for card in hits[:5]:
        st.markdown(f"**{card.get('doc_id') or 'document'}**")
        st.write(card.get("excerpt") or card.get("problem_summary") or "")
        if card.get("source_url"):
            st.caption(str(card["source_url"]))
        approval = ("Human-approved development reference label; not a model output" if card.get("reference_label_approved")
                    else "semantically approved" if card.get("semantically_approved") else "not semantically approved")
        st.caption(approval)


def _methodology(dataset: dict, index: dict) -> None:
    st.subheader("Methodology and limitations")
    summary = dataset["summary"]
    st.markdown(
        """
This view reads a prepared export of saved runs. It does not call a model,
the YouTube API, or an n8n workflow.

**Provenance.** The development set is the manual pilot import. The YouTube
set is a separate research batch. The manifest names each run. Overlapping
pilot imports are not added together.

**Partial collection.** YouTube comments were collected under a document limit.
Reply coverage is complete only where the saved review says the reply list
finished. A video that was not started contributes no documents.

**Normalization and privacy.** Display text is the redacted audit excerpt.
Author keys are truncated hashes. Emails and phone numbers are masked.
Full source text, salts, and credentials are not in this export.

**Deduplication.** Confirmed duplicate links collapse the analysis-document
count. Pending links do not.

**Bounded model calls.** Relevance and extraction were separate attempts on
the runs named in the export. A cache hit is not a new attempt. Failed and
empty extraction responses are kept for inspection and excluded from conclusions.

**Evidence validation.** A quote is shown as source text only when the stored
offsets match the excerpt. Invented, abbreviated, and spliced quotes stay
labeled as rejected model text.

**Semantic review.** A matching quote can still fail to support the assigned
value. The known gaps are a search method stored as `retrieval_trigger`,
impact or severity without a quote that states it, a `problem_summary` whose
quote misses a factual clause, and a quote that was abbreviated or spliced.
Automatic validity does not approve any of those.

**What a count means.** Every number on the overview is the size of this
collected sample. It is not the prevalence of a problem among Google Photos users.
Quality measurement is reported separately from these prepared sample counts.
        """
    )
    _quality_result()
    st.markdown("**This dataset**")
    for item in summary.get("limitations") or []:
        st.write("- " + item)
    st.markdown("**Not combined into these counts**")
    for item in index.get("not_combined") or []:
        st.write("- " + item)
    st.markdown("**n8n community threads**")
    st.write(
        "The Community insights section can show a saved tagged-thread snapshot, "
        "or a public sheet, and can ask an n8n webhook to fetch more rows. "
        "Those rows are not CollectedDocument records and do not enter "
        "normalization, relevance, or extraction. The mapping in "
        "docs/n8n_import_mapping.md documents the new bounded original-post bridge. "
        "The n8n Cloud endpoint and source-page compatibility still need verification. "
        "Historical tagged summaries are not findings."
    )


def _reference_bundle() -> tuple[dict, list[dict]]:
    folder = st.session_state.get("reference_export_dir")
    if not folder:
        index = _load(_export_dir()).get("index", {})
        folder = index.get("approved_reference_export")
        if folder:
            folder = str(Path(_export_dir()) / folder)
    if not folder:
        return {}, []
    return load_reference(Path(folder))


def _reference_evidence() -> None:
    metadata, records = _reference_bundle()
    st.subheader("Reviewed reference evidence")
    if not metadata:
        st.info("A reviewed development reference export is not included in this bundle.")
        return
    st.write(f"{metadata['cases']} reviewed reference cases across {metadata['documents']} development documents.")
    st.caption("Human-approved reference labels, separate from model outputs. Evidence fragments are not additional cases.")
    for limitation in metadata.get("limitations", []):
        st.caption(limitation)
    wanted = st.selectbox("Reference case", [row["case_id"] for row in metadata["reference_cases"]], key="reference_case")
    case = next(row for row in metadata["reference_cases"] if row["case_id"]==wanted)
    st.write(f"Reviewed scope: {case['scope_class']}")
    for record in records:
        if record["extracted_fields"]["reference_case_id"] != wanted:
            continue
        span = record["evidence_spans"][0]
        st.markdown(f"**{span['field_name']}**")
        value = record["extracted_fields"]["assigned_values"].get(span["field_name"])
        if value:
            st.write(value)
        st.text(record["excerpt"])
        st.caption(f"Source offsets: {span['document_start_char']}–{span['document_end_char']}; approved by Sunayana.")
        st.link_button("Open public source", record["source_url"])


def _reference_analysis() -> None:
    metadata, _records = _reference_bundle()
    if not metadata:
        return
    st.markdown("**Comparison of reviewed development reference labels**")
    st.caption(f"Separate reference sample: {metadata['cases']} cases. These counts are not model performance or population prevalence; no taxonomy or opportunity score is inferred.")
    analysis = reference_comparison(metadata)
    for field, values in analysis.items():
        with st.expander(field.replace("_", " ").capitalize()):
            for row in values["rows"]:
                st.write(f"{row['value']}: {row['count']} case(s) — " + ", ".join(row["cases"]))
            st.caption(f"Unstated, uncertain or unsupported in this export: {len(values['unstated_cases'])} case(s).")


def _reference_journeys() -> None:
    st.subheader("Memory map and journeys")
    _reference_analysis()
    metadata, _records = _reference_bundle()
    if not metadata:
        st.info("No reviewed reference sample is included in this export.")
        return
    for case in metadata["reference_cases"]:
        with st.expander(case["case_id"]):
            st.caption("Open Reviewed reference evidence for verbatim supporting quotes and source links.")
            for field in ("remembered_cues", "forgotten_information", "query_strategies", "system_responses", "outcome"):
                observed = case["assigned_values"].get(field)
                st.write(f"{field.replace('_', ' ')}: {observed if observed else 'not supported in exported reference evidence'}")


def _reference_search_cards() -> list[dict]:
    _metadata, records = _reference_bundle()
    return [{"doc_id":record["doc_id"],
             "case_id":record["extracted_fields"]["reference_case_id"],
             "excerpt":record["excerpt"],"source_url":record["source_url"],
             "reference_label_approved":True,"semantically_approved":False}
            for record in records]


bundle = _load(_export_dir())
if not bundle.get("ok"):
    st.error(bundle.get("message") or "Prepared export is missing.")
    st.stop()

index = bundle["index"]
dataset_ids = [item["dataset_id"] for item in index.get("datasets") or []]
quality_dataset = "development-quality-v6"
default_index = dataset_ids.index(quality_dataset) if quality_dataset in dataset_ids else 0
with st.sidebar:
    st.markdown("**Photo Discovery Lab**")
    st.caption("RESEARCH ENGINE")
    section = st.radio(
        "Navigation",
        SECTIONS,
        format_func=lambda name: NAV_LABELS.get(name, name),
        key="section",
    )
    st.divider()
    st.caption("CORPUS SNAPSHOT")
    dataset_id = st.selectbox(
        "Selected dataset",
        dataset_ids,
        index=default_index,
        key="dataset_quality",
    )
    chosen = next(item for item in index["datasets"] if item["dataset_id"] == dataset_id)
    st.caption(chosen.get("description") or "")
    st.caption(f"Extraction run {chosen.get('run_id')}")

dataset = bundle["datasets"][dataset_id]
if section == "Evidence browser":
    _evidence(dataset)
elif section == "Problem comparison":
    _comparison(dataset)
elif section == "Reviewed reference evidence":
    _reference_evidence()
elif section == "Memory map and journeys":
    _reference_journeys()
elif section == "Quality report":
    _quality_report()
elif section == "Ask the evidence":
    _ask(browser_cards(dataset) + _reference_search_cards())
elif section == "Methodology and limitations":
    _methodology(dataset, index)
elif section == "Community insights":
    render_community_insights()
else:
    _overview(dataset, index)
st.divider()
st.caption("Photo Discovery Lab · Qualitative feedback workbench · Google Photos")
