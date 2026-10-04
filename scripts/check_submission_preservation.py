"""Hash-only verification of retained data; no source-based evaluation."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
baseline = json.loads((root / 'data/interim/phase6/quality-preservation-2026-10-04-01.json').read_text(encoding='utf-8'))
allowed = {'data/gold/documents.jsonl', 'data/gold/cases.jsonl'}
changed = []
unexpected = []
for name, expected in baseline.items():
    path = root / name
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    if digest != expected:
        changed.append(name)
        if name not in allowed:
            unexpected.append(name)
        else:
            backup = root / 'data/gold/pre-quality-freeze-2026-10-04-01' / path.name
            assert hashlib.sha256(backup.read_bytes()).hexdigest() == expected
assert not unexpected, unexpected
completed = json.loads((root / 'data/interim/phase6/quality-freeze-2026-10-04-01/measurement_completed.json').read_text(encoding='utf-8'))
artifacts = completed['artifact_sha256']
for name, expected in artifacts.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
result = {'baseline_files_checked': len(baseline), 'prior_authorized_gold_changes': sorted(changed),
          'unexpected_changes': unexpected, 'frozen_measurement_files_checked': len(artifacts),
          'method': 'hashes only; no source text interpreted'}
dest = root / 'data/interim/submission-preparation-2026-10-04-01/preservation-final.json'
if dest.exists():
    raise SystemExit('Preservation report exists; refusing overwrite')
dest.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result))
