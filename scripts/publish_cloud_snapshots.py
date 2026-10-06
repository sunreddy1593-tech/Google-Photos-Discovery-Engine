"""Publish saved public snapshots after a scheduled run, without collecting data."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.export.cloud_publication import publish_cloud_snapshots

if __name__ == "__main__":
    outcome = publish_cloud_snapshots(ROOT)
    print("Cloud snapshot publication: " + json.dumps(outcome))
    raise SystemExit(0 if outcome.get("ok") else 1)
