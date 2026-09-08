import ast
from collections import defaultdict
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "sewing_svg", ROOT / "scripts/illustrator/generate_sewing_svg.py"
)
svg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(svg)


class Vector(list):
    """Small 2D vector stand-in for the sewing SVG reader's arithmetic."""
    def __add__(self, other):
        return Vector(a + b for a, b in zip(self, other))

    def __iadd__(self, other):
        self[:] = self + other
        return self

    def __mul__(self, scalar):
        return Vector(a * scalar for a in self)

    def copy(self):
        return Vector(self)

    x = property(lambda self: self[0], lambda self, value: self.__setitem__(0, value))
    y = property(lambda self: self[1], lambda self, value: self.__setitem__(1, value))


class SewingSVGTests(unittest.TestCase):
    def test_dodge_output_is_readable_by_actual_sewing_parser(self):
        source = ROOT / "scripts/illustrator/SVG/Dodge Challenger 495-125 (+12).svg"
        before = source.read_bytes()
        tree = ast.parse((ROOT / "scripts/blender/generate_sewing_standalone.py").read_text(encoding="utf-8"))
        names = {"_local_name", "_cubic", "_flatten_path", "_element_polyline", "_semantic_svg"}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names
                 or isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id in {"_SEAM_NAME", "_PATH_TOKEN"}]
        namespace = dict(re=re, ET=ET, defaultdict=defaultdict, Vector=Vector)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "sewing_parser", "exec"), namespace)
        with tempfile.TemporaryDirectory() as directory:
            output = svg.convert_file(source, Path(directory) / "output.svg")
            panels, seams, hems, pairs = namespace["_semantic_svg"](output)
            self.assertEqual((len(panels), len(seams), len(hems), len(pairs)), (3, 4, 4, 2))
            self.assertTrue(all(points[0][0] < points[-1][0] for points in seams.values()))
            # TOP waist must survive; it cannot become a straight Tesla edge.
            self.assertGreater(max(p[1] for p in seams["S001_TOP"])
                               - min(p[1] for p in seams["S001_TOP"]), 30)
            with self.assertRaises(FileExistsError):
                svg.convert_file(source, output)
        self.assertEqual(source.read_bytes(), before)

    def test_split_top_accepts_consecutive_vertical_end_segments(self):
        source = ROOT / "scripts/illustrator/SVG/Dodge Challenger 495-125 (+12X2).svg"
        root = ET.parse(source).getroot()
        output = svg.convert_tree(root)
        paths = {element.get("id"): element for element in output.iter()}
        self.assertIn("HEM_TOP_FRONT", paths)
        self.assertIn("HEM_TOP_REAR", paths)
        segment_counts = [
            sum(token.isalpha() and token.upper() != "M"
                for token in svg.TOKEN.findall(element.get("d")))
            for name, element in paths.items()
            if name in {"HEM_TOP_FRONT", "HEM_TOP_REAR"}
        ]
        self.assertEqual(sorted(segment_counts), [1, 3])

    def test_smooth_curve_reflects_control_and_roundtrips(self):
        segments = svg.parse_path("M0 0 C1 0 2 1 3 1 s2 1 3 0 L0 0Z")
        self.assertEqual(segments[1], ((3., 1.), (6., 1.), ((4., 1.), (5., 2.))))
        self.assertEqual(svg.parse_path(svg.path_data(segments, True)), segments)

    def test_tesla_reference_partition_covers_exact_panel_boundary(self):
        root = ET.parse(ROOT / "scripts/illustrator/Tesla Model X 505-145.svg").getroot()
        output = svg.convert_tree(root)
        for element in output[0]:
            segments = svg.contour(element)
            if element.get("id") == "PANEL_TOP":
                seams, hems = svg.split_panel(segments, top=True)
                partition = sum(seams + hems, [])
            else:
                seam, hem = svg.split_panel(segments)
                partition = seam + hem
            def canonical(segment):
                reverse = (segment[1], segment[0], tuple(reversed(segment[2])) if segment[2] else None)
                return min(repr(segment), repr(reverse))
            self.assertCountEqual(map(canonical, segments), map(canonical, partition))

    def test_ambiguous_or_transformed_input_fails(self):
        with self.assertRaises(ValueError):
            svg.split_panel(svg.parse_path("M0 0H100V20H0Z"))
        root = ET.parse(ROOT / "scripts/illustrator/Tesla Model X 505-145.svg").getroot()
        root[0].set("transform", "scale(2)")
        with self.assertRaisesRegex(ValueError, "transforms"):
            svg.convert_tree(root)

    def test_front_can_be_reversed(self):
        root = ET.parse(ROOT / "scripts/illustrator/Tesla Model X 505-145.svg").getroot()
        right = svg.convert_tree(root, "right")
        left = svg.convert_tree(root, "left")
        paths = lambda output: {e.get("id"): e.get("d") for e in output.iter()}
        self.assertEqual(paths(right)["HEM_TOP_FRONT"], paths(left)["HEM_TOP_REAR"])


if __name__ == "__main__":
    unittest.main()
