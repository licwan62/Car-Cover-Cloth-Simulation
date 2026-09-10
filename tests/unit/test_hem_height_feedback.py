"""Exercise the feedback controller without requiring Blender."""

import ast
from pathlib import Path
import unittest


class HemHeightFeedbackTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / "scripts/blender/setup_cloth.py"
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


class PerVertexLevelTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / "scripts/blender/setup_cloth.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name == "hem_level_target_z"]
        namespace = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
        self.target = namespace["hem_level_target_z"]

    def test_all_corners_reach_one_plane(self):
        for height in (-0.2, -0.1, 0.1, 0.2):
            self.assertAlmostEqual(self.target(height, 0.05, 65, 45, 65), 0.05)
            self.assertAlmostEqual(self.target(height, 0.05, 75, 45, 65), 0.05)

    def test_before_acquisition_follows_free_drape(self):
        self.assertEqual(self.target(0.2, 0.05, 1, 45, 65), 0.2)
        self.assertEqual(self.target(0.2, 0.05, 45, 45, 65), 0.2)

    def test_midpoint_lifts_low_vertices_and_lowers_high_vertices(self):
        self.assertAlmostEqual(self.target(0.2, 0, 55, 45, 65), 0.1)
        self.assertAlmostEqual(self.target(-0.2, 0, 55, 45, 65), -0.1)


if __name__ == "__main__":
    unittest.main()
