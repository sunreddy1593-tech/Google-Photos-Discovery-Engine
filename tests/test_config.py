"""Configuration loading (IMPLEMENTATION-PLAN Phase 0).

Three things are under test: the shipped configuration is valid, a missing
structural key raises ``ConfigError``, and absent optional secrets do not raise.

The third is the one that matters most. The deterministic pipeline and the
evaluator app must both run with no API key, so a loader that demanded one would
break that guarantee before any stage executed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.core.config import (
    Secrets,
    load_settings,
    reset_settings_cache,
)
from src.core.errors import ConfigError


def _write(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# The shipped configuration loads
# --------------------------------------------------------------------------- #


def test_shipped_config_loads(config_dir: Path, empty_env: Path) -> None:
    settings = load_settings(config_dir, env_file=empty_env)

    assert settings.models.provider
    assert settings.analysis.dedupe.min_tokens == 25
    assert settings.analysis.dedupe.simhash_duplicate_max == 3
    assert settings.analysis.dedupe.simhash_review_band_max == 6
    assert settings.analysis.export.excerpt_context_chars == 160
    assert settings.sources.sources, "at least one source must be configured"


def test_taxonomy_ships_empty(config_dir: Path, empty_env: Path) -> None:
    """Invariant I10: no cluster labels before the pilot review (spec Section 20)."""
    settings = load_settings(config_dir, env_file=empty_env)

    assert settings.taxonomy.version == "0-unassigned"
    assert settings.taxonomy.clusters == []


def test_clusters_with_unassigned_version_are_rejected(
    config_dir: Path, empty_env: Path
) -> None:
    """Populating clusters without bumping the version is caught, not tolerated."""
    path = config_dir / "taxonomy.yaml"
    data = _read(path)
    data["clusters"] = [{"id": "c1", "name": "premature cluster"}]
    _write(path, data)

    with pytest.raises(ConfigError, match="must not exist before the pilot"):
        load_settings(config_dir, env_file=empty_env)


def test_no_source_is_enabled_at_phase_zero(
    config_dir: Path, empty_env: Path
) -> None:
    """No collector exists yet, so nothing may be enabled."""
    settings = load_settings(config_dir, env_file=empty_env)
    assert settings.enabled_sources() == {}


def test_config_hash_is_stable_and_excludes_secrets(
    config_dir: Path, empty_env: Path, tmp_path: Path
) -> None:
    first = load_settings(config_dir, env_file=empty_env)

    populated = tmp_path / "populated.env"
    populated.write_text(
        "ANTHROPIC_API_KEY=sk-test-not-a-real-key\nAUTHOR_SALT=test-salt\n",
        encoding="utf-8",
    )
    second = load_settings(config_dir, env_file=populated)

    assert second.secrets.anthropic_api_key == "sk-test-not-a-real-key"
    assert first.config_hash() == second.config_hash(), (
        "config hash must depend on YAML only; if adding a credential moves it, "
        "the hash leaks credential presence into published manifests"
    )


# --------------------------------------------------------------------------- #
# Missing and malformed structural keys raise ConfigError
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("filename", "removed_key"),
    [
        ("models.yaml", "provider"),
        ("models.yaml", "relevance_model"),
        ("analysis.yaml", "dedupe"),
        ("taxonomy.yaml", "version"),
        ("sources.yaml", "sources"),
    ],
)
def test_missing_required_key_raises_config_error(
    config_dir: Path, empty_env: Path, filename: str, removed_key: str
) -> None:
    path = config_dir / filename
    data = _read(path)
    del data[removed_key]
    _write(path, data)

    with pytest.raises(ConfigError) as exc:
        load_settings(config_dir, env_file=empty_env)

    assert filename in str(exc.value)
    assert removed_key in str(exc.value)


def test_missing_file_raises_config_error(
    config_dir: Path, empty_env: Path
) -> None:
    (config_dir / "models.yaml").unlink()

    with pytest.raises(ConfigError, match="not found"):
        load_settings(config_dir, env_file=empty_env)


def test_missing_config_directory_raises_config_error(
    tmp_path: Path, empty_env: Path
) -> None:
    with pytest.raises(ConfigError, match="directory not found"):
        load_settings(tmp_path / "absent", env_file=empty_env)


def test_malformed_yaml_raises_config_error(
    config_dir: Path, empty_env: Path
) -> None:
    (config_dir / "models.yaml").write_text(
        "provider: [unclosed\n", encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="not valid YAML"):
        load_settings(config_dir, env_file=empty_env)


def test_empty_yaml_raises_config_error(
    config_dir: Path, empty_env: Path
) -> None:
    (config_dir / "analysis.yaml").write_text("", encoding="utf-8")

    with pytest.raises(ConfigError, match="is empty"):
        load_settings(config_dir, env_file=empty_env)


def test_unknown_key_is_rejected(config_dir: Path, empty_env: Path) -> None:
    """A typo becomes an error rather than a setting that silently does nothing."""
    path = config_dir / "analysis.yaml"
    data = _read(path)
    data["recency_month"] = 6  # missing 's'
    _write(path, data)

    with pytest.raises(ConfigError, match="recency_month"):
        load_settings(config_dir, env_file=empty_env)


def test_cross_author_auto_collapse_cannot_be_enabled(
    config_dir: Path, empty_env: Path
) -> None:
    """ADR-21's irreversible error is blocked at load, not merely documented.

    Collapsing two genuine users is invisible and unrecoverable, and the signal it
    destroys is the strongest prevalence evidence in the corpus.
    """
    path = config_dir / "analysis.yaml"
    data = _read(path)
    data["dedupe"]["allow_cross_author_auto"] = True
    _write(path, data)

    with pytest.raises(ConfigError, match="never collapsed automatically"):
        load_settings(config_dir, env_file=empty_env)


def test_review_band_below_duplicate_max_is_rejected(
    config_dir: Path, empty_env: Path
) -> None:
    path = config_dir / "analysis.yaml"
    data = _read(path)
    data["dedupe"]["simhash_review_band_max"] = 1
    _write(path, data)

    with pytest.raises(ConfigError, match="review_band_max"):
        load_settings(config_dir, env_file=empty_env)


# --------------------------------------------------------------------------- #
# Optional secrets
# --------------------------------------------------------------------------- #


def test_loads_with_no_secrets_at_all(config_dir: Path, empty_env: Path) -> None:
    """The no-key guarantee: absent credentials must not raise."""
    settings = load_settings(config_dir, env_file=empty_env)

    assert settings.secrets.anthropic_api_key is None
    assert settings.secrets.openai_api_key is None
    assert settings.secrets.author_salt is None
    assert settings.secrets.youtube_api_key is None
    assert settings.secrets.author_salt_id is None


def test_loads_when_env_file_does_not_exist(
    config_dir: Path, tmp_path: Path
) -> None:
    """A fresh clone has no .env at all. That is not an error."""
    settings = load_settings(config_dir, env_file=tmp_path / "nonexistent.env")
    assert settings.secrets.anthropic_api_key is None


def test_has_reports_presence() -> None:
    assert Secrets(_env_file=None, youtube_api_key="k").has("youtube_api_key")
    assert not Secrets(_env_file=None).has("youtube_api_key")


def test_require_raises_config_error_naming_the_variable() -> None:
    secrets = Secrets(_env_file=None)

    with pytest.raises(ConfigError) as exc:
        secrets.require("anthropic_api_key", needed_for="relevance classification")

    message = str(exc.value)
    assert "ANTHROPIC_API_KEY" in message
    assert "relevance classification" in message
    assert ".env.example" in message


def test_require_returns_a_present_value() -> None:
    secrets = Secrets(_env_file=None, author_salt="corpus-salt")
    assert secrets.require("author_salt", needed_for="author hashing") == "corpus-salt"


def test_author_salt_id_is_derived_but_not_the_salt() -> None:
    secrets = Secrets(_env_file=None, author_salt="corpus-salt")
    salt_id = secrets.author_salt_id

    assert salt_id is not None
    assert "corpus-salt" not in salt_id
    assert secrets.author_salt_id == salt_id, "must be deterministic"
    assert Secrets(_env_file=None, author_salt="other").author_salt_id != salt_id


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #


def test_settings_cache_can_be_reset() -> None:
    reset_settings_cache()  # must not raise even when nothing is cached
