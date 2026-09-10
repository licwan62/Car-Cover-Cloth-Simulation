"""Run with Blender --background --factory-startup --python this_file."""
from pathlib import Path
import bpy, runpy
ns=runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/blender/setup_cloth.py'),run_name='preset_test')
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_grid_add(x_subdivisions=9,y_subdivisions=9,size=2)
obj=bpy.context.object
for v in obj.data.vertices: v.co.z=0.15*v.co.x+0.1*v.co.y
hem=obj.vertex_groups.new(name='HEM')
hem.add([v.index for v in obj.data.vertices if abs(v.co.x)>0.99 or abs(v.co.y)>0.99],1,'REPLACE')
cloth=obj.modifiers.new('Cloth','CLOTH'); cloth.settings.quality=8
bpy.context.scene.gravity=(0,0,0)
ns['configure_hem_level_feedback'](obj,cloth)
scene=bpy.context.scene
spreads={}
for f in range(1,76):
 scene.frame_set(f)
 ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
 if f in (45,60,75):
  z=[v.co.z for v in ev.data.vertices if any(g.group == hem.index for g in v.groups)]; spreads[f]=max(z)-min(z)
  print('HEM_SMOKE',f,spreads[f])
key=obj.data.shape_keys.key_blocks['CC_HEM_LIVE_LEVEL_0075']
assert key.value==1
assert spreads[75] < 0.005, spreads
print('HEM_SMOKE_PASS')
