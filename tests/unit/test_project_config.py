from __future__ import annotations

import json
import ast
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_MODULES = PROJECT_ROOT / "scripts" / "modules"
sys.path.insert(0, str(SHARED_MODULES))

from project_config import (  # noqa: E402
    load_cloth_preset,
    load_fit_thresholds,
    load_simulation_config,
)


class ProjectConfigTests(unittest.TestCase):
    def test_all_json_files_are_valid_objects(self) -> None:
        for path in (PROJECT_ROOT / "config").rglob("*.json"):
            with self.subTest(path=path):
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(value, dict)
                self.assertEqual(value["schema_version"], 1)

    def test_standard_mesh_edge_is_50_mm(self) -> None:
        cloth = load_cloth_preset()
        simulation = load_simulation_config()
        self.assertEqual(cloth["mesh_edge_target_mm"], 50.0)
        self.assertEqual(simulation["cloth_mesh"]["target_edge_mm"], 50.0)

    def test_sewing_force_is_bounded(self) -> None:
        cloth = load_cloth_preset()
        force = cloth["sewing"]["max_force"]
        self.assertGreater(force, 0.0)
        self.assertLessEqual(force, 15.0)

    def test_smooth_drape_profile_limits_fine_wrinkle_bias(self) -> None:
        cloth = load_cloth_preset()
        self.assertEqual(cloth["preset"], "Oxford_210D_SmoothDrape_V2")
        self.assertLessEqual(cloth["stiffness"]["compression"], 30.0)
        self.assertLessEqual(cloth["stiffness"]["shear"], 30.0)
        self.assertGreaterEqual(cloth["stiffness"]["bending"], 8.0)
        self.assertGreaterEqual(cloth["damping"]["bending"], 5.0)
        self.assertTrue(cloth["display"]["shade_smooth"])

    def test_standalone_denim_preset_is_self_contained(self) -> None:
        cloth = load_cloth_preset()
        path = PROJECT_ROOT / "scripts" / "blender" / "003_cloth_setup.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported_modules = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertEqual(imported_modules, {"bpy", "re"})
        self.assertNotIn("project_config", source)
        self.assertNotIn(".keyframe_insert(", source)
        self.assertIn("bpy.app.handlers.frame_change_pre", source)
        self.assertIn('field.type = "WIND"', source)
        self.assertIn("animate_field_strength(", source)
        self.assertIn('base_target.driver_add("value")', source)
        self.assertIn('level_target.driver_add("value")', source)
        self.assertIn("remove_v24_hem_grab_artifacts(", source)
        self.assertIn("HEM Pin OFF; collision/slide remain active", source)
        self.assertIn("settings.use_dynamic_mesh = True", source)
        self.assertIn('driver_add("pin_stiffness")', source)
        self.assertIn(
            "effector_weights.force = 1.0 if ENABLE_STAGED_EXPANSION else 0.0",
            source,
        )
        self.assertNotIn('obj["car_cover_rear_drag_schedule"] = True', source)

        constants = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    constants[target.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass

        self.assertEqual(constants["PRESET_NAME"], "CarCover_Simplified_50F_V29")
        self.assertEqual(constants["SIMULATION_END_OFFSET"], 49)
        self.assertFalse(constants["ENABLE_HEM_LEVEL_FEEDBACK"])
        self.assertFalse(constants["ENABLE_HEM_DRAG"])
        self.assertTrue(constants["ENABLE_POST_CLOTH_SEAM_WELD"])
        self.assertTrue(constants["ENABLE_SELF_COLLISION"])
        self.assertTrue(constants["ENABLE_OBJECT_COLLISION"])

    def test_fit_thresholds_remain_marked_for_calibration(self) -> None:
        thresholds = load_fit_thresholds()
        self.assertTrue(thresholds["calibration_required"])
        self.assertEqual(
            thresholds["thresholds"]["max_stretch"]["pass_max_ratio"],
            0.03,
        )


if __name__ == "__main__":
    unittest.main()
