"""Config-driven entry point for non-physical mirror-position marks."""

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from project_config import load_json
from setup_mirror_markers_standalone import apply_mirror_markers


CONFIG = load_json("simulation.json")["mirror_markers"]


if __name__ == "__main__":
    apply_mirror_markers(config=CONFIG)
