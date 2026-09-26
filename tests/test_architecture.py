"""Import-boundary enforcement (ARCHITECTURE Section 17.1, invariants I5 and I8).

Layering that is only documented erodes; layering that fails a test does not.

These checks parse source with ``ast`` rather than importing modules. Importing to
inspect dependencies would execute module-level code and, worse, would make the
test pass or fail depending on what happens to be installed — an absent
``anthropic`` package would look like compliance.

Phase 0 asserted the two boundary rules the plan lists for that phase, plus the
no-Streamlit rule that the no-key guarantee depends on. Phase 1 adds the two edges
that appear with ``src/models`` and ``src/extract``: contracts depend only on
``core``, and the validator depends only on ``core`` and the contracts. Later
phases extend this file as the packages they constrain come into existence.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"

#: Provider SDKs. Only ``src/llm/providers/`` may import these (Phase 4 onward);
#: everything else goes through the gateway, which is what keeps the deterministic
#: path free of a hard dependency on a vendor package.
PROVIDER_SDKS = frozenset({"anthropic", "openai", "cohere", "google.generativeai"})

#: Presentation-only dependencies. No module under ``src/`` may import these: the
#: pipeline must run headless, and ``app.py`` is the only Streamlit entry point.
UI_PACKAGES = frozenset({"streamlit"})


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_modules(path: Path) -> set[str]:
    """Top-level module paths imported by ``path``.

    Relative imports are resolved to their package so ``from .errors import X``
    inside ``src/core`` reports as ``src.core.errors``.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package_parts = path.relative_to(PROJECT_ROOT).parent.parts
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(package_parts[: len(package_parts) - node.level + 1])
                if node.module:
                    base.append(node.module)
                found.add(".".join(base))
            elif node.module:
                found.add(node.module)

    return found


def _is_internal(module: str) -> bool:
    return module == "src" or module.startswith("src.")


def _all_src_files() -> list[Path]:
    files = _python_files(SRC)
    assert files, "expected Python files under src/"
    return files


def _module_label(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT).as_posix())


# --------------------------------------------------------------------------- #
# Rule 1 — core imports nothing internal outside itself
# --------------------------------------------------------------------------- #


def test_core_imports_nothing_internal_outside_core() -> None:
    """``core`` is the bottom of the stack: everything imports it, it imports none.

    Intra-package imports (``src.core.errors`` from ``src.core.config``) are
    allowed; a dependency on ``src.models``, ``src.store``, or any stage is not.
    A single such edge would make the layering circular and would mean importing
    configuration pulls in the schema.
    """
    offenders: list[str] = []

    for path in _python_files(SRC / "core"):
        for module in _imported_modules(path):
            if _is_internal(module) and not module.startswith("src.core"):
                offenders.append(f"{_module_label(path)} imports {module}")

    assert not offenders, "core must not import other internal packages:\n" + "\n".join(
        offenders
    )


def test_core_modules_exist() -> None:
    """Guards against the boundary tests passing vacuously on an empty package."""
    expected = {"config.py", "errors.py", "hashing.py", "ids.py", "logging.py",
                "versions.py"}
    present = {p.name for p in _python_files(SRC / "core")}
    assert expected <= present, f"missing from src/core: {sorted(expected - present)}"


# --------------------------------------------------------------------------- #
# Rule 2 — no provider SDK outside src/llm/providers/
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", _all_src_files(), ids=_module_label)
def test_no_module_imports_a_provider_sdk(path: Path) -> None:
    """Provider SDKs live behind the gateway (ADR-4), so the deterministic path
    never depends on a vendor package being installed."""
    allowed = Path("src") / "llm" / "providers"
    if allowed in path.relative_to(PROJECT_ROOT).parents:
        pytest.skip("src/llm/providers/ is the designated adapter location")

    leaked = {
        module
        for module in _imported_modules(path)
        if module.split(".")[0] in {sdk.split(".")[0] for sdk in PROVIDER_SDKS}
    }
    assert not leaked, f"{_module_label(path)} imports provider SDK(s) {sorted(leaked)}"


@pytest.mark.parametrize("path", _all_src_files(), ids=_module_label)
def test_no_module_under_src_imports_streamlit(path: Path) -> None:
    """The pipeline runs headless; ``app.py`` is the only Streamlit entry point."""
    leaked = {
        module
        for module in _imported_modules(path)
        if module.split(".")[0] in UI_PACKAGES
    }
    assert not leaked, f"{_module_label(path)} imports {sorted(leaked)}"


# --------------------------------------------------------------------------- #
# Rule 3 — only core reads the environment
# --------------------------------------------------------------------------- #


def test_only_core_config_reads_the_environment() -> None:
    """One module owns the environment (ARCHITECTURE 16.1).

    A stray ``os.environ`` read elsewhere is how an undocumented setting appears
    that is absent from ``.env.example`` and from the manifest.
    """
    allowed = {Path("src/core/config.py")}
    offenders: list[str] = []

    for path in _all_src_files():
        relative = path.relative_to(PROJECT_ROOT)
        if relative in allowed:
            continue

        source = path.read_text(encoding="utf-8")
        for marker in ("os.environ", "os.getenv", "getenv("):
            if marker in source:
                offenders.append(f"{relative.as_posix()} uses {marker}")

    assert not offenders, "only src/core/config.py may read the environment:\n" + (
        "\n".join(offenders)
    )


# --------------------------------------------------------------------------- #
# Rule 4 — contracts depend on core alone (Phase 1)
# --------------------------------------------------------------------------- #


def test_models_import_only_core_and_other_models() -> None:
    """``models`` sits directly above ``core`` and below every stage.

    A contract that imported a stage would invert the dependency that invariant
    I11 rests on: the schema would then need the pipeline in order to describe
    itself, and Phase 2's importer could no longer be finished without Phase 3.
    """
    allowed = ("src.core", "src.models")
    offenders = [
        f"{_module_label(path)} imports {module}"
        for path in _python_files(SRC / "models")
        for module in _imported_modules(path)
        if _is_internal(module) and not module.startswith(allowed)
    ]
    assert not offenders, "models may import only core:\n" + "\n".join(offenders)


def test_extract_imports_only_core_models_and_itself() -> None:
    """The validator reads contracts and the evidence map, and nothing else.

    In particular it must not reach the store or a provider: validation is a pure
    function of a record, its spans, and the document text, which is what lets it
    be called from the store layer without a cycle.
    """
    allowed = ("src.core", "src.models", "src.extract")
    offenders = [
        f"{_module_label(path)} imports {module}"
        for path in _python_files(SRC / "extract")
        for module in _imported_modules(path)
        if _is_internal(module) and not module.startswith(allowed)
    ]
    assert not offenders, "extract may import only core and models:\n" + "\n".join(
        offenders
    )


def test_phase_1_packages_exist() -> None:
    """Guards the two rules above against passing vacuously."""
    assert (SRC / "models" / "enums.py").exists()
    assert (SRC / "models" / "evidence_map.py").exists()
    assert (SRC / "extract" / "validator.py").exists()


# --------------------------------------------------------------------------- #
# Phase scope — nothing from a later phase exists yet
# --------------------------------------------------------------------------- #


def test_no_later_phase_packages_exist_yet() -> None:
    """Phase 2 adds ``src/collect`` and nothing after it.

    Spec Section 29.4: one phase at a time. ``src/relevance`` is the Phase 4
    classifier package and is unrelated to ``src/models/relevance.py``, which is
    the contract. ``src/collect`` is the manual-import package this phase is
    allowed to create; the names below are still later work.
    """
    premature = [
        name
        for name in ("normalize", "dedupe", "relevance",
                     "llm", "taxonomy", "analyze", "retrieve",
                     "review", "pipeline", "store")
        if (SRC / name).exists()
    ]
    assert not premature, f"these belong to later phases: {premature}"


def test_collect_imports_only_core_models_and_itself() -> None:
    """The importer must be finishable with no Phase 3 module on its path.

    Normalization, dedupe, and the store are exactly the dependencies manual
    import is not allowed to grow. A single import of one of them would make
    ``CollectedDocument`` depend on a stage that does not exist yet.
    """
    assert (SRC / "collect" / "workbook.py").exists()
    allowed = ("src.core", "src.models", "src.collect")
    offenders = [
        f"{_module_label(path)} imports {module}"
        for path in _python_files(SRC / "collect")
        for module in _imported_modules(path)
        if _is_internal(module) and not module.startswith(allowed)
    ]
    assert not offenders, "collect may import only core and models:\n" + "\n".join(
        offenders
    )


def test_extract_holds_only_the_validator_so_far() -> None:
    """``prompts.py`` and ``extractor.py`` are Phase 5: the gate is built before
    the thing it gates, so validation cannot be relaxed to let output through."""
    present = {p.name for p in _python_files(SRC / "extract")}
    assert present == {"__init__.py", "validator.py"}, sorted(present)


def test_no_streamlit_app_exists_yet() -> None:
    """``app.py`` is Phase 10."""
    assert not (PROJECT_ROOT / "app.py").exists()


def test_prototype_is_outside_the_package_boundary() -> None:
    """``prototype/`` is read-only reference; nothing may import from it (ADR-9)."""
    assert (PROJECT_ROOT / "prototype").is_dir()

    offenders = [
        _module_label(path)
        for path in _all_src_files()
        if any(m.split(".")[0] == "prototype" for m in _imported_modules(path))
    ]
    assert not offenders, f"these import from prototype/: {offenders}"


def test_every_src_file_parses() -> None:
    for path in _all_src_files():
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
