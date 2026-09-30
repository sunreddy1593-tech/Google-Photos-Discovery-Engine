"""Parent-thread context for a reply, chosen by split membership.

The lookup uses document ids and thread ids. Parent text is requested only
when that parent is in the development split. A holdout parent, or a parent
that cannot be identified, is marked incomplete and its text is not read.
Human labels and notes are never context.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from src.relevance.split import SPLIT_DEVELOPMENT

CONTEXT_NONE = "none"
CONTEXT_INCLUDED = "included"
CONTEXT_INCOMPLETE = "incomplete"

TextLookup = Callable[[str], tuple[str | None, str, str]]


@dataclass(frozen=True)
class DocumentLink:
    """Identity fields only. No title and no body."""

    doc_id: str
    source_item_id: str | None
    parent_thread_id: str | None


@dataclass(frozen=True)
class ParentContext:
    """Included text belongs to the parent document, not the reply."""

    status: str
    parent_doc_id: str | None = None
    parent_thread_id: str | None = None
    title: str | None = None
    text: str | None = None
    content_hash: str | None = None

    def cache_fields(self) -> dict[str, str]:
        """Identity that must move the response cache when context changes."""
        if self.status == CONTEXT_NONE:
            return {}
        fields = {
            "context_status": self.status,
            "context_doc_id": self.parent_doc_id or "",
            "context_thread_id": self.parent_thread_id or "",
        }
        if self.status == CONTEXT_INCLUDED:
            fields["context_content_hash"] = self.content_hash or ""
        return fields


def resolve_parent_context(
    target: DocumentLink,
    links: Sequence[DocumentLink],
    splits: Mapping[str, str],
    text_for: TextLookup,
) -> ParentContext:
    """Resolve one reply. ``text_for`` runs only for a development parent."""
    thread_id = target.parent_thread_id
    if not thread_id:
        return ParentContext(status=CONTEXT_NONE)
    parent = next(
        (link for link in links if link.source_item_id == thread_id),
        None,
    )
    if parent is None or splits.get(parent.doc_id) != SPLIT_DEVELOPMENT:
        return ParentContext(
            status=CONTEXT_INCOMPLETE,
            parent_doc_id=None if parent is None else parent.doc_id,
            parent_thread_id=thread_id,
        )
    title, text, content_hash = text_for(parent.doc_id)
    return ParentContext(
        status=CONTEXT_INCLUDED,
        parent_doc_id=parent.doc_id,
        parent_thread_id=thread_id,
        title=title,
        text=text,
        content_hash=content_hash,
    )


class ContextAccessError(ValueError):
    """Parent text was requested for a document outside the development split."""


def guarded_parent_contexts(
    targets: Sequence[str],
    links: Sequence[DocumentLink],
    splits: Mapping[str, str],
    title_of: Callable[[str], str | None],
    audit_of: Callable[[str], str],
    hash_of: Callable[[str], str],
) -> dict[str, ParentContext]:
    """Build contexts. Title and audit callbacks run only for a development parent."""

    def text_for(doc_id: str) -> tuple[str | None, str, str]:
        if splits.get(doc_id) != SPLIT_DEVELOPMENT:
            raise ContextAccessError(
                "refusing to read a parent outside the development split"
            )
        return title_of(doc_id), audit_of(doc_id), hash_of(doc_id)

    return assemble_parent_contexts(targets, links, splits, text_for)


def assemble_parent_contexts(
    targets: Sequence[str],
    links: Sequence[DocumentLink],
    splits: Mapping[str, str],
    text_for: TextLookup,
) -> dict[str, ParentContext]:
    """Resolve context for ``targets``. ``links`` may include documents not classified."""
    by_id = {link.doc_id: link for link in links}
    return {
        doc_id: resolve_parent_context(by_id[doc_id], links, splits, text_for)
        for doc_id in targets
        if doc_id in by_id
    }


def cross_split_families(
    links: Sequence[DocumentLink],
    splits: Mapping[str, str],
) -> tuple[dict[str, object], ...]:
    """Threads whose members are not all in one split. Metadata only."""
    grouped: dict[str, list[DocumentLink]] = {}
    for link in links:
        if link.parent_thread_id:
            grouped.setdefault(link.parent_thread_id, []).append(link)
    families: list[dict[str, object]] = []
    by_item = {
        link.source_item_id: link for link in links if link.source_item_id
    }
    for thread_id, replies in sorted(grouped.items()):
        members: list[DocumentLink] = []
        parent = by_item.get(thread_id)
        if parent is not None:
            members.append(parent)
        members.extend(replies)
        member_splits = {splits.get(member.doc_id, "unlabeled") for member in members}
        if len(member_splits) < 2:
            continue
        families.append(
            {
                "parent_thread_id": thread_id,
                "members": [
                    {
                        "doc_id": member.doc_id,
                        "split": splits.get(member.doc_id, "unlabeled"),
                        "role": "parent" if member.source_item_id == thread_id else "reply",
                    }
                    for member in members
                ],
            }
        )
    return tuple(families)
