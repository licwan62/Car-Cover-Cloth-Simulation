"""Exercise the feedback controller without requiring Blender."""

import ast
from pathlib import Path
import unittest


class HemHeightFeedbackTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / "scripts/blender/setup_cloth_standalone.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {"HEM_EQUAL_HEIGHT_TOLERANCE_MM", "HEM_HEIGHT_FEEDBACK_GAIN",
                 "MAX_HEM_FRONT_EXTRA_MM"}
        nodes = [node for node in tree.body if
                 (isinstance(node, ast.FunctionDef) and node.name == "hem_front_extra_mm")
                 or (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                     and node.targets[0].id in names)]
        namespace = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
        self.adjust = namespace["hem_front_extra_mm"]

    def test_aligned_hem_retains_correction(self):
        for gap in (-20, 0, 20):
            self.assertEqual(self.adjust(40, gap), 40)

    def test_high_front_adds_bounded_pull(self):
        self.assertEqual(self.adjust(0, 120), 50)
        self.assertEqual(self.adjust(240, 120), 250)

    def test_overshoot_releases_only_extra_pull(self):
        self.assertEqual(self.adjust(80, -100), 40)
        self.assertEqual(self.adjust(0, -100), 0)


if __name__ == "__main__":
    unittest.main()
