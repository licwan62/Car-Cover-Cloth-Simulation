import ast
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
        "REFLECTIVE_CONFIG", "SIDE_PANELS", "HEM_WINDOW_MM", "HEM_NEAREST_COUNT",
        "_front_axis", "_choice", "_panel_names", "_strip_extents", "_hem_height",
        "_strip_target",
    }
    nodes = [
        node for node in tree.body
        if getattr(node, "name", None) in names
        or (isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) in names)
    ]
    namespace = {"Vector": _Vector}
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
        self.config = dict(self.ns["REFLECTIVE_CONFIG"])

    def test_default_strip_is_250_by_50(self):
        self.assertEqual((self.config["length_mm"], self.config["width_mm"]), (250.0, 50.0))
        self.assertEqual(self.ns["_strip_extents"](self.config), (0.125, 0.025))
        self.config["orientation"] = "VERTICAL"
        self.assertEqual(self.ns["_strip_extents"](self.config), (0.025, 0.125))

    def test_sides(self):
        names = self.ns["_panel_names"]
        self.assertEqual(names(self.config), ("PANEL_LEFT", "PANEL_RIGHT"))
        self.config["sides"] = "panel_right"
        self.assertEqual(names(self.config), ("PANEL_RIGHT",))
        self.config["sides"] = "TOP"
        with self.assertRaises(ValueError):
            names(self.config)

    def test_front_and_rear_reference_with_minus_y_front(self):
        panel, world = _panel(lambda y: 0.1)
        self.config.update(distance_mm=500.0, height_from_hem_mm=300.0)
        target, hem_z, source = self.ns["_strip_target"](
            "PANEL_LEFT", panel, world, self.config, 0.125, 0.025
        )
        self.assertAlmostEqual(target.y, -1.5)  # front end is -Y
        self.assertAlmostEqual(target.z, 0.4)   # hem 0.1 + 0.3
        self.assertEqual((round(hem_z, 6), source), (0.1, "hem"))
        self.config["reference"] = "REAR"
        target, _, _ = self.ns["_strip_target"](
            "PANEL_LEFT", panel, world, self.config, 0.125, 0.025
        )
        self.assertAlmostEqual(target.y, 1.5)

    def test_height_follows_local_sloped_hem(self):
        panel, world = _panel(lambda y: 0.1 + 0.05 * y)  # hem rises towards +Y
        self.config.update(reference="REAR", distance_mm=500.0, height_from_hem_mm=300.0)
        target, hem_z, _ = self.ns["_strip_target"](
            "PANEL_LEFT", panel, world, self.config, 0.125, 0.025
        )
        self.assertAlmostEqual(hem_z, 0.1 + 0.05 * 1.5)
        self.assertAlmostEqual(target.z, hem_z + 0.3)

    def test_panel_without_hem_uses_bottom(self):
        panel, world = _panel(lambda y: 0.1)
        panel["hem"] = []
        _, hem_z, source = self.ns["_strip_target"](
            "PANEL_LEFT", panel, world, self.config, 0.125, 0.025
        )
        self.assertEqual((hem_z, source), (0.0, "panel_bottom"))

    def test_out_of_range_strip_is_rejected(self):
        panel, world = _panel(lambda y: 0.1)
        target = self.ns["_strip_target"]
        for values in ({"distance_mm": 50.0}, {"height_from_hem_mm": 10.0},
                       {"height_from_hem_mm": 900.0}):
            config = dict(self.config, **values)
            with self.subTest(values=values), self.assertRaises(ValueError):
                target("PANEL_LEFT", panel, world, config, 0.125, 0.025)

    def test_standalone_and_non_physical(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for text in ("project_config", "simulation.json", "modifiers.new",
                     "polygons.add", "vertices.add"):
            self.assertNotIn(text, source)
        self.assertIn('MARK_KIND = "reflective"', source)
        self.assertIn("invoke_props_dialog", source)


if __name__ == "__main__":
    unittest.main()
