"""BM25 over saved case text, with a minimum score and a per-source cap.

Filters run before ranking. A question whose best score is below ``min_score``
returns no records. There is no embedding index and no model call.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Mapping

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    {
        "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "how",
        "do", "does", "people", "with", "from", "is", "are", "what", "me",
    }
)
_K1 = 1.5
_B = 0.75


def _tokens(text: str) -> list[str]:
    return [token for token in _TOKEN.findall(text.lower()) if token not in _STOP]


def _document_text(record: Mapping[str, object]) -> str:
    parts = [
        str(record.get("problem_summary") or ""),
        str(record.get("labels") or ""),
        str(record.get("quotes") or ""),
        str(record.get("excerpt") or ""),
    ]
    return " ".join(parts)


def _passes(record: Mapping[str, object], filters: Mapping[str, str] | None) -> bool:
    if not filters:
        return True
    for key, expected in filters.items():
        if str(record.get(key) or "") != expected:
            return False
    return True


def search(
    question: str,
    records: list[Mapping[str, object]] | None = None,
    *,
    filters: Mapping[str, str] | None = None,
    min_score: float = 0.15,
    top_k: int = 10,
    per_source_cap: int = 3,
) -> list[dict[str, object]]:
    """Rank ``records``. No records, or no score at the threshold, returns []."""
    if not records or not question.strip():
        return []
    pool = [record for record in records if _passes(record, filters)]
    if not pool:
        return []
    docs = [_tokens(_document_text(record)) for record in pool]
    query = _tokens(question)
    if not query:
        return []
    avg = sum(len(tokens) for tokens in docs) / len(docs)
    document_frequency: Counter[str] = Counter()
    for tokens in docs:
        document_frequency.update(set(tokens))
    total = len(docs)
    scored: list[tuple[float, Mapping[str, object]]] = []
    for record, tokens in zip(pool, docs, strict=True):
        counts = Counter(tokens)
        score = 0.0
        for term in query:
            tf = counts[term]
            if tf == 0:
                continue
            df = document_frequency[term]
            idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
            norm = tf * (_K1 + 1) / (tf + _K1 * (1 - _B + _B * len(tokens) / avg))
            score += idf * norm
        scored.append((score, record))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("case_id") or "")))
    if not scored or scored[0][0] < min_score:
        return []
    kept: list[dict[str, object]] = []
    per_source: Counter[str] = Counter()
    for score, record in scored:
        if score < min_score:
            break
        source = str(record.get("source") or "")
        if per_source[source] >= per_source_cap:
            continue
        per_source[source] += 1
        kept.append({"case_id": record.get("case_id"), "score": score, "source": source})
        if len(kept) >= top_k:
            break
    return kept
