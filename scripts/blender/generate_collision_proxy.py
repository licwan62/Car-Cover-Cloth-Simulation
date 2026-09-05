"""Config-driven entry point for vehicle Collision Proxy generation.

Run this file from its project path. For a script that can be pasted into a
.blend Text block without local imports or JSON, use
generate_collision_proxy_standalone.py instead.
"""

from pathlib import Path
import importlib
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_collision_proxy_standalone as proxy_generator
from project_config import load_simulation_config


def main():
    # Blender keeps imported modules alive between Text Editor runs. Reload the
    # implementation so edits are not masked by a stale in-memory module.
    importlib.reload(proxy_generator)
    config = load_simulation_config()["collision_proxy"]
    proxy_generator.configure_from_mapping(config)
    return proxy_generator.main()


if __name__ == "__main__":
    main()
