"""Render the local evidence page. Highlighting uses stored offsets."""

from __future__ import annotations

from html import escape

from src.browse.findings import REVIEW_RISKS
from src.browse.snapshot import EvidenceCard, ScopeComparison, Snapshot


def render_page(snapshot: Snapshot) -> str:
    """One local page: overview, evidence, and comparison."""
    body = "\n".join(
        (
            _overview(snapshot),
            _evidence(snapshot),
            _comparison(snapshot),
            _groups(snapshot),
            _corrections(snapshot),
        )
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Evidence browser</title>
<style>
:root {{ color-scheme: light; }}
body {{ margin: 0; font: 16px/1.45 Georgia, serif; color: #1c1917; background: #fafaf9; }}
header, main {{ max-width: 960px; margin: 0 auto; padding: 1.25rem; }}
header {{ background: #1c1917; color: #fafaf9; }}
header p {{ margin: 0.4rem 0 0; }}
nav a {{ color: #fafaf9; margin-right: 1rem; }}
h1, h2, h3 {{ font-family: "Segoe UI", sans-serif; line-height: 1.2; }}
h1 {{ margin: 0; font-size: 1.6rem; }}
section {{ margin: 2rem 0; }}
.banner {{ background: #fff7ed; border: 1px solid #c2410c; padding: 0.8rem 1rem; }}
.counts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; }}
.counts article {{ background: white; border: 1px solid #d6d3d1; padding: 0.75rem; }}
.counts strong {{ display: block; font-size: 1.6rem; font-family: "Segoe UI", sans-serif; }}
.counts span {{ color: #44403c; font-size: 0.92rem; }}
article.card, article.column {{ background: white; border: 1px solid #d6d3d1; padding: 1rem; margin: 0.8rem 0; }}
.columns {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
@media (max-width: 720px) {{ .columns {{ grid-template-columns: 1fr; }} }}
mark {{ background: #fde68a; }}
.meta {{ color: #44403c; font-size: 0.92rem; }}
.empty {{ background: #f5f5f4; border: 1px dashed #a8a29e; padding: 0.8rem 1rem; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ text-align: left; border-bottom: 1px solid #e7e5e4; padding: 0.25rem 0.4rem; vertical-align: top; }}
code {{ font-family: Consolas, monospace; font-size: 0.9rem; }}
</style>
</head>
<body>
<header>
<h1>Local evidence browser</h1>
<p>Saved development outputs only. Automatically valid is not semantically approved. No model is called.</p>
<nav>
<a href="#overview">Overview</a>
<a href="#evidence">Evidence</a>
<a href="#comparison">Comparison</a>
<a href="#groups">Provisional groups</a>
</nav>
</header>
<main>
{body}
</main>
</body>
</html>
"""


def _overview(snapshot: Snapshot) -> str:
    counts = (
        ("Collected", snapshot.collected, "Development documents. Holdout text is not loaded."),
        ("Excluded", snapshot.excluded, "Development documents labeled out of scope."),
        ("Failed", snapshot.failed, "Extraction attempts that are not ok."),
        ("Automatically valid", snapshot.automatically_valid, "Evidence gate passed. Not semantic approval."),
        ("Human-reviewed", snapshot.human_reviewed, "Development documents with a human relevance label."),
        ("Unresolved", snapshot.unresolved, "Open review items. They are not research conclusions."),
    )
    articles = "\n".join(
        f"<article><strong>{count}</strong><span>{escape(label)}. {escape(note)}</span></article>"
        for label, count, note in counts
    )
    missing = ""
    if snapshot.missing:
        missing = "<p class='empty'>Missing inputs: " + escape(", ".join(snapshot.missing)) + "</p>"
    risks = "".join(f"<li>{escape(item)}</li>" for item in REVIEW_RISKS)
    return f"""
<section id="overview">
<h2>Corpus overview</h2>
<p class="banner">Semantic approval: {snapshot.semantically_approved}. Automatic validity does not approve a case.</p>
<div class="counts">{articles}</div>
<p class="meta">Collected records {snapshot.collected_records}. Analysis documents after confirmed duplicates {snapshot.analysis_documents}. Confirmed duplicate links {snapshot.confirmed_duplicates}. Pending duplicate links {snapshot.pending_duplicates}, not counted as duplicates. Holdout withheld {snapshot.withheld_holdout}.</p>
{missing}
<h3>Known semantic risks</h3>
<ul>{risks}</ul>
</section>
"""


def _evidence(snapshot: Snapshot) -> str:
    shown = [card for card in snapshot.cards if _visible(card)]
    if not shown:
        body = "<p class='empty'>No stored extraction evidence is available to browse.</p>"
    else:
        body = "\n".join(_card(card) for card in shown)
    return f"""
<section id="evidence">
<h2>Evidence</h2>
<p class="meta">Excerpts are redacted audit text. Highlights use stored offsets. Complete raw text stays in the local collection files and is not shown.</p>
{body}
</section>
"""


def _visible(card: EvidenceCard) -> bool:
    status = card.review_status
    return bool(
        card.automatically_valid
        or card.case_id
        or card.findings
        or "unresolved" in status
        or "failed" in status
    )


def _card(card: EvidenceCard) -> str:
    title = escape(card.case_id or card.doc_id)
    scope = "Core" if card.scope_class == "core_incomplete_recall" else (
        "Adjacent" if card.scope_class == "adjacent_known_item_retrieval" else escape(card.scope_class or "scope not stored")
    )
    link = (
        f"<a href='{escape(card.source_url, quote=True)}'>Source</a>"
        if card.source_url
        else "No source link stored"
    )
    values = _table(card.values) if card.values else "<p class='empty'>No extracted values are stored for this record.</p>"
    quotes = _quotes(card)
    findings = "".join(
        f"<li><strong>{escape(item.field)}</strong> ({escape(item.risk)}): {escape(item.summary)} "
        f"<span class='meta'>{escape(item.source_note)}</span></li>"
        for item in card.findings
    ) or "<li>No recorded semantic finding for this record.</li>"
    excerpt = _mark(card.excerpt, card.highlights) if card.excerpt else "<p class='empty'>No redacted excerpt is stored for this document.</p>"
    approval = (
        "<p class='banner'>Automatically valid. This is not semantic approval.</p>"
        if card.automatically_valid and not card.enters_conclusions
        else ""
    )
    return f"""
<article class="card">
<h3><code>{title}</code></h3>
{approval}
<p class="meta">{scope}. Human relevance label: {escape(card.human_scope or 'none')}. {link}. Platform: {escape(card.source_platform or 'unknown')}.</p>
<p class="meta">Review: {escape(card.review_status)}</p>
<h4>Excerpt</h4>
<p>{excerpt}</p>
<h4>Extracted values</h4>
{values}
<h4>Supporting quotes</h4>
{quotes}
<h4>Semantic review</h4>
<ul>{findings}</ul>
</article>
"""


def _quotes(card: EvidenceCard) -> str:
    if not card.quotes:
        return "<p class='empty'>No supporting quote is stored.</p>"
    rows = []
    for quote in card.quotes:
        flag = "offset matches the redacted text" if quote.offset_matches else "offset does not match the redacted text"
        rows.append(
            f"<tr><td>{escape(quote.field_name)}</td><td>{escape(quote.validation_state)}</td>"
            f"<td>{escape(quote.text)}</td><td>{flag}</td></tr>"
        )
    return "<table><tr><th>Field</th><th>Validation</th><th>Quote from the redacted text</th><th>Offset</th></tr>" + "".join(rows) + "</table>"


def _comparison(snapshot: Snapshot) -> str:
    conclusion = (
        "<p class='empty'>No semantically approved case is available, so this page states no research conclusion.</p>"
        if snapshot.conclusion_cases == 0
        else f"<p>{snapshot.conclusion_cases} semantically approved cases are included in conclusions.</p>"
    )
    return f"""
<section id="comparison">
<h2>Comparison</h2>
<p class="banner">The distributions below are model output from automatically valid cases. They are not research conclusions. Failed and unresolved records are omitted. Core and adjacent stay separate.</p>
{conclusion}
<div class="columns">
{_column(snapshot.core)}
{_column(snapshot.adjacent)}
</div>
</section>
"""


def _column(column: ScopeComparison) -> str:
    if column.model_cases == 0:
        body = f"<p class='empty'>{escape(column.empty_reason)}</p>"
    else:
        body = "\n".join(
            (
                f"<h4>Retrieval targets</h4>{_table(column.targets)}",
                f"<h4>Remembered cues</h4>{_table(column.cues)}",
                f"<h4>Search behavior</h4>{_table(column.strategies)}",
                f"<h4>System responses</h4>{_table(column.responses)}",
                f"<h4>Outcomes</h4>{_table(column.outcomes)}",
                f"<h4>Source distribution</h4>{_table(column.sources)}",
            )
        )
    return f"<article class='column'><h3>{escape(column.label)}</h3><p class='meta'>{column.model_cases} automatically valid cases. Not a conclusion.</p>{body}</article>"


def _groups(snapshot: Snapshot) -> str:
    if not snapshot.groups:
        body = f"<p class='empty'>{escape(snapshot.group_reason)}</p>"
    else:
        items = "".join(
            f"<li><strong>Provisional.</strong> {escape(group.label)}: {escape(', '.join(group.case_ids))}</li>"
            for group in snapshot.groups
        )
        body = f"<p>{escape(snapshot.group_reason)}</p><ul>{items}</ul>"
    return f"""
<section id="groups">
<h2>Provisional problem groups</h2>
<p class="banner">Provisional. These are not established clusters and not opportunity scores.</p>
{body}
</section>
"""


def _corrections(snapshot: Snapshot) -> str:
    if not snapshot.corrections:
        body = "<p class='empty'>No human corrections are recorded. Saved model output is unchanged.</p>"
    else:
        rows = "".join(
            "<tr>"
            f"<td><code>{escape(item.case_id)}</code></td>"
            f"<td>{escape(item.field)}</td>"
            f"<td>{escape(item.original_value)}</td>"
            f"<td>{escape(item.corrected_value)}</td>"
            f"<td>{escape(item.reviewer)}</td>"
            f"<td>{escape(item.note)}</td>"
            "</tr>"
            for item in snapshot.corrections
        )
        body = (
            "<p>Corrections are listed beside the original value. The saved model record is not rewritten.</p>"
            "<table><tr><th>Case</th><th>Field</th><th>Original model value</th><th>Correction</th><th>Reviewer</th><th>Note</th></tr>"
            f"{rows}</table>"
        )
    return f"<section id='corrections'><h2>Human corrections</h2>{body}</section>"


def _table(rows: tuple[tuple[str, str], ...] | tuple[tuple[str, int], ...]) -> str:
    if not rows:
        return "<p class='empty'>Nothing stated in this column.</p>"
    body = "".join(f"<tr><td>{escape(str(name))}</td><td>{escape(str(value))}</td></tr>" for name, value in rows)
    return f"<table>{body}</table>"


def _mark(excerpt: str, highlights: tuple[tuple[int, int], ...]) -> str:
    if not highlights:
        return escape(excerpt)
    cursor = 0
    parts: list[str] = []
    for start, end in sorted(highlights):
        start = max(cursor, min(start, len(excerpt)))
        end = max(start, min(end, len(excerpt)))
        parts.append(escape(excerpt[cursor:start]))
        parts.append(f"<mark>{escape(excerpt[start:end])}</mark>")
        cursor = end
    parts.append(escape(excerpt[cursor:]))
    return "".join(parts)
