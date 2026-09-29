"""Config-driven entry point for non-physical mirror-position marks."""

from pathlib import Path
import sys


# Shared helpers live in scripts/modules, which Blender puts on sys.path once
# the project's scripts folder is listed in Preferences > File Paths > Script
# Directories. The fallback serves `blender --factory-startup --python <file>`.
try:
    import project_config  # noqa: F401
except ImportError:
    MODULES_DIR = Path(__file__).resolve().parent.parent.parent / "modules"
    if not (MODULES_DIR / "project_config.py").is_file():
        raise ImportError(
            "project_config not found. Add <project>/scripts to Blender "
            "Preferences > File Paths > Script Directories and restart Blender."
        ) from None
    sys.path.append(str(MODULES_DIR))

from project_config import load_blender_script, load_json


CONFIG = load_json("simulation.json")["mirror_markers"]


if __name__ == "__main__":
    # Reuse the standalone implementation with the project JSON settings.
    marker_impl = load_blender_script("100_mirror_marks.py")
    marker_impl.apply_mirror_markers(config=CONFIG)
