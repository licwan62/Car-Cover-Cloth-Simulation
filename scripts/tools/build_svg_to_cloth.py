"""Refresh embedded dependencies in scripts/blender/000_svg_to_cloth.py.

This is a repository maintenance tool, not a Blender script. Run it with a
regular Python interpreter whenever 001_remesh.py, 002_sew_from_svg.py, or
003_cloth_setup.py changes (003_cloth_setup.py carries the shared CC mark
overlay used for seam marks).
"""

import base64
from pathlib import Path
import re
import sys
import zlib


BLENDER_SCRIPTS = Path(__file__).resolve().parents[1] / "blender"
TARGET = BLENDER_SCRIPTS / "000_svg_to_cloth.py"
DEPENDENCIES = ("001_remesh.py", "002_sew_from_svg.py", "003_cloth_setup.py")


def encode(filepath):
    source = filepath.read_bytes()
    return base64.b85encode(zlib.compress(source, level=9)).decode("ascii")


def main():
    if "bpy" in sys.modules:
        raise RuntimeError(
            "build_svg_to_cloth.py 是仓库维护工具，请在命令行用 "
            "python 运行；在 Blender 中应运行 000_svg_to_cloth.py。"
        )
    source = TARGET.read_text(encoding="utf-8")
    for filename in DEPENDENCIES:
        payload = encode(BLENDER_SCRIPTS / filename)
        pattern = rf'("{re.escape(filename)}": ")([^"\r\n]*)(")'
        source, count = re.subn(pattern, rf"\g<1>{payload}\g<3>", source, count=1)
        if count != 1:
            raise RuntimeError(f"Cannot find embedded payload slot for {filename}")
    TARGET.write_text(source, encoding="utf-8", newline="\n")
    print(f"Updated embedded scripts in {TARGET}")


if __name__ == "__main__":
    main()
