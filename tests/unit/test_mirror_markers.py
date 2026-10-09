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
        source = (ROOT / "scripts" / "blender" / "100_mirror_marks.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("project_config", source)
        self.assertNotIn("simulation.json", source)
        self.assertIn("apply_mirror_markers", source)
        self.assertIn("invoke_props_dialog", source)
        self.assertIn("launch_marker_dialog", source)

    def test_marks_do_not_add_physics_or_geometry_modifiers(self):
        source = (ROOT / "scripts" / "blender" / "100_mirror_marks.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("modifiers.new", source)
        self.assertNotIn("polygons.add", source)
        self.assertNotIn("vertices.add", source)
        self.assertIn("_mark_base_slot", source)


class SharedMarkBlockTests(unittest.TestCase):
    """Numbered standalone scripts keep the embedded overlay block in sync."""

    FILENAMES = (
        "100_mirror_marks.py",
        "101_door_marks.py",
        "102_plate_marks.py",
        "003_cloth_setup.py",
    )

    @staticmethod
    def _block(filename):
        source = (ROOT / "scripts" / "blender" / filename).read_text(encoding="utf-8")
        start = source.index("# >>> CC MARK OVERLAY >>>")
        end = source.index("# <<< CC MARK OVERLAY <<<")
        return source[start:end]

    def test_blocks_are_identical(self):
        reference = self._block(self.FILENAMES[0])
        for filename in self.FILENAMES[1:]:
            with self.subTest(filename=filename):
                self.assertEqual(self._block(filename), reference)


if __name__ == "__main__":
    unittest.main()
