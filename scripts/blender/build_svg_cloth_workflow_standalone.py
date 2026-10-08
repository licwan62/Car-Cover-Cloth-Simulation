"""Refresh embedded dependencies in svg_cloth_workflow.py.

This is a repository maintenance tool, not a Blender script. Run it whenever
remesh.py, generate_sewing.py, or cloth.py changes (cloth.py carries the
shared CC mark overlay used for seam marks).
"""

import base64
from pathlib import Path
import re
import sys
import zlib


ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "svg_cloth_workflow.py"
DEPENDENCIES = {
    "remesh.py": "__REMESH_PAYLOAD__",
    "generate_sewing.py": "__SEWING_PAYLOAD__",
    "setup_cloth.py": "__CLOTH_PAYLOAD__",
}


def encode(filepath):
    # Normalize line endings so the payload does not depend on the checkout.
    source = filepath.read_bytes().replace(b"\r\n", b"\n")
    return base64.b85encode(zlib.compress(source, level=9)).decode("ascii")


def main():
    if "bpy" in sys.modules:
        raise RuntimeError(
            "build_svg_cloth_workflow_standalone.py 是仓库维护工具，请在命令行用 "
            "python 运行；在 Blender 中应运行 svg_cloth_workflow.py。"
        )
    source = TARGET.read_text(encoding="utf-8")
    for filename, initial_placeholder in DEPENDENCIES.items():
        source_name = "cloth.py" if filename == "setup_cloth.py" else filename
        payload = encode(ROOT / source_name)
        pattern = rf'("{re.escape(filename)}": ")([^"\r\n]*)(")'
        source, count = re.subn(pattern, rf"\g<1>{payload}\g<3>", source, count=1)
        if count != 1:
            raise RuntimeError(f"Cannot find embedded payload slot for {filename}")
    TARGET.write_text(source, encoding="utf-8", newline="\n")
    print(f"Updated embedded scripts in {TARGET}")


if __name__ == "__main__":
    main()
