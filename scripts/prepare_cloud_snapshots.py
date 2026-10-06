"""Package current public snapshots for Git-backed Streamlit deployment, offline."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.export.cloud_snapshots import prepare_cloud_snapshots

if __name__ == "__main__":
    print(json.dumps(prepare_cloud_snapshots(ROOT), indent=2))
