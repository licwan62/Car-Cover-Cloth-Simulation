"""Project configuration helpers that can be tested outside Blender.

This module lives in ``scripts/modules``. When ``scripts`` is added to
Blender's Preferences > File Paths > Script Directories, Blender puts
``scripts/modules`` on ``sys.path`` and ``import project_config`` works from any
Text Editor block, regardless of the misleading ``__file__`` Blender assigns to
text blocks.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = PROJECT_ROOT / "config"
BLENDER_SCRIPTS = PROJECT_ROOT / "scripts" / "blender"


def load_blender_script(filename: str) -> ModuleType:
    """Load ``scripts/blender/<filename>`` as a fresh module.

    Numbered script names such as ``100_mirror_marks.py`` are not valid import
    names. Loading anew on every call also keeps Blender from reusing a stale
    module after the file is edited between Text Editor runs. The script's
    ``if __name__ == "__main__"`` block does not run.
    """

    path = BLENDER_SCRIPTS / filename
    module_name = "_cc_" + path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Blender script: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_json(relative_path: str | Path) -> dict[str, Any]:
    """Load a UTF-8 JSON object below the project config directory."""

    path = (CONFIG_ROOT / relative_path).resolve()
    if CONFIG_ROOT.resolve() not in path.parents:
        raise ValueError(f"Config path escapes config directory: {relative_path}")

    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)

    if not isinstance(value, dict):
        raise TypeError(f"Config root must be a JSON object: {path}")
    if value.get("schema_version") != 1:
        raise ValueError(f"Unsupported schema_version in {path}")
    return value


def load_cloth_preset() -> dict[str, Any]:
    return load_json(Path("cloth") / "oxford_210d.json")


def load_simulation_config() -> dict[str, Any]:
    return load_json("simulation.json")


def load_fit_thresholds() -> dict[str, Any]:
    return load_json("fit_thresholds.json")
