"""在 Blender Text Editor 运行：活动 Mesh 的四张正交图 + 两张透视图。

输出独立 PNG 和内嵌 PNG 的 SVG 图集；正交图 1 SVG unit = 1 mm。
透视图仅用于外观参考，不具备统一测量比例。无需项目依赖。
"""

import base64
import math
from pathlib import Path
from xml.sax.saxutils import escape

import bpy
from mathutils import Matrix, Vector


# 与 export_three_views.py 相同：Z 为高，X/Y 中较长的轴为车长。
# 若前后/左右方向不符，分别翻转对应 SIGN。
LEFT_SIGN = -1
FRONT_SIGN = -1
OUTPUT_FOLDER = "SIX_VIEWS"
RASTER_PX_PER_MM = 0.125
WORKBENCH_COLOR_TYPE = 'TEXTURE'
PERSPECTIVE_LENS_MM = 50.0
PERSPECTIVE_ELEVATION_DEG = 20.0
PERSPECTIVE_PADDING = 1.08
MARGIN_MM = 250.0
GAP_MM = 400.0
LABEL_HEIGHT_MM = 140.0
MIN_SHEET_WIDTH_MM = 10000.0
MIN_SHEET_HEIGHT_MM = 10000.0


def orientation(outward, up):
    z = outward.normalized()
    x = up.cross(z).normalized()
    y = z.cross(x).normalized()
    return Matrix((x, y, z)).transposed()


def snapshot(owner, names):
    return [(owner, name, getattr(owner, name)) for name in names]


def export_views():
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        raise RuntimeError("请先激活需要导出的 Mesh")
    if LEFT_SIGN not in (-1, 1) or FRONT_SIGN not in (-1, 1):
        raise ValueError("LEFT_SIGN / FRONT_SIGN 必须为 -1 或 1")
    if (RASTER_PX_PER_MM <= 0 or PERSPECTIVE_LENS_MM <= 0
            or PERSPECTIVE_PADDING < 1 or not 0 < PERSPECTIVE_ELEVATION_DEG < 90):
        raise ValueError("请检查采样率、焦距、透视留白和俯视角度配置")

    scene = bpy.context.scene
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    corners = [evaluated.matrix_world @ Vector(p) for p in evaluated.bound_box]
    low = Vector(tuple(min(p[i] for p in corners) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in corners) for i in range(3)))
    size = high - low
    if min(size) <= 0:
        raise RuntimeError("模型包围盒必须具有非零长、宽、高")
    center = (low + high) * 0.5
    mm_per_unit = (scene.unit_settings.scale_length or 1.0) * 1000.0
    along_x = size.x >= size.y
    length = max(size.x, size.y) * mm_per_unit
    width = min(size.x, size.y) * mm_per_unit
    height = size.z * mm_per_unit
    left = Vector((0, LEFT_SIGN, 0) if along_x else (LEFT_SIGN, 0, 0))
    front = Vector((FRONT_SIGN, 0, 0) if along_x else (0, FRONT_SIGN, 0))
    up = Vector((0, 0, 1))
    top_up = Vector((0, 1, 0) if along_x else (1, 0, 0))
    elevation = math.radians(PERSPECTIVE_ELEVATION_DEG)

    def perspective_direction(end):
        return ((left + end).normalized() * math.cos(elevation)
                + up * math.sin(elevation))

    # 每行两图：左/前、顶/后、左前透视/左后透视。
    views = [
        dict(key='LEFT', label='左视 / LEFT', w=length, h=height, direction=left, up=up),
        dict(key='FRONT', label='前视 / FRONT', w=width, h=height, direction=front, up=up),
        dict(key='TOP', label='顶视 / TOP', w=length, h=width, direction=up, up=top_up),
        dict(key='REAR', label='后视 / REAR', w=width, h=height, direction=-front, up=up),
        dict(key='LEFT_FRONT', label='左前透视 / LEFT FRONT — 非测量比例',
             w=length, h=length * 0.65, direction=perspective_direction(front), up=up),
        dict(key='LEFT_REAR', label='左后透视 / LEFT REAR — 非测量比例',
             w=length, h=length * 0.65, direction=perspective_direction(-front), up=up),
    ]
    column_widths = [max(v['w'] for v in views[i::2]) for i in range(2)]
    sheet_width = max(MIN_SHEET_WIDTH_MM, sum(column_widths) + GAP_MM + 2 * MARGIN_MM)
    y = MARGIN_MM + 260.0
    for row in range(3):
        pair = views[row * 2:row * 2 + 2]
        for col, view in enumerate(pair):
            view['x'] = MARGIN_MM if col == 0 else sheet_width - MARGIN_MM - view['w']
            view['y'] = y + LABEL_HEIGHT_MM
        y += LABEL_HEIGHT_MM + max(v['h'] for v in pair) + GAP_MM
    sheet_height = max(MIN_SHEET_HEIGHT_MM, y - GAP_MM + MARGIN_MM)

    safe_name = ''.join('_' if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in obj.name)
    safe_name = safe_name.strip().strip('.') or 'CAR'
    if safe_name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                                           *(f'COM{i}' for i in range(1, 10)),
                                           *(f'LPT{i}' for i in range(1, 10))}:
        safe_name = '_' + safe_name
    base = Path(bpy.path.abspath('//')) if bpy.data.filepath else Path.home() / 'Desktop'
    output = base / OUTPUT_FOLDER / safe_name
    output.mkdir(parents=True, exist_ok=True)

    render = scene.render
    shading = scene.display.shading
    settings = render.image_settings
    backup = snapshot(scene, ['camera'])
    backup += snapshot(render, ['engine', 'resolution_x', 'resolution_y', 'resolution_percentage',
                                'pixel_aspect_x', 'pixel_aspect_y', 'filepath', 'film_transparent',
                                'use_border', 'use_crop_to_border', 'use_compositing', 'use_sequencer'])
    backup += snapshot(settings, ['file_format', 'color_mode', 'color_depth', 'compression'])
    backup += snapshot(shading, ['light', 'color_type', 'show_shadows', 'show_cavity'])
    backup += snapshot(scene.display, ['render_aa'])
    hidden = [(other, other.hide_render) for other in scene.objects]
    camera_data = bpy.data.cameras.new('__SIX_VIEWS_CAMERA')
    camera = None
    try:
        camera = bpy.data.objects.new('__SIX_VIEWS_CAMERA', camera_data)
        scene.collection.objects.link(camera)
        scene.camera = camera
        render.engine = 'BLENDER_WORKBENCH'
        render.resolution_percentage = 100
        render.film_transparent = True
        render.use_border = render.use_crop_to_border = False
        render.use_compositing = render.use_sequencer = False
        settings.file_format = 'PNG'
        settings.color_mode = 'RGBA'
        settings.color_depth = '8'
        settings.compression = 100
        shading.light = 'STUDIO'
        shading.color_type = WORKBENCH_COLOR_TYPE
        shading.show_shadows = shading.show_cavity = True
        scene.display.render_aa = '32'
        for other, _ in hidden:
            other.hide_render = other != obj
        camera_data.sensor_fit = 'HORIZONTAL'
        camera_data.lens = PERSPECTIVE_LENS_MM
        camera_data.clip_start = max(size) * 0.00001

        for index, view in enumerate(views):
            rotation = orientation(view['direction'], view['up'])
            camera.rotation_euler = rotation.to_euler()
            render.resolution_x = max(2, round(view['w'] * RASTER_PX_PER_MM))
            render.resolution_y = max(2, round(view['h'] * RASTER_PX_PER_MM))
            render.pixel_aspect_x = 1.0
            render.pixel_aspect_y = (view['h'] * render.resolution_x
                                     / (view['w'] * render.resolution_y))
            if index < 4:
                camera_data.type = 'ORTHO'
                camera_data.ortho_scale = view['w'] / mm_per_unit
                distance = max(size) * 4.0
            else:
                camera_data.type = 'PERSP'
                tan_x = camera_data.sensor_width / (2.0 * camera_data.lens)
                tan_y = tan_x * view['h'] / view['w']
                local = [rotation.transposed() @ (p - center) for p in corners]
                # 对每个包围盒角点解透视锥约束，包含深度，避免长车头/车尾裁切。
                distance = max(p.z + PERSPECTIVE_PADDING * max(abs(p.x) / tan_x,
                                                                              abs(p.y) / tan_y)
                               for p in local) + camera_data.clip_start * 2
            camera.location = center + view['direction'].normalized() * distance
            camera_data.clip_end = distance + max(size) * 4
            bpy.context.view_layer.update()
            path = output / f"{safe_name}_{view['key']}.png"
            render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            with path.open('rb') as handle:
                view['data'] = base64.b64encode(handle.read()).decode('ascii')
            print(f"[{index + 1}/6] {path}")
    finally:
        for other, value in hidden:
            other.hide_render = value
        for owner, name, value in backup:
            setattr(owner, name, value)
        if camera is not None:
            bpy.data.objects.remove(camera, do_unlink=True)
        bpy.data.cameras.remove(camera_data)

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'width="{sheet_width:.3f}mm" height="{sheet_height:.3f}mm" '
           f'viewBox="0 0 {sheet_width:.3f} {sheet_height:.3f}">',
           '<g font-family="Arial, Microsoft YaHei, sans-serif" fill="#111827">',
           f'<text x="{MARGIN_MM}" y="{MARGIN_MM + 90}" font-size="90">{escape(obj.name)} — 六视图集</text>',
           f'<text x="{MARGIN_MM}" y="{MARGIN_MM + 190}" font-size="45">'
           f'L × W × H = {length:.1f} × {width:.1f} × {height:.1f} mm · 正交图 1:1 · 透视图仅供外观参考</text>']
    for view in views:
        svg.extend([
            f'<g id="{view["key"]}">',
            f'<text x="{view["x"]:.3f}" y="{view["y"] - 45:.3f}" font-size="55">{escape(view["label"])}</text>',
            f'<image x="{view["x"]:.3f}" y="{view["y"]:.3f}" width="{view["w"]:.3f}" '
            f'height="{view["h"]:.3f}" preserveAspectRatio="none" '
            f'xlink:href="data:image/png;base64,{view["data"]}"/>', '</g>'])
    svg.extend(['</g>', '</svg>'])
    svg_path = output / f'{safe_name}_SIX_VIEWS.svg'
    svg_path.write_text('\n'.join(svg), encoding='utf-8')
    print(f'六视图导出完成：{svg_path}')


if __name__ == '__main__':
    export_views()
