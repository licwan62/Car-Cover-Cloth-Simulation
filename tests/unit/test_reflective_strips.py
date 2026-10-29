import ast
import copy
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "blender" / "101_reflective_strips.py"


class _Vector:
    """Just enough of mathutils.Vector for the positioning helpers."""

    def __init__(self, values):
        self.values = [float(value) for value in values]

    def __getitem__(self, index):
        return self.values[index]

    def __setitem__(self, index, value):
        self.values[index] = float(value)

    def __add__(self, other):
        return _Vector(a + b for a, b in zip(self.values, other.values))

    def __mul__(self, scale):
        return _Vector(value * scale for value in self.values)

    x = property(lambda self: self.values[0])
    y = property(lambda self: self.values[1])

    @property
    def z(self):
        return self.values[2]

    @z.setter
    def z(self, value):
        self.values[2] = float(value)


def _load():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    names = {
        "REFLECTIVE_CONFIG", "STRIPS", "SIDE_PANELS", "HEM_WINDOW_MM",
        "HEM_NEAREST_COUNT", "_front_axis", "_choice", "_panel_names", "_strip_extents",
        "_hem_height", "_strip_target", "_merged_config", "strip_info_text",
    }
    nodes = [
        node for node in tree.body
        if getattr(node, "name", None) in names
        or (isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) in names)
    ]
    namespace = {"Vector": _Vector, "copy": copy}
    exec(compile(ast.Module(nodes, []), SCRIPT.name, "exec"), namespace)
    return namespace


def _panel(hem_z):
    """Side panel 4 m long (Y -2..2), 0..1 m high; hem points along Y."""
    world = [_Vector((0.5, y / 10.0, hem_z(y / 10.0))) for y in range(-20, 21)]
    return {
        "bounds": (_Vector((0.4, -2.0, 0.0)), _Vector((0.6, 2.0, 1.0))),
        "hem": list(range(len(world))),
    }, world


class ReflectiveStripTests(unittest.TestCase):
    def setUp(self):
        self.ns = _load()
        self.config = self.ns["REFLECTIVE_CONFIG"]
        self.strip = dict(self.config["front"])

    def _target(self, panel, world, end="front", axis="-Y", **values):
        strip = dict(self.strip, **values)
        half_along, half_up = self.ns["_strip_extents"](strip)
        return self.ns["_strip_target"](
            "PANEL_LEFT", panel, world, axis, end, strip, half_along, half_up
        )

    def test_front_and_rear_strips_default_to_orange_250_by_50(self):
        self.assertEqual(self.ns["STRIPS"], ("front", "rear"))
        for end in self.ns["STRIPS"]:
            strip = self.config[end]
            with self.subTest(end=end):
                self.assertTrue(strip["enabled"])
                self.assertEqual((strip["length_mm"], strip["width_mm"]), (250.0, 50.0))
                red, green, blue, _ = strip["color_rgba"]
                self.assertTrue(red == 1.0 and 0.1 < green < 0.5 and blue == 0.0)

    def test_extents_follow_orientation(self):
        self.assertEqual(self.ns["_strip_extents"](self.strip), (0.125, 0.025))
        self.strip["orientation"] = "VERTICAL"
        self.assertEqual(self.ns["_strip_extents"](self.strip), (0.025, 0.125))

    def test_sides(self):
        names = self.ns["_panel_names"]
        self.assertEqual(names(self.strip), ("PANEL_LEFT", "PANEL_RIGHT"))
        self.strip["sides"] = "panel_right"
        self.assertEqual(names(self.strip), ("PANEL_RIGHT",))
        self.strip["sides"] = "TOP"
        with self.assertRaises(ValueError):
            names(self.strip)

    def test_merged_config_keeps_strips_separate(self):
        merged = self.ns["_merged_config"]({"rear": {"distance_mm": 700.0}, "reference": "REAR"})
        self.assertEqual(merged["rear"]["distance_mm"], 700.0)
        self.assertEqual(merged["rear"]["length_mm"], 250.0)
        self.assertEqual(merged["front"]["distance_mm"], 500.0)
        self.assertNotIn("reference", merged)  # first-version flat keys are dropped
        merged["rear"]["enabled"] = False
        self.assertEqual(self.ns["strip_info_text"](merged, "rear"), "REFLECTIVE REAR OFF")

    def test_front_and_rear_ends_for_each_axis(self):
        panel, world = _panel(lambda y: 0.1)
        for axis, front_y in (("-Y", -1.5), ("+Y", 1.5)):
            with self.subTest(axis=axis):
                target, hem_z, source = self._target(panel, world, "front", axis)
                self.assertAlmostEqual(target.y, front_y)
                self.assertAlmostEqual(target.z, 0.4)   # hem 0.1 + 0.3
                self.assertEqual((round(hem_z, 6), source), (0.1, "hem"))
                target, _, _ = self._target(panel, world, "rear", axis)
                self.assertAlmostEqual(target.y, -front_y)

    def test_height_follows_local_sloped_hem(self):
        panel, world = _panel(lambda y: 0.1 + 0.05 * y)  # hem rises towards +Y
        target, hem_z, _ = self._target(panel, world, "rear")
        self.assertAlmostEqual(hem_z, 0.1 + 0.05 * 1.5)
        self.assertAlmostEqual(target.z, hem_z + 0.3)

    def test_panel_without_hem_uses_bottom(self):
        panel, world = _panel(lambda y: 0.1)
        panel["hem"] = []
        _, hem_z, source = self._target(panel, world)
        self.assertEqual((hem_z, source), (0.0, "panel_bottom"))

    def test_out_of_range_strip_is_rejected(self):
        panel, world = _panel(lambda y: 0.1)
        for values in ({"distance_mm": 50.0}, {"height_from_hem_mm": 10.0},
                       {"height_from_hem_mm": 900.0}):
            for end in ("front", "rear"):
                with self.subTest(values=values, end=end), self.assertRaises(ValueError):
                    self._target(panel, world, end, **values)

    def test_standalone_and_non_physical(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for text in ("project_config", "simulation.json", "modifiers.new",
                     "polygons.add", "vertices.add"):
            self.assertNotIn(text, source)
        self.assertIn('MARK_KINDS = {"front": "reflective_front", "rear": "reflective_rear"}',
                      source)
        self.assertIn("invoke_props_dialog", source)


if __name__ == "__main__":
    unittest.main()
