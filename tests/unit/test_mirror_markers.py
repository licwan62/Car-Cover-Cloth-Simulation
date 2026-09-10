import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class MirrorMarkerTests(unittest.TestCase):
    def test_artboard_one_dimensions_are_configured_in_mm(self):
        config = json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))
        markers = config["mirror_markers"]
        self.assertEqual(markers["reference"], "TESLA-MODELX.ai artboard 1")
        self.assertEqual(markers["mirror"]["distance_from_front_mm"], 1600.0)
        self.assertEqual(markers["mirror"]["height_from_bottom_mm"], 1020.0)
        self.assertEqual(markers["charge_port"]["distance_from_rear_mm"], 340.0)
        self.assertEqual(markers["charge_port"]["height_from_bottom_mm"], 820.0)
        self.assertIn(markers["front_axis"], {"+X", "-X", "+Y", "-Y"})

    def test_standalone_has_no_project_dependency(self):
        source = (ROOT / "scripts" / "blender" / "setup_mirror_markers.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("project_config", source)
        self.assertNotIn("simulation.json", source)
        self.assertIn("apply_mirror_markers", source)
        self.assertIn("invoke_props_dialog", source)
        self.assertIn("launch_marker_dialog", source)

    def test_marks_do_not_add_physics_or_geometry_modifiers(self):
        source = (ROOT / "scripts" / "blender" / "setup_mirror_markers.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("modifiers.new", source)
        self.assertNotIn("polygons.add", source)
        self.assertNotIn("vertices.add", source)
        self.assertIn("_ensure_base_slot", source)


if __name__ == "__main__":
    unittest.main()
