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
        source = (ROOT / "scripts" / "blender" / "mirror_markers.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("project_config", source)
        self.assertNotIn("simulation.json", source)
        self.assertIn("apply_mirror_markers", source)
        self.assertIn("invoke_props_dialog", source)
        self.assertIn("launch_marker_dialog", source)

    def test_marks_do_not_add_physics_or_geometry_modifiers(self):
        source = (ROOT / "scripts" / "blender" / "mirror_markers.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("modifiers.new", source)
        self.assertNotIn("polygons.add", source)
        self.assertNotIn("vertices.add", source)
        self.assertIn("_mark_base_slot", source)


class SharedMarkBlockTests(unittest.TestCase):
    """Standalone scripts embed copies of the shared blocks; keep them in sync."""

    BLOCKS = {
        "CC MARK OVERLAY": (
            "mirror_markers.py", "door_maker.py", "plates_maker.py",
            "cloth.py", "cloth_fit_test.py",
        ),
        "CC SEAM MARK": ("cloth.py", "cloth_fit_test.py"),
    }

    @staticmethod
    def _block(filename, marker):
        source = (ROOT / "scripts" / "blender" / filename).read_text(encoding="utf-8")
        start = source.index(f"# >>> {marker} >>>")
        end = source.index(f"# <<< {marker} <<<")
        return source[start:end]

    def test_blocks_are_identical(self):
        for marker, filenames in self.BLOCKS.items():
            reference = self._block(filenames[0], marker)
            for filename in filenames[1:]:
                with self.subTest(marker=marker, filename=filename):
                    self.assertEqual(self._block(filename, marker), reference)

    def test_workflow_embeds_current_cloth_script(self):
        import base64
        import re
        import zlib

        workflow = (ROOT / "scripts" / "blender" / "svg_cloth_workflow.py").read_text(
            encoding="utf-8"
        )
        payload = re.search(r'"setup_cloth.py": "([^"]*)"', workflow).group(1)
        embedded = zlib.decompress(base64.b85decode(payload))
        current = (ROOT / "scripts" / "blender" / "cloth.py").read_bytes()
        self.assertEqual(embedded, current.replace(b"\r\n", b"\n"))


if __name__ == "__main__":
    unittest.main()
