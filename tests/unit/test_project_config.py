from __future__ import annotations

import json
import ast
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLENDER_SCRIPTS = PROJECT_ROOT / "scripts" / "blender" / "config_driven"
sys.path.insert(0, str(BLENDER_SCRIPTS))

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
        path = PROJECT_ROOT / "scripts" / "blender" / "setup_cloth.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported_modules = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertEqual(imported_modules, {"bpy"})
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

        self.assertEqual(constants["PRESET_NAME"], "CarCover_HemFeedback_75F_V28")
        self.assertEqual(constants["SIMULATION_END_OFFSET"], 74)
        self.assertTrue(constants["ENABLE_HEM_LEVEL_FEEDBACK"])
        self.assertFalse(constants["ENABLE_HEM_DRAG"])
        self.assertTrue(constants["ENABLE_POST_CLOTH_SEAM_WELD"])
        self.assertLess(constants["ROOF_PIN_RELEASE_END"], constants["HEM_FEEDBACK_START"])
        self.assertLess(constants["HEM_FEEDBACK_START"] + constants["HEM_FEEDBACK_RAMP"],
                        constants["SIMULATION_END_OFFSET"])
        self.assertGreater(constants["HEM_LEVEL_PIN_WEIGHT"], 0)
        self.assertLess(constants["HEM_LEVEL_PIN_WEIGHT"], 1)
        self.assertTrue(constants["ENABLE_SELF_COLLISION"])
        self.assertTrue(constants["ENABLE_OBJECT_COLLISION"])

    def test_collision_proxy_config_and_standalone_match(self) -> None:
        simulation = load_simulation_config()
        config = simulation["collision_proxy"]
        path = (
            PROJECT_ROOT
            / "scripts"
            / "blender"
            / "generate_collision_proxy.py"
        )
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported_modules = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_from = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertEqual(imported_modules, {"bmesh", "bpy"})
        self.assertEqual(imported_from, set())
        self.assertNotIn("project_config", source)
        self.assertNotIn("load_simulation_config", source)

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

        self.assertEqual(constants["PRESET_NAME"], config["preset"])
        self.assertEqual(
            constants["PROXY_COLLECTION_NAME"],
            config["collection_name"],
        )
        self.assertEqual(constants["VOXEL_SIZE_MM"], config["voxel_size_mm"])
        self.assertEqual(
            constants["ENABLE_VOXEL_REMESH"],
            config["use_voxel_remesh"],
        )
        self.assertEqual(
            constants["REMOVE_DISCONNECTED_COMPONENTS"],
            config["remove_disconnected_components"],
        )
        self.assertEqual(
            constants["TARGET_FACE_RANGE"],
            tuple(config["target_faces"]),
        )
        self.assertEqual(
            constants["TARGET_FACE_COUNT"],
            config["target_face_count"],
        )
        self.assertEqual(
            constants["MAX_FINAL_FACE_COUNT"],
            config["max_final_face_count"],
        )
        self.assertEqual(
            constants["ENABLE_PLANAR_DISSOLVE"],
            config["planar_dissolve"],
        )
        self.assertEqual(
            constants["PLANAR_DISSOLVE_ANGLE_DEG"],
            config["planar_angle_deg"],
        )
        self.assertEqual(constants["SMOOTH_METHOD"], config["smooth_method"])
        self.assertEqual(
            constants["SMOOTH_VOLUME_PRESERVE"],
            config["smooth_volume_preserve"],
        )
        self.assertEqual(
            constants["PRESERVE_SOURCE_BOUNDS"],
            config["preserve_source_bounds"],
        )
        self.assertEqual(
            constants["MAX_BOUNDS_ERROR_MM"],
            config["max_bounds_error_mm"],
        )
        self.assertEqual(
            constants["ENABLE_THIN_OVERHANG_SUPPORT"],
            config["thin_overhang_support"]["enabled"],
        )
        self.assertEqual(
            constants["THIN_OVERHANG_MAX_THICKNESS_MM"],
            config["thin_overhang_support"]["max_thickness_mm"],
        )
        self.assertEqual(
            constants["THIN_OVERHANG_MIN_HORIZONTAL_SPAN_MM"],
            config["thin_overhang_support"]["min_horizontal_span_mm"],
        )
        self.assertEqual(
            constants["THIN_OVERHANG_MIN_HEIGHT_RATIO"],
            config["thin_overhang_support"]["min_height_ratio"],
        )
        self.assertEqual(
            constants["THIN_OVERHANG_SUPPORT_DROP_MM"],
            config["thin_overhang_support"]["support_drop_mm"],
        )
        self.assertEqual(
            constants["THIN_OVERHANG_MAX_LENGTH_RATIO"],
            config["thin_overhang_support"]["max_length_ratio"],
        )
        self.assertEqual(
            constants["THIN_OVERHANG_MIN_WIDTH_RATIO"],
            config["thin_overhang_support"]["min_width_ratio"],
        )
        self.assertEqual(
            constants["THIN_OVERHANG_MIN_END_RATIO"],
            config["thin_overhang_support"]["min_end_ratio"],
        )
        self.assertEqual(
            constants["THIN_OVERHANG_MIN_ASPECT_RATIO"],
            config["thin_overhang_support"]["min_aspect_ratio"],
        )
        self.assertEqual(
            constants["ENABLE_LOWER_BODY_INSET"],
            config["lower_body_inset"]["enabled"],
        )
        self.assertEqual(
            constants["LOWER_BODY_INSET_MM"],
            config["lower_body_inset"]["distance_mm"],
        )
        self.assertEqual(
            constants["COLLISION_THICKNESS_MM"],
            config["thickness_mm"],
        )
        self.assertEqual(
            constants["COLLISION_FRICTION"],
            config["friction"],
        )

    def test_fit_thresholds_remain_marked_for_calibration(self) -> None:
        thresholds = load_fit_thresholds()
        self.assertTrue(thresholds["calibration_required"])
        self.assertEqual(
            thresholds["thresholds"]["max_stretch"]["pass_max_ratio"],
            0.03,
        )


if __name__ == "__main__":
    unittest.main()
