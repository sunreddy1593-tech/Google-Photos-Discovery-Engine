"""Shared fixtures.

Note what these fixtures deliberately avoid: no fixture reads the developer's
real ``.env``. Configuration tests build their own config directory and point the
loader at an explicit env file, so the suite behaves identically on a machine with
credentials and on a fresh clone without them. A test that passes only because the
author happens to have an API key exported is not a test.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_CONFIG_DIR = PROJECT_ROOT / "config"


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def empty_env(tmp_path: Path) -> Path:
    """An env file that exists and sets nothing.

    Pointing the loader here proves configuration loads with every credential
    absent, which is the no-key guarantee (spec Sections 13.1, 22.3, 23).
    """
    path = tmp_path / "empty.env"
    path.write_text("# intentionally empty\n", encoding="utf-8")
    return path


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """A writable copy of the real ``config/`` directory.

    Copied rather than synthesized so the tests exercise the configuration the
    project actually ships. A test fixture that drifts from the real config can
    pass while the real config is broken.
    """
    destination = tmp_path / "config"
    shutil.copytree(REAL_CONFIG_DIR, destination)
    return destination
