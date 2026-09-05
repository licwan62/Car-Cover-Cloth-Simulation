from __future__ import annotations

import ast
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class CollisionShellScriptTests(unittest.TestCase):
    def test_two_stage_shell_script_is_standalone_and_guarded(self) -> None:
        path = (
            PROJECT_ROOT
            / "scripts"
            / "blender"
            / "generate_collision_shell_standalone.py"
        )
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported_modules = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertEqual(imported_modules, {"bmesh", "bpy"})
        self.assertNotIn("project_config", source)
        self.assertGreaterEqual(source.count("apply_voxel_remesh("), 3)
        self.assertIn("keep_largest_surface_component(", source)
        self.assertIn("inspect_watertight_mesh(", source)
        self.assertIn("capture_top_surface_samples(", source)
        self.assertIn("measure_top_surface_damage(", source)
        self.assertIn("apply_thin_surface_protection(", source)
        self.assertIn('type="SOLIDIFY"', source)
        self.assertIn('type="COLLISION"', source)
        self.assertIn("settings.use_culling = COLLISION_USE_CULLING", source)

        constants = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            try:
                constants[target.id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass

        self.assertEqual(
            constants["PRESET_NAME"],
            "CarCover_TwoStageOuterShell_TEST_V2",
        )
        self.assertLess(
            constants["OUTER_SHELL_VOXEL_MM"],
            constants["COLLISION_VOXEL_MM"],
        )
        self.assertEqual(constants["TARGET_TRIANGLES"], 6000)
        self.assertLessEqual(
            constants["TARGET_TRIANGLES"],
            constants["MAX_TRIANGLES"],
        )
        self.assertTrue(constants["PRESERVE_SOURCE_BOUNDS"])
        self.assertTrue(constants["ENABLE_THIN_SURFACE_REPAIR"])
        self.assertGreater(
            constants["THIN_SURFACE_PROTECTION_MM"],
            constants["COLLISION_VOXEL_MM"],
        )
        self.assertLess(
            constants["MAX_TOP_SURFACE_DAMAGE_FRACTION"],
            0.05,
        )
        self.assertFalse(constants["COLLISION_USE_CULLING"])
        self.assertEqual(constants["COLLISION_FRICTION"], 3.0)


if __name__ == "__main__":
    unittest.main()
