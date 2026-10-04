"""Offline inspection of the completed, explicitly authorized development run."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.gold.load import load_gold_cases, load_gold_documents
from src.gold.match import match_cases
from src.gold.saved_run import load_saved_development

pack = ROOT / 'data/annotation/dev-starter-2026-10-03/sunayana-reviewed-02'
gold = pack / 'development-reference-02'
run = ROOT / 'data/interim/phase6/quality-dev-v4-2026-10-04-01'
inputs = load_saved_development(
    doc_ids={d.doc_id for d in load_gold_documents(gold / 'documents.jsonl')},
    run=run / 'extraction/d7581cf180be',
    relevance=run / 'relevance/relevance_decisions.jsonl', pack=pack,
    prefilter_events=run / 'relevance/stage_events.jsonl',
)
for case in load_gold_cases(gold / 'cases.jsonl'):
    models = [c for c in inputs.extracted_cases if c.doc_id == case.doc_id]
    print(json.dumps({
        'doc_id': case.doc_id,
        'source_text': inputs.texts[case.doc_id],
        'matched': bool(match_cases([case], models, inputs.texts[case.doc_id])),
        'gold_evidence': case.expected_evidence,
        'gold_values': case.expected_values,
        'model_values': [c.values for c in models],
        'spans': [[vars(s) for s in c.spans] for c in models],
    }, ensure_ascii=True))
