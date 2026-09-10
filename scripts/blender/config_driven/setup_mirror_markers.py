"""Config-driven entry point for non-physical mirror-position marks."""

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

PROJECT_ROOT = SCRIPT_DIR.parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_config import load_json
from scripts.blender.setup_mirror_markers import apply_mirror_markers


CONFIG = load_json("simulation.json")["mirror_markers"]


if __name__ == "__main__":
    apply_mirror_markers(config=CONFIG)
