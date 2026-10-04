"""Typed configuration over ``config/*.yaml`` plus ``.env``.

**This is the only module that reads the environment** (ARCHITECTURE 16.1).
Everything else takes a ``Settings`` object. ``tests/test_architecture.py``
enforces that boundary, because a single stray ``os.environ`` read elsewhere is
how an undocumented setting appears.

The requiredness split is the important design decision here:

* **Secrets are all optional at load time.** ``Settings`` builds successfully
  with no ``.env`` file and nothing exported. This is not laxity — the
  deterministic pipeline and the evaluator app must both run with no API key
  (spec Sections 13.1, 22.3, 23), so a loader that demanded a key would break
  the guarantee before any stage ran. Requiredness is enforced at point of use
  via :meth:`Secrets.require`, which raises ``ConfigError`` naming the variable
  and the reason it is needed.
* **Structural YAML keys are required.** A ``taxonomy.yaml`` with no ``version``
  or an ``analysis.yaml`` with no dedupe block is a broken configuration, not a
  degraded one, and it fails immediately with ``ConfigError``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticError
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.errors import ConfigError
from src.core.ids import author_salt_id
from src.core.versions import TAXONOMY_VERSION

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR: Final[Path] = PROJECT_ROOT / "config"


# --------------------------------------------------------------------------- #
# Secrets
# --------------------------------------------------------------------------- #


class Secrets(BaseSettings):
    """Credentials from ``.env`` or the process environment.

    Every field is optional. See the module docstring for why.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    groq_api_key: str | None = None
    author_salt: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str | None = None
    youtube_api_key: str | None = None
    n8n_collection_webhook_url: str | None = None
    n8n_webhook_key: str | None = None

    def require(self, field: str, *, needed_for: str) -> str:
        """Return a secret's value, or raise ``ConfigError`` explaining the need.

        Stages call this instead of reading the attribute, so a missing
        credential produces one actionable message rather than a ``None``
        propagating into a provider call.
        """
        value = getattr(self, field, None)
        if not value:
            raise ConfigError(
                f"{field.upper()} is not set but is required for {needed_for}. "
                f"Add it to .env (see .env.example)."
            )
        return value

    def has(self, field: str) -> bool:
        """Whether a secret is present, for cleanly skipping optional sources."""
        return bool(getattr(self, field, None))

    @property
    def author_salt_id(self) -> str | None:
        """Salt identifier for the manifest, or ``None`` when unset.

        The salt value itself is never recorded or exported (spec 12.1).
        """
        return author_salt_id(self.author_salt) if self.author_salt else None


# --------------------------------------------------------------------------- #
# YAML sections
# --------------------------------------------------------------------------- #


class _Section(BaseModel):
    """Base for YAML-backed config. Unknown keys are rejected.

    ``extra="forbid"`` turns a typo into an error rather than a silently ignored
    setting — the failure mode where someone edits a threshold, sees no effect,
    and concludes the threshold does not work.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceEntry(_Section):
    """One configured source and its feasibility tier (spec Section 11.4)."""

    enabled: bool = False
    tier: str
    collection_method: str
    queries: list[str] = Field(default_factory=list)
    rate_limit_per_minute: int | None = None
    notes: str | None = None


class SourcesConfig(_Section):
    recency_months: int = 12
    languages: list[str] = Field(default_factory=lambda: ["en"])
    sources: dict[str, SourceEntry]


class ModelsConfig(_Section):
    provider: str
    api_key_env: str = "ANTHROPIC_API_KEY"
    prefilter_model: str | None = None
    relevance_model: str
    extraction_model: str
    anthropic_relevance_model: str = "claude-sonnet-4-5"
    groq_relevance_model: str = "openai/gpt-oss-120b"
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout_seconds: int = 60
    max_retries: int = 3
    # List-price estimates only. They are not an invoice and they are not
    # actual billed cost. Cached input is optional; a missing count bills
    # every input token at the normal input rate.
    estimated_input_usd_per_million: float = 0.0
    estimated_cached_input_usd_per_million: float | None = None
    estimated_output_usd_per_million: float = 0.0
    list_price_source: str = ""
    list_price_retrieved_on: str = ""

    def relevance_choice(self, override: str | None = None) -> tuple[str, str, str]:
        """Active relevance provider, model, and environment-variable name.

        The returned name is the variable, never a key value. An explicit
        override selects that adapter. Anthropic stays available when Groq is
        the configured smoke provider.
        """
        name = override or self.provider
        if name == "groq":
            model = self.relevance_model if self.provider == "groq" else self.groq_relevance_model
            return "groq", model, "GROQ_API_KEY"
        if name == "anthropic":
            model = (
                self.relevance_model
                if self.provider == "anthropic"
                else self.anthropic_relevance_model
            )
            return "anthropic", model, "ANTHROPIC_API_KEY"
        if override is None:
            return self.provider, self.relevance_model, self.api_key_env
        raise ValueError(f"unsupported relevance provider {name!r}")


class DedupeConfig(_Section):
    """Thresholds from spec Section 26.5.

    ``allow_cross_author_auto`` must stay ``False``. Two people independently
    writing "can't find my photos" are two users with the same complaint — the
    strongest prevalence signal in the corpus — and automatic collapsing would
    delete precisely that signal while reporting a healthy-looking duplicate
    rate. ``model_post_init`` refuses to load a config that flips it.
    """

    simhash_duplicate_max: int = 3
    simhash_review_band_max: int = 6
    min_tokens: int = 25
    allow_cross_author_auto: bool = False

    def model_post_init(self, _context: Any) -> None:
        if self.allow_cross_author_auto:
            raise ValueError(
                "dedupe.allow_cross_author_auto must remain false: identical "
                "text from different authors is never collapsed automatically "
                "(spec Section 19.6, ADR-21)"
            )
        if self.simhash_review_band_max < self.simhash_duplicate_max:
            raise ValueError(
                "dedupe.simhash_review_band_max must be >= simhash_duplicate_max"
            )


class ExportConfig(_Section):
    """Public-export profile settings (spec Section 12.1, ADR-23)."""

    excerpt_context_chars: int = 160
    allow_full_text_sources: list[str] = Field(default_factory=list)


class RetrievalConfig(_Section):
    top_k: int = 10
    min_score: float = 0.15


class RelevanceRoutingConfig(_Section):
    """When a stored decision still needs a person.

    The threshold does not change ``scope_class``. It only opens a review item.
    """

    confidence_review_below: float = Field(default=0.7, ge=0.0, le=1.0)


class AnalysisConfig(_Section):
    dedupe: DedupeConfig
    export: ExportConfig = Field(default_factory=ExportConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    relevance: RelevanceRoutingConfig = Field(default_factory=RelevanceRoutingConfig)
    recency_months: int = 12
    source_concentration_threshold: float = 0.40
    composite_score_enabled: bool = False
    composite_weights: dict[str, float] = Field(default_factory=dict)


class TaxonomyConfig(_Section):
    """Taxonomy version and clusters.

    Ships empty at ``0-unassigned``. Invariant I10: cluster labels must not exist
    in code or config before the pilot review produces them (spec Section 20).
    """

    version: str
    clusters: list[dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #


class Settings(BaseModel):
    """Everything the pipeline needs to run, loaded and validated once."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    project_root: Path
    config_dir: Path
    secrets: Secrets
    sources: SourcesConfig
    models: ModelsConfig
    analysis: AnalysisConfig
    taxonomy: TaxonomyConfig

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    def enabled_sources(self) -> dict[str, SourceEntry]:
        return {n: s for n, s in self.sources.sources.items() if s.enabled}

    def config_hash(self) -> str:
        """Hash of the YAML configuration, for the run manifest.

        Secrets are excluded: the manifest records ``author_salt_id``, never a
        secret value, and a config hash that moved when a key was added would
        leak the presence of credentials into a published artifact.
        """
        from src.core.hashing import content_equivalence_hash

        return content_equivalence_hash(
            {
                "sources": self.sources.model_dump(mode="json"),
                "models": self.models.model_dump(mode="json"),
                "analysis": self.analysis.model_dump(mode="json"),
                "taxonomy": self.taxonomy.model_dump(mode="json"),
            }
        )


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"configuration file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path.name} is not valid YAML: {exc}") from exc
    if raw is None:
        raise ConfigError(f"{path.name} is empty")
    if not isinstance(raw, dict):
        raise ConfigError(
            f"{path.name} must contain a mapping at the top level, "
            f"got {type(raw).__name__}"
        )
    return raw


def _parse(model: type[BaseModel], data: dict[str, Any], filename: str) -> Any:
    """Validate ``data`` against ``model``, reporting failures as ConfigError."""
    try:
        return model.model_validate(data)
    except PydanticError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}"
            for e in exc.errors()
        )
        raise ConfigError(f"{filename} is invalid — {details}") from exc


def load_settings(
    config_dir: Path | str | None = None,
    *,
    env_file: Path | str | None = None,
    project_root: Path | str | None = None,
) -> Settings:
    """Load and validate configuration. Raises ``ConfigError`` on any problem.

    Arguments exist for tests; production callers use :func:`get_settings`.
    """
    cfg_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    root = Path(project_root) if project_root else PROJECT_ROOT

    if not cfg_dir.is_dir():
        raise ConfigError(f"configuration directory not found: {cfg_dir}")

    secrets = (
        Secrets(_env_file=str(env_file))  # type: ignore[call-arg]
        if env_file is not None
        else Secrets()
    )

    sources = _parse(
        SourcesConfig, _load_yaml(cfg_dir / "sources.yaml"), "sources.yaml"
    )
    models = _parse(ModelsConfig, _load_yaml(cfg_dir / "models.yaml"), "models.yaml")
    analysis = _parse(
        AnalysisConfig, _load_yaml(cfg_dir / "analysis.yaml"), "analysis.yaml"
    )
    taxonomy = _parse(
        TaxonomyConfig, _load_yaml(cfg_dir / "taxonomy.yaml"), "taxonomy.yaml"
    )

    if taxonomy.version == TAXONOMY_VERSION and taxonomy.clusters:
        raise ConfigError(
            f"taxonomy.yaml declares version '{TAXONOMY_VERSION}' but defines "
            f"{len(taxonomy.clusters)} cluster(s). Clusters must not exist "
            f"before the pilot review (spec Section 20, invariant I10); bump the "
            f"version when the taxonomy is derived."
        )

    return Settings(
        project_root=root,
        config_dir=cfg_dir,
        secrets=secrets,
        sources=sources,
        models=models,
        analysis=analysis,
        taxonomy=taxonomy,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings for production callers."""
    return load_settings()


def reset_settings_cache() -> None:
    """Clear the cache. Used by tests that load alternate configurations."""
    get_settings.cache_clear()


def env_snapshot() -> dict[str, bool]:
    """Which known credentials are present, as booleans — never values.

    The one other place a module may legitimately want to know about the
    environment. Returning presence rather than content means this can be logged
    or put in a manifest without leaking a secret.
    """
    return {
        name: bool(os.environ.get(name))
        for name in (
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "GROQ_API_KEY",
            "AUTHOR_SALT",
            "REDDIT_CLIENT_ID",
            "REDDIT_CLIENT_SECRET",
            "YOUTUBE_API_KEY",
        )
    }
