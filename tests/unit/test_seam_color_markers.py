"""Test seam-face selection without importing Blender."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class SeamColorMarkerTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / "scripts/blender/setup_cloth.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        wanted = {"is_semantic_seam_group", "semantic_seam_faces"}
        nodes = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in wanted
        ]
        namespace = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
        self.select = namespace["semantic_seam_faces"]

    def test_marks_only_faces_containing_a_semantic_seam_edge(self):
        groups = [SimpleNamespace(name="S001_TOP", index=2)]
        vertices = [
            SimpleNamespace(index=0, groups=[SimpleNamespace(group=2, weight=1.0)]),
            SimpleNamespace(index=1, groups=[SimpleNamespace(group=2, weight=1.0)]),
            SimpleNamespace(index=2, groups=[]),
            SimpleNamespace(index=3, groups=[SimpleNamespace(group=2, weight=1.0)]),
            SimpleNamespace(index=4, groups=[]),
        ]
        polygons = [
            SimpleNamespace(index=0, vertices=(0, 1, 2)),
            SimpleNamespace(index=1, vertices=(0, 2, 4)),
        ]
        obj = SimpleNamespace(
            vertex_groups=groups,
            data=SimpleNamespace(vertices=vertices, polygons=polygons),
        )

        faces, vertex_count = self.select(obj)

        self.assertEqual(faces, {0})
        self.assertEqual(vertex_count, 3)


if __name__ == "__main__":
    unittest.main()
