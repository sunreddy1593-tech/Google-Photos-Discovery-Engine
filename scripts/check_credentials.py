"""Report which optional source credentials are present. Values are not printed."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.collect.reddit import credentials_present
from src.core.config import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check optional source credentials.")
    parser.add_argument("--env-file", type=Path, default=None)
    args = parser.parse_args(argv)
    settings = load_settings(env_file=args.env_file) if args.env_file else load_settings()
    secrets = settings.secrets
    reddit = credentials_present(
        secrets.reddit_client_id,
        secrets.reddit_client_secret,
        secrets.reddit_user_agent,
    )
    rows = [
        ("youtube", "configured" if secrets.youtube_api_key else "source disabled"),
        ("reddit", "configured" if reddit else "source disabled"),
        ("groq", "configured" if secrets.groq_api_key else "source disabled"),
        (
            "n8n",
            "configured"
            if secrets.n8n_collection_webhook_url and secrets.n8n_webhook_key
            else "source disabled",
        ),
    ]
    for name, status in rows:
        print(f"{name}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
