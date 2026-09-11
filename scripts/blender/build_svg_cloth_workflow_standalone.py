"""Refresh embedded dependencies in svg_cloth_workflow.py.

This is a repository maintenance tool, not a Blender script. Run it whenever
remesh.py, generate_sewing.py, or setup_cloth.py changes.
"""

import base64
from pathlib import Path
import re
import zlib


ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "svg_cloth_workflow.py"
DEPENDENCIES = {
    "remesh.py": "__REMESH_PAYLOAD__",
    "generate_sewing.py": "__SEWING_PAYLOAD__",
    "setup_cloth.py": "__CLOTH_PAYLOAD__",
}


def encode(filepath):
    return base64.b85encode(zlib.compress(filepath.read_bytes(), level=9)).decode("ascii")


def main():
    source = TARGET.read_text(encoding="utf-8")
    for filename, initial_placeholder in DEPENDENCIES.items():
        payload = encode(ROOT / filename)
        pattern = rf'("{re.escape(filename)}": ")([^"\r\n]*)(")'
        source, count = re.subn(pattern, rf"\g<1>{payload}\g<3>", source, count=1)
        if count != 1:
            raise RuntimeError(f"Cannot find embedded payload slot for {filename}")
    TARGET.write_text(source, encoding="utf-8", newline="\n")
    print(f"Updated embedded scripts in {TARGET}")


if __name__ == "__main__":
    main()
