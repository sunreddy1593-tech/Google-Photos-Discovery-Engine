"""Publish aggregate metadata for the completed v4 experiment, without rescoring."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pointer = ROOT / 'data/exports/quality/CURRENT.json'
backup = ROOT / 'data/interim/submission-preparation-2026-10-04-01/quality-CURRENT-before-v4.json'
if backup.exists():
    raise SystemExit('Summary snapshot already exists; refusing a second mutation')
backup.write_bytes(pointer.read_bytes())
current = json.loads(pointer.read_text(encoding='utf-8'))
report_path = 'data/exports/quality/dev-v4-2026-10-04-01/report.json'
report = json.loads((ROOT / report_path).read_text(encoding='utf-8'))
run = ROOT / 'data/interim/phase6/quality-dev-v4-2026-10-04-01'
summary = json.loads((run / 'summary.json').read_text(encoding='utf-8'))
manifest = json.loads((run / 'extraction/d7581cf180be/run_manifest.json').read_text(encoding='utf-8'))
for row in current['splits']:
    row['configuration'] = 'relevance/v5 + extract/v3'
current['splits'].append({
    'split': 'development', 'configuration': 'relevance/v5 + extract/v4 (separate experiment)',
    'documents': report['documents'], 'matched_cases': report['case_coverage']['matched_cases'],
    'reference_cases': report['gold_cases'],
    'accepted_model_cases': report['case_coverage']['accepted_model_cases'],
    'schema_validation_rate': report['schema_validation_rate'],
    'span_validation_rate': report['span_validation_rate'],
    'prefilter_recall': report['prefilter_recall'],
    'relevance_precision': report['relevance']['precision'],
    'relevance_recall': report['relevance']['recall'],
    'delivered_relevance_recall': 5 / 6,
    'quality_gate_status': report['quality_gate_status'],
    'excluded_technical_failures': report['excluded_technical_failures'],
    'provider_calls': summary['provider_calls'],
    'input_tokens': manifest['tokens']['input_tokens'],
    'output_tokens': manifest['tokens']['output_tokens'],
    'estimated_cost_usd': manifest['tokens']['estimated_cost_usd'],
})
current['candidate_development_report'] = report_path
current['candidate_development_prompt'] = 'extract/v4'
current['candidate_development_matched_cases'] = 4
current['candidate_development_reference_cases'] = 6
current['candidate_development_provider_calls'] = 6
current['candidate_development_authorization_consumed'] = True
current['accepted_limitations'] = [
    item for item in current['accepted_limitations'] if item['split'] != 'submission'
]
current['accepted_limitations'].extend([
    {'split': 'development', 'text': 'Separate extract/v4 experiment matches 4/6, with five accepted cases. Poodle evidence remains in the illustrative setup; cat is blocked by cached relevance evidence. Trigger, date, subject and summary interpretations still require semantic decisions. No model case is approved.'},
    {'split': 'submission', 'text': 'A development-only reviewed-reference export, field comparisons and Cloud package are prepared. Six approved reference cases are not model extraction results. Public deployment and the new n8n Cloud workflow connection remain pending; no new taxonomy or opportunity score is claimed.'},
])
pointer.write_text(json.dumps(current, indent=2) + '\n', encoding='utf-8')
print('Aggregate pointer updated; baseline and holdout reports unchanged')
