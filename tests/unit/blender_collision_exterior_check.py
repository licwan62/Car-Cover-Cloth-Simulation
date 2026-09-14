"""Run with blender --background --factory-startup --python this_file."""
import importlib.util
from pathlib import Path

import bpy
import numpy as np


path = Path(__file__).resolve().parents[2] / "scripts/blender/generate_collision_exterior.py"
spec = importlib.util.spec_from_file_location("exterior", path)
exterior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exterior)


def cube(name, dimensions, location=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = dimensions
    return obj


def select(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
outer = cube("Body", (2, 4, 1.5))
inner = cube("Hidden interior", (1.8, 3.8, 1.3))
subdivision = inner.modifiers.new("High detail interior", "SUBSURF")
subdivision.levels = 4
bpy.context.view_layer.update()
trees, low, high = exterior.source_trees([outer])
baseline, origin = exterior.sample_envelope(trees, low, high, 0.08)
trees, low, high = exterior.source_trees([outer, inner])
with_interior, _ = exterior.sample_envelope(trees, low, high, 0.08)
assert np.array_equal(baseline, with_interior), "Hidden high-poly parts changed exterior"

# A single-sided roof is sampled without needing Solidify or reliable normals.
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 1.5))
roof = bpy.context.object
roof.scale = (1.8, 3.8, 1)
bpy.context.view_layer.update()
trees, low, high = exterior.source_trees([outer, inner, roof])
grid, origin = exterior.sample_envelope(trees, low, high, 0.08)
assert origin.z + (np.argwhere(grid)[:, 2].max() + 1) * 0.08 >= 1.5

source_state = [(o, len(o.data.vertices), o.matrix_world.copy(), len(o.modifiers)) for o in (outer, inner, roof)]
exterior.VOXEL_SIZE_MM = 80
exterior.TARGET_TRIANGLES = 3000
select([outer, inner, roof])
proxy = exterior.main()
exterior.retain_exterior_and_validate(proxy.data)
assert proxy.collision and proxy.get(exterior.GENERATED_TAG)
assert max(v.co.z for v in proxy.data.vertices) >= 1.4, "Thin roof lost"
for obj, count, matrix, modifiers in source_state:
    assert len(obj.data.vertices) == count and obj.matrix_world == matrix
    assert len(obj.modifiers) == modifiers, "Source modifiers changed"

# Physical units produce the same envelope for metre and centimetre scenes.
bpy.context.scene.unit_settings.scale_length = 0.01
outer.scale *= 100
bpy.context.view_layer.update()
select([outer])
centimetre_proxy = exterior.main()
assert abs(centimetre_proxy.dimensions.x * 0.01 - 2) < 0.2

# Reject oversized grids and leave source selection/data untouched.
exterior.MAX_GRID_CELLS = 1000
select([outer])
before_objects = len(bpy.data.objects)
try:
    exterior.main()
except RuntimeError as error:
    assert "Grid" in str(error)
else:
    raise AssertionError("Missing grid allocation guard")
assert len(bpy.data.objects) == before_objects
assert bpy.context.view_layer.objects.active == outer and outer.select_get()
print("EXTERIOR_CHECKS_PASSED", flush=True)
