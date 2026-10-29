"""Blender background integration test for localized, animated HEM shrinking."""
from pathlib import Path
import runpy
import bpy

ns = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/blender/003_cloth_setup.py'), run_name='preset_test')
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 15
scene.gravity = (0, 0, 0)
bpy.ops.mesh.primitive_grid_add(x_subdivisions=21, y_subdivisions=21, size=1)
obj = bpy.context.object
for name, indices in (
    ('PANEL_TOP', [v.index for v in obj.data.vertices]),
    ('HEM_TOP_FRONT', [v.index for v in obj.data.vertices if v.co.y < -0.499]),
    ('HEM_TOP_REAR', [v.index for v in obj.data.vertices if v.co.y > 0.499]),
):
    obj.vertex_groups.new(name=name).add(indices, 1, 'REPLACE')
cloth = obj.modifiers.new('Cloth', 'CLOTH')
cloth.settings.quality = 12
cloth.settings.air_damping = 0
cloth.settings.bending_stiffness = 0.1
cloth.point_cache.frame_end = 15
prepare = ns['prepare_hem_shrink']
configure = ns['configure_hem_shrink']
weights = prepare(obj)
assert weights
assert all(abs(obj.data.vertices[i].co.y) > 0.34 for i in weights)
assert max(weights.values()) == 1
configure(obj, cloth, weights)
obj['cloth_hem_shrink_status'] = configure(obj, cloth, prepare(obj))
assert len([g for g in obj.vertex_groups if g.name.startswith('CC_HEM_SHRINK')]) == 1
assert len(obj.animation_data.drivers) == 1
front = [v.index for v in obj.data.vertices if v.co.y < -0.499]
rear = [v.index for v in obj.data.vertices if v.co.y > 0.499]
def span(indices):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    xs = [evaluated.data.vertices[i].co.x for i in indices]
    return max(xs) - min(xs)
spans = {}
for frame in range(1, 16):
    scene.frame_set(frame)
    spans[frame] = (span(front), span(rear))
    if frame <= 10:
        assert abs(cloth.settings.shrink_max) < 1e-7
    if frame >= 13:
        assert abs(cloth.settings.shrink_max - 0.20) < 1e-6
assert all(abs(a - b) < 1e-4 for a, b in zip(spans[10], spans[1])), spans
assert spans[15][0] < spans[10][0] - 0.001, spans
assert spans[15][1] < spans[10][1] - 0.001, spans
assert abs(spans[15][1] - spans[15][0]) < 0.02, spans
# Disabled cleanup is idempotent and clears only generated data.
configure.__globals__['ENABLE_HEM_SHRINK'] = False
configure(obj, cloth, {})
configure(obj, cloth, {})
assert not cloth.settings.vertex_group_shrink
assert cloth.settings.shrink_max == 0
assert obj.vertex_groups.get('CC_HEM_SHRINK') is None
assert not obj.animation_data.drivers
# Missing semantic input is rejected without creating groups or changing settings.
configure.__globals__['ENABLE_HEM_SHRINK'] = True
obj.vertex_groups.remove(obj.vertex_groups['HEM_TOP_FRONT'])
try:
    prepare(obj)
except RuntimeError as error:
    assert 'HEM_TOP_FRONT' in str(error)
else:
    raise AssertionError('Missing group should fail preflight')
assert obj.vertex_groups.get('CC_HEM_SHRINK') is None
print('HEM_SHRINK_PASS', spans)
