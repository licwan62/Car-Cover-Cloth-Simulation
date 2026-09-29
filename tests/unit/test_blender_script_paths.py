from __future__ import annotations

import ast
import base64
from pathlib import Path
import re
import sys
import unittest
import zlib


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT_ROOT / "scripts"
BLENDER = SCRIPTS / "blender"
CONFIG_DRIVEN = BLENDER / "config_driven"
sys.path.insert(0, str(SCRIPTS / "modules"))

import project_config  # noqa: E402


SCRIPT_NAME = re.compile(r"^(?P<stage>\d{3})_[a-z0-9]+(?:_[a-z0-9]+)*\.py$")


class BlenderScriptPathTests(unittest.TestCase):
    """Blender Script Directories only search scripts/{modules,addons,startup}."""

    def test_shared_modules_live_in_blender_modules_directory(self) -> None:
        for name in ("project_config.py", "seam_naming.py"):
            with self.subTest(name=name):
                self.assertTrue((SCRIPTS / "modules" / name).is_file())
                self.assertFalse((CONFIG_DRIVEN / name).exists())

    def test_project_config_locates_repository_folders(self) -> None:
        self.assertEqual(project_config.PROJECT_ROOT, PROJECT_ROOT)
        self.assertEqual(project_config.BLENDER_SCRIPTS, BLENDER)
        self.assertTrue((project_config.CONFIG_ROOT / "simulation.json").is_file())

    def test_blender_scripts_use_unique_stage_numbers(self) -> None:
        # 0xx pipeline, 1xx marks, 2xx collision, 3xx export.
        for folder in (BLENDER, CONFIG_DRIVEN):
            stages = []
            for path in folder.glob("*.py"):
                with self.subTest(path=path.name):
                    match = SCRIPT_NAME.fullmatch(path.name)
                    self.assertIsNotNone(match)
                    stages.append(match["stage"])
            with self.subTest(folder=folder.name):
                self.assertEqual(len(stages), len(set(stages)))

    def test_config_driven_scripts_do_not_trust_text_block_file_dir(self) -> None:
        # Blender's Text Editor sets __file__ to "<blend path>/<text name>",
        # so the script's own directory is not a usable import root.
        for path in CONFIG_DRIVEN.glob("*.py"):
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("SCRIPT_DIR", source)
                self.assertNotIn("sys.path.insert(0", source)
                self.assertNotIn("scripts.blender", source)

    def test_config_driven_wrappers_load_existing_scripts(self) -> None:
        for path in CONFIG_DRIVEN.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "load_blender_script"
                ):
                    target = ast.literal_eval(node.args[0])
                    with self.subTest(path=path.name, target=target):
                        self.assertTrue((BLENDER / target).is_file())

    def test_standalone_workflow_embeds_current_sources(self) -> None:
        source = (BLENDER / "000_svg_to_cloth.py").read_text(encoding="utf-8")
        for filename in ("001_remesh.py", "002_sew_from_svg.py", "003_cloth_setup.py"):
            with self.subTest(source=filename):
                match = re.search(rf'"{re.escape(filename)}": "([^"\r\n]*)"', source)
                self.assertIsNotNone(match)
                embedded = zlib.decompress(base64.b85decode(match.group(1)))
                self.assertEqual(
                    embedded,
                    (BLENDER / filename).read_bytes(),
                    "Run: python scripts/tools/build_svg_to_cloth.py",
                )


if __name__ == "__main__":
    unittest.main()
