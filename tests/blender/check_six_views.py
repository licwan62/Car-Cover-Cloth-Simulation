"""Check real viewport export in a disposable Blender GUI instance.

blender --factory-startup --python tests/blender/check_six_views.py

The check quits its Blender instance on completion. Artifacts and the result
are written under the temporary directory printed in the console. With
--background, only the unsupported-context guard is checked.
"""

import importlib.util
from array import array
from pathlib import Path
import tempfile
import traceback
import xml.etree.ElementTree as ET

import bpy


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/blender/301_export_six_views.py'
OUTPUT = Path(tempfile.mkdtemp(prefix='six_views_check_'))
print(f'SIX_VIEWS_CHECK_OUTPUT={OUTPUT}', flush=True)


def load_exporter():
    spec = importlib.util.spec_from_file_location('six_views_exporter', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def state(space):
    """Independent snapshot of UI/render state, including mutable RNA arrays."""
    owners = [bpy.context.scene.render, bpy.context.scene.render.image_settings,
              space, space.shading, space.overlay, space.region_3d,
              bpy.context.scene.display]
    result = []
    for owner in owners:
        props = {}
        for prop in owner.bl_rna.properties:
            if prop.is_readonly or prop.type == 'COLLECTION':
                continue
            value = getattr(owner, prop.identifier)
            if getattr(prop, 'is_array', False):
                value = tuple(value)
            elif prop.type == 'POINTER':
                value = value.as_pointer() if value else None
            props[prop.identifier] = value
        result.append(props)
    result.append(bpy.context.scene.camera)
    result.append([(obj.name, obj.hide_render, obj.hide_get(), obj.select_get())
                   for obj in bpy.context.scene.objects])
    result.append(bpy.context.view_layer.objects.active)
    result.append(bpy.context.preferences.system.viewport_aa)
    result.append(tuple(bpy.context.preferences.themes[0].view_3d.wire))
    result.append(sorted(bpy.data.cameras.keys()))
    return result


def assert_restored(space, before):
    after = state(space)
    differences = []
    for index, (old, new) in enumerate(zip(before, after)):
        if old == new:
            continue
        if isinstance(old, dict):
            differences.extend((index, key, value, new[key])
                               for key, value in old.items() if value != new[key])
        else:
            differences.append((index, old, new))
    assert not differences, differences


def check_gui():
    exporter = load_exporter()
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_cube_add()
    car = bpy.context.object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.subdivide(number_cuts=5)
    bpy.ops.mesh.quads_convert_to_tris()
    bpy.ops.object.mode_set(mode='OBJECT')
    car.name = 'ViewportCheck'
    car.scale = (2.0, 1.0, 0.8)
    mat = bpy.data.materials.new('Blue body')
    mat.diffuse_color = (0.05, 0.1, 0.9, 1)
    car.data.materials.append(mat)

    # A separate object visible in the viewport but disabled for final renders.
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.45, location=(0, -1.15, 0))
    marker = bpy.context.object
    marker.hide_render = True
    mat = bpy.data.materials.new('Red marker')
    mat.diffuse_color = (1, 0.01, 0.01, 1)
    marker.data.materials.append(mat)
    font = bpy.data.curves.new('Label', 'FONT')
    font.body = 'MARK'
    font.size = 0.3
    label = bpy.data.objects.new('Separate text', font)
    bpy.context.scene.collection.objects.link(label)
    label.location = (-0.6, -1.2, 0.35)
    label.rotation_euler.x = 1.57079632679
    bpy.context.view_layer.objects.active = car
    marker.select_set(True)  # Must be deselected only for perspective exports.
    car.select_set(True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / 'check.blend'))

    _, area, _, space = exporter.find_viewport()
    # Exercise restoration of non-default configuration and a previous camera.
    old_camera = bpy.data.objects.new('Original camera', bpy.data.cameras.new('Original camera'))
    bpy.context.scene.collection.objects.link(old_camera)
    bpy.context.scene.camera = old_camera
    space.camera = old_camera
    space.shading.object_outline_color = (0.2, 0.3, 0.4)
    space.shading.type = 'WIREFRAME'
    space.overlay.wireframe_threshold = 0.0
    space.overlay.wireframe_opacity = 0.25
    space.region_3d.view_perspective = 'ORTHO'
    bpy.context.scene.render.use_file_extension = False
    bpy.context.scene.render.use_stamp = True
    space.region_3d.update()
    before = state(space)
    # Mimic Run Script from another editor; the viewport must be discovered.
    editor = next(a for a in bpy.context.screen.areas if a != area)
    with bpy.context.temp_override(area=editor):
        exporter.export_views()
    assert_restored(space, before)

    output = OUTPUT / exporter.OUTPUT_FOLDER / car.name
    pngs = list(output.glob('*.png'))
    assert len(pngs) == 8, pngs
    root = ET.parse(output / f'{car.name}_EIGHT_VIEWS.svg').getroot()
    images = root.findall('.//{http://www.w3.org/2000/svg}image')
    assert len(images) == 8
    groups = {g.attrib['id']: g for g in root.findall('.//{http://www.w3.org/2000/svg}g')
              if 'id' in g.attrib}
    def image_y(key):
        return float(groups[key].find('{http://www.w3.org/2000/svg}image').attrib['y'])
    assert image_y('RIGHT_FRONT') > image_y('LEFT_FRONT')
    assert image_y('RIGHT_REAR') == image_y('RIGHT_FRONT')
    for image in images:
        assert image.attrib['{http://www.w3.org/1999/xlink}href'].startswith('data:image/png;base64,')
    image = bpy.data.images.load(str(output / f'{car.name}_LEFT.png'))
    expected = tuple(round(mm * exporter.RASTER_PX_PER_MM) for mm in (4200, 1800))
    assert tuple(image.size) == expected, tuple(image.size)
    pixels = array('f', [0.0]) * len(image.pixels)
    image.pixels.foreach_get(pixels)
    rgba = lambda: zip(*[iter(pixels)] * 4)
    assert all(p[3] > 0.99 for p in rgba()), 'Theme background must be opaque'
    assert any(g > r + 0.15 and g > b + 0.15 for r, g, b, _ in rgba()), 'Missing green outline'
    # X-Ray mixes the red marker with the blue body behind it.
    assert any(r > b + 0.01 for r, g, b, _ in rgba()), 'Separate viewport-only red marker missing'
    assert any(b > r + 0.15 for r, g, b, _ in rgba()), 'Blue body missing'
    bpy.data.images.remove(image)

    # All six mesh views use orange selected wires without green outlines.
    for key in ('FRONT', 'REAR', 'LEFT_FRONT', 'LEFT_REAR', 'RIGHT_FRONT', 'RIGHT_REAR'):
        image = bpy.data.images.load(str(output / f'{car.name}_{key}.png'))
        dimensions = (2200, 1800) if key in {'FRONT', 'REAR'} else (4000, 2600)
        expected = tuple(round(mm * exporter.RASTER_PX_PER_MM) for mm in dimensions)
        assert tuple(image.size) == expected, tuple(image.size)
        pixels = array('f', [0.0]) * len(image.pixels)
        image.pixels.foreach_get(pixels)
        rgba = lambda: zip(*[iter(pixels)] * 4)
        assert any(r > g + 0.1 and g > b + 0.05 for r, g, b, _ in rgba()), (
            f'Selected orange wireframe missing in {key}')
        assert not any(g > r + 0.15 and g > b + 0.15 for r, g, b, _ in rgba()), (
            f'Unexpected green outline in {key}')
        assert not any(b > r + 0.15 for r, g, b, _ in rgba()), (
            f'Unexpected solid blue shading in {key}')
        bpy.data.images.remove(image)

    # Fail in the first bottom perspective image, after changing selection and
    # overlay settings, exercising the actual cleanup path.
    original_encode = exporter.base64.b64encode

    encode_count = 0

    def fail_encode(data):
        nonlocal encode_count
        encode_count += 1
        camera = bpy.context.scene.camera
        if encode_count in (5, 6):
            assert camera.location.z > 0 and camera.location.y < 0
        if encode_count == 7:
            assert camera.location.z < 0 and camera.location.y > 0
            assert space.shading.type == 'WIREFRAME'
            assert space.shading.wireframe_color_type == 'THEME'
            assert space.shading.background_type == 'THEME'
            assert not space.shading.show_xray_wireframe
            assert abs(space.shading.xray_alpha_wireframe - 1.0) < 1e-6
            assert tuple(bpy.context.preferences.themes[0].view_3d.wire) == before[-2]
            assert not space.shading.show_object_outline
            assert bpy.context.preferences.system.viewport_aa == '32'
            assert bpy.context.scene.display.render_aa == '32'
            raise RuntimeError('Injected encoding failure')
        return original_encode(data)

    try:
        exporter.base64.b64encode = fail_encode
        try:
            exporter.export_views()
        except RuntimeError as error:
            assert str(error) == 'Injected encoding failure', str(error)
        else:
            raise AssertionError('Expected injected failure')
    finally:
        exporter.base64.b64encode = original_encode
    assert_restored(space, before)


def run():
    try:
        if bpy.app.background:
            try:
                load_exporter().export_views()
            except RuntimeError as error:
                assert '--background' in str(error)
            else:
                raise AssertionError('Background mode must fail clearly')
        else:
            check_gui()
        result = 'PASS'
    except Exception:
        result = traceback.format_exc()
    (OUTPUT / 'result.txt').write_text(result, encoding='utf-8')
    print(result, flush=True)
    bpy.ops.wm.quit_blender()


if bpy.app.background:
    run()
else:
    bpy.app.timers.register(run, first_interval=2.0)
