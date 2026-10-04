"""Bounded n8n original-post bridge; never import workflow summaries as source."""
from __future__ import annotations

import json
import re
from datetime import datetime, UTC
from pathlib import Path
from urllib.parse import urlsplit

import requests

from src.core.errors import ConfigError
from src.core.ids import author_hash, author_salt_id, doc_id, raw_text_sha256, source_url_key
from src.models.collected_document import CollectedDocument

CONTRACT = "community-collection/v1"
MAX_DOCUMENTS = 20


def thread_id(url: str) -> str:
    parts = urlsplit(url)
    match = re.fullmatch(r"/photos/thread/(\d+)(?:/[^/]*)?/?", parts.path)
    if parts.scheme != "https" or parts.netloc != "support.google.com" or not match:
        raise ValueError("Only direct HTTPS Google Photos community thread URLs are allowed")
    return match[1]


def import_payload(payload: dict, output: Path, *, author_salt: str,
                   document_limit: int, dry_run: bool = False) -> dict:
    if not author_salt:
        raise ConfigError("AUTHOR_SALT is required for community import")
    if not 1 <= document_limit <= MAX_DOCUMENTS:
        raise ValueError("community document limit must be between 1 and 20")
    if not isinstance(payload, dict):
        raise ValueError("Collection envelope must be an object")
    if (payload.get("contract") != CONTRACT or type(payload.get("model_calls")) is not int or payload.get("model_calls") != 0
            or not isinstance(payload.get("items"), list)
            or not isinstance(payload.get("execution_id"), str) or not payload["execution_id"]):
        raise ValueError("Original-post collection contract required; tagged summaries are refused")
    if len(payload["items"]) > document_limit:
        raise ValueError("returned documents exceed the requested bound")
    documents = []
    for row in payload["items"]:
        if not isinstance(row, dict) or not all(key in row for key in ("source_url","raw_text","collected_at")):
            raise ValueError("Original-post collection fields are missing")
        if not isinstance(row["source_url"], str):
            raise ValueError("Source URL must be a string")
        url = row["source_url"]
        item_id = thread_id(url)
        if row.get("text_kind") != "original_post" or row.get("replies_complete") is not False:
            raise ValueError("Only identified original posts with replies explicitly unfetched are supported")
        text = row["raw_text"]
        if not isinstance(text, str) or not text.strip() or re.search(r"</?[A-Za-z][^>]*>", text):
            raise ValueError("Unmodified plain source text is required; HTML and summaries are refused")
        if str(row.get("source_item_id")) != item_id:
            raise ValueError("Source item ID does not match its direct URL")
        author = row.get("author_name")
        documents.append(CollectedDocument(
            doc_id=doc_id("google_support", source_item_id=item_id),
            ingest_batch_id=f"n8n-{payload['execution_id']}", source_platform="google_support",
            source_type="support_thread", evidence_tier="direct_user", source_item_id=item_id,
            source_url=url, source_url_key=source_url_key(url), source_name="Google Photos Help",
            title=row.get("title"), raw_text=text, raw_text_sha256=raw_text_sha256(text),
            author_hash=author_hash(author_salt, "google_support", author) if author else None,
            author_salt_id=author_salt_id(author_salt), published_at=row.get("published_at"),
            collected_at=row["collected_at"], collection_method="other",
            metadata={"collector":"n8n", "contract":CONTRACT, "execution_id":payload["execution_id"],
                      "text_kind":"original_post", "replies_complete":False,
                      "source_text_path":row.get("source_text_path", "QAPage.mainEntity.text")},
        ))
    path = output / "collected_documents.jsonl"
    known = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                old = CollectedDocument.model_validate_json(line)
                known[old.source_url_key] = old
    pending = []
    duplicates = 0
    for document in documents:
        key = document.source_url_key
        if key in known:
            if known[key].raw_text_sha256 != document.raw_text_sha256:
                raise ValueError("Previously collected source text changed; preserve it and review separately")
            duplicates += 1
        else:
            known[key] = document
            pending.append(document)
    result = {"documents_seen":len(documents), "documents_written":0 if dry_run else len(pending),
              "already_present":duplicates, "provider_calls":0, "dry_run":dry_run,
              "collection_requests_reported":payload.get("requests_made"),
              "failures":len(payload.get("failures") or []), "replies_complete":False}
    if dry_run:
        return result
    output.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for document in pending:
            handle.write(document.model_dump_json()+"\n")
    # Each import has its own report. Existing reports are never replaced.
    report = output / f"collection-report-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.json"
    report.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    return result


def collect_webhook(url_file: Path, output: Path, *, webhook_url: str, key: str,
                    author_salt: str, document_limit: int, request_budget: int,
                    dry_run: bool = False, transport=None) -> dict:
    if not webhook_url or not key or not author_salt:
        raise ConfigError("N8N_COLLECTION_WEBHOOK_URL, N8N_WEBHOOK_KEY and AUTHOR_SALT are required")
    endpoint = urlsplit(webhook_url)
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.query:
        raise ValueError("Collection webhook must be an HTTPS URL without embedded credentials or query")
    if endpoint.path != "/webhook/discovery-original-posts-v1":
        raise ValueError("Only the dedicated collection-only production webhook is supported; the tagging route is refused")
    if not 1 <= document_limit <= 20 or not 1 <= request_budget <= 20:
        raise ValueError("Collection bounds must be between 1 and 20")
    urls = list(dict.fromkeys(line.strip() for line in url_file.read_text(encoding="utf-8").splitlines()
                              if line.strip() and not line.lstrip().startswith("#")))
    for url in urls:
        thread_id(url)
    if not urls or len(urls) > min(document_limit, request_budget):
        raise ValueError("URL count must fit both document and collection-request budgets")
    if output.exists():
        raise ValueError("Live webhook collection requires a fresh output parent")
    if dry_run:
        return {"documents":len(urls), "webhook_requests":0, "collection_requests":0,
                "model_calls":0, "documents_written":0, "dry_run":True}
    post = transport or requests.post
    try:
        response = post(webhook_url, headers={"X-Api-Key":key},
                        json={"contract":CONTRACT, "urls":urls, "document_limit":document_limit,
                              "request_budget":request_budget, "model_calls":0},
                        timeout=120, allow_redirects=False)
        if response.status_code != 200:
            raise ValueError("n8n collection returned an unsuccessful HTTP status; no automatic retry")
        payload = response.json()
    except (requests.RequestException, ValueError):
        raise ValueError("n8n collection failed; no automatic retry or output creation") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("n8n response must be a collection envelope, not a workflow-start acknowledgement")
    made = payload.get("requests_made")
    if type(made) is not int or not 0 <= made <= request_budget:
        raise ValueError("n8n response does not attest the requested collection budget")
    requested_ids = {thread_id(url) for url in urls}
    if any(not isinstance(row, dict) or str(row.get("source_item_id")) not in requested_ids for row in payload["items"]):
        raise ValueError("n8n returned an unrequested source item")
    result = import_payload(payload, output, author_salt=author_salt, document_limit=document_limit)
    result["webhook_requests"] = 1
    return result
