"""Project configuration helpers that can be tested outside Blender."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = PROJECT_ROOT / "config"


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
