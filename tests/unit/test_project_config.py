from __future__ import annotations

import json
import ast
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLENDER_SCRIPTS = PROJECT_ROOT / "scripts" / "blender"
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
        path = PROJECT_ROOT / "scripts" / "blender" / "setup_cloth_standalone.py"
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

        self.assertEqual(
            constants["PRESET_NAME"],
            "Blender_Denim_HemLevel_50F_V26",
        )
        self.assertEqual(constants["MATERIAL_PRESET_NAME"], "Blender Default Denim")
        self.assertEqual(constants["SIMULATION_END_OFFSET"], 49)
        self.assertEqual(constants["QUALITY_STEPS"], 8)
        self.assertEqual(constants["MASS_PER_VERTEX"], 0.25)
        self.assertLessEqual(constants["TIME_SCALE"], 2.0)
        self.assertEqual(constants["BENDING_STIFFNESS"], 25.0)
        self.assertEqual(constants["BENDING_STIFFNESS_DURING_SEWING"], 18.0)
        self.assertGreater(constants["MAX_SEWING_FORCE"], cloth["sewing"]["max_force"])
        self.assertLessEqual(constants["MAX_SEWING_FORCE"], 40.0)
        self.assertFalse(constants["DISPLAY_SUBSURF_IN_VIEWPORT"])
        self.assertTrue(constants["ENABLE_POST_CLOTH_SEAM_WELD"])
        self.assertLess(
            constants["SEAM_WELD_DISTANCE_MM"],
            constants["MESH_EDGE_TARGET_MM"],
        )
        self.assertEqual(
            constants["SEAM_WELD_ENABLE_OFFSET"],
            constants["SEWING_RELEASE_END"] + 1,
        )
        self.assertTrue(constants["ABORT_ON_SEWING_HUBS"])
        self.assertEqual(constants["MAX_SEWING_CONNECTORS_PER_VERTEX"], 2)
        self.assertGreater(constants["SEWING_FORCE_START"], 0.0)
        self.assertLess(constants["SEWING_FORCE_START"], constants["MAX_SEWING_FORCE"])
        self.assertGreater(constants["SEWING_FORCE_SUSTAIN"], 0.0)
        self.assertLess(
            constants["SEWING_FORCE_SUSTAIN"],
            constants["MAX_SEWING_FORCE"],
        )
        self.assertGreater(constants["SEWING_GRAVITY_FACTOR"], 0.0)
        self.assertLess(
            constants["SELF_COLLISION_DISTANCE_MM"],
            cloth["self_collision"]["distance_mm"],
        )
        self.assertLessEqual(constants["OBJECT_COLLISION_FRICTION"], 0.2)
        self.assertLessEqual(constants["COLLIDER_SURFACE_FRICTION"], 3.0)
        self.assertNotIn("COLLISION_COLLECTION_NAME =", source)
        self.assertNotIn("ACTIVE_COLLISION_COLLECTION_NAME =", source)
        self.assertIn("for obj in scene.objects", source)
        self.assertIn('else "SCENE"', source)
        self.assertIn("当前场景没有带 Collision 修改器", source)
        self.assertTrue(constants["ENABLE_HEM_DRAG"])
        self.assertFalse(constants["ENABLE_REAR_DRAG"])
        self.assertEqual(constants["FRONT_DRAG_GROUP_NAME"], "HEM_FRONT")
        self.assertEqual(constants["REAR_DRAG_GROUP_NAME"], "HEM_REAR")
        self.assertEqual(constants["REAR_DRAG_PIN_GROUP_NAME"], "CC_REAR_DRAG_PIN")
        self.assertGreater(constants["REAR_DRAG_DISTANCE_MM"], 0.0)
        self.assertLessEqual(
            constants["REAR_DRAG_DISTANCE_MM"],
            constants["MAX_SAFE_REAR_DRAG_DISTANCE_MM"],
        )
        self.assertEqual(constants["REAR_DRAG_OUTWARD_MM"], 0.0)
        self.assertLessEqual(
            constants["REAR_DRAG_OUTWARD_MM"],
            constants["MAX_SAFE_REAR_DRAG_OUTWARD_MM"],
        )
        self.assertGreater(constants["REAR_DRAG_PIN_STIFFNESS"], 0.0)
        self.assertGreater(constants["REAR_DRAG_VERTEX_WEIGHT"], 0.0)
        self.assertLessEqual(constants["REAR_DRAG_VERTEX_WEIGHT"], 1.0)
        self.assertEqual(constants["REAR_DRAG_SUSTAIN_FACTOR"], 1.0)
        self.assertEqual(constants["REAR_DRAG_SUSTAIN_PIN_FACTOR"], 0.0)
        self.assertTrue(constants["REAR_DRAG_LEVEL_TO_LOWEST"])
        self.assertEqual(
            constants["HEM_DRAG_START"],
            constants["SEWING_RELEASE_END"],
        )
        self.assertLess(
            constants["HEM_DRAG_START"],
            constants["HEM_DRAG_END"],
        )
        self.assertEqual(
            constants["HEM_DRAG_SETTLE_END"],
            constants["SIMULATION_END_OFFSET"],
        )
        self.assertGreater(constants["HEM_TENSION_DISTANCE_MM"], 0.0)
        self.assertLessEqual(
            constants["HEM_TENSION_DISTANCE_MM"],
            constants["MAX_SAFE_HEM_TENSION_DISTANCE_MM"],
        )
        self.assertEqual(constants["HEM_LEVELING_BIAS_MM"], 30.0)
        self.assertEqual(constants["HEM_FRONT_TENSION_DISTANCE_MM"], 80.0)
        self.assertEqual(constants["HEM_REAR_TENSION_DISTANCE_MM"], 20.0)
        self.assertGreater(
            constants["HEM_FRONT_TENSION_DISTANCE_MM"],
            constants["HEM_REAR_TENSION_DISTANCE_MM"],
        )
        self.assertLessEqual(
            constants["HEM_FRONT_TENSION_DISTANCE_MM"],
            constants["MAX_SAFE_HEM_TENSION_DISTANCE_MM"],
        )
        self.assertGreaterEqual(constants["HEM_REAR_TENSION_DISTANCE_MM"], 0.0)
        self.assertLess(
            constants["HEM_DRAG_START"],
            constants["HEM_LEVEL_START"],
        )
        self.assertLess(
            constants["HEM_LEVEL_START"],
            constants["HEM_LEVEL_END"],
        )
        self.assertLessEqual(
            constants["HEM_LEVEL_END"],
            constants["HEM_DRAG_SETTLE_END"],
        )
        self.assertGreater(constants["REAR_DRAG_RELEASE_VERTEX_WEIGHT"], 0.0)
        self.assertLessEqual(constants["REAR_DRAG_RELEASE_VERTEX_WEIGHT"], 0.02)
        self.assertGreater(constants["EXPANSION_STRENGTH"], 0.0)
        self.assertLessEqual(constants["EXPANSION_STRENGTH"], 2.0)
        self.assertGreater(constants["EXPANSION_SUSTAIN_STRENGTH"], 0.0)
        self.assertLess(
            constants["EXPANSION_SUSTAIN_STRENGTH"],
            constants["EXPANSION_STRENGTH"],
        )
        self.assertTrue(constants["REQUIRE_PIN_FOR_EXPANSION"])
        self.assertFalse(constants["ENABLE_STAGED_EXPANSION"])
        self.assertEqual(constants["EXPANSION_FIELD_COUNT"], 5)
        self.assertGreater(constants["EXPANSION_FORCE_ABOVE_TOP_MM"], 0.0)
        self.assertGreaterEqual(constants["EXPANSION_AXIS_SPREAD"], 0.4)
        self.assertGreaterEqual(constants["EXPANSION_MAX_DISTANCE_MM"], 1500.0)
        self.assertTrue(constants["ENABLE_ROOF_PIN_DURING_SIMULATION"])
        self.assertFalse(constants["ENABLE_TOP_DOWN_GUIDE"])
        self.assertEqual(constants["TOP_PANEL_GROUP_NAMES"], ("PANEL_TOP", "TOP"))
        self.assertEqual(constants["TENSION_STIFFNESS"], 60.0)
        self.assertEqual(constants["COMPRESSION_STIFFNESS"], 50.0)
        self.assertEqual(constants["SHEAR_STIFFNESS"], 50.0)
        self.assertEqual(constants["TENSION_DAMPING"], 25.0)
        self.assertLess(
            constants["GRAVITY_RAMP_START"],
            constants["GRAVITY_RAMP_END"],
        )
        self.assertLess(
            constants["ROOF_PIN_HOLD_END"],
            constants["ROOF_PIN_RELEASE_END"],
        )
        self.assertLess(
            constants["HEM_DRAG_END"],
            constants["HEM_DRAG_SETTLE_END"],
        )

    def test_collision_proxy_config_and_standalone_match(self) -> None:
        simulation = load_simulation_config()
        config = simulation["collision_proxy"]
        path = (
            PROJECT_ROOT
            / "scripts"
            / "blender"
            / "generate_collision_proxy_standalone.py"
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
