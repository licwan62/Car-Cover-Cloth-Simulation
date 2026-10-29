"""在 Blender Text Editor 运行：视口外观的四张正交图 + 四张透视图。

输出独立 PNG 和内嵌 PNG 的 SVG 图集；正交图 1 SVG unit = 1 mm。
活动 Mesh 用于计算尺寸，导出当前视图层/局部视图中的可见对象。
需在同一窗口保留普通 3D 视口；透视图仅供外观参考。无需项目依赖。
"""

import base64
import math
from pathlib import Path
from xml.sax.saxutils import escape

import bpy
from mathutils import Matrix, Vector


# 与 300_export_three_views.py 相同：Z 为高，X/Y 中较长的轴为车长。
# 若前后/左右方向不符，分别翻转对应 SIGN。
LEFT_SIGN = -1
FRONT_SIGN = -1
OUTPUT_FOLDER = "EIGHT_VIEWS"
RASTER_PX_PER_MM = 0.25  # 质量/速度折中，0.125 = 1:8 缩小；0.25 = 1:4 缩小；0.5 = 1:2 缩小；1.0 = 1:1 原尺寸。
VIEWPORT_AA = '32'
ORTHO_MARGIN_MM = 100.0  # 正交图四周留白，避免轮廓贴边被截断；保持毫米比例。
# 继承目标视口的具体棚灯及其参数，其余按参考图设置。
VIEWPORT_XRAY_ALPHA = 0.600
VIEWPORT_OUTLINE_COLOR = (0.0, 1.0, 0.0)
# 透视图使用线框视图，并通过 Blender 主题的活动选择颜色突出布料。
# False 隐藏正交图网格、选择高亮、辅助线等；实际 Mesh/Text 标记仍会导出。
KEEP_VIEWPORT_OVERLAYS = False
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
    values = []
    for name in names:
        value = getattr(owner, name)
        # RNA 数组/向量可能引用原数据，必须复制后再修改。
        if isinstance(value, bpy.types.ID):
            pass
        elif hasattr(value, 'copy'):
            value = value.copy()
        elif not isinstance(value, (str, bool, int, float, type(None), bpy.types.ID)):
            value = tuple(value)
        values.append((owner, name, value))
    return values


def find_viewport():
    if bpy.app.background:
        raise RuntimeError("视口导出需要 Blender 图形界面，不支持 --background")
    window = bpy.context.window
    if window is None:
        raise RuntimeError("找不到当前 Blender 窗口")
    areas = [area for area in window.screen.areas if area.type == 'VIEW_3D']
    if bpy.context.area in areas:
        area = bpy.context.area
    elif areas:
        # Text Editor 运行时优先使用同窗口最大的 3D 视口。
        area = max(areas, key=lambda item: item.width * item.height)
    else:
        raise RuntimeError("请退出编辑器最大化，并在同一窗口保留一个 3D 视口")
    space = area.spaces.active
    if space.region_quadviews:
        raise RuntimeError("请先退出目标 3D 视口的四分视图，再导出")
    region = next((region for region in area.regions if region.type == 'WINDOW'), None)
    if region is None or space.region_3d is None:
        raise RuntimeError("目标 3D 视口没有可用的 WINDOW 区域")
    return window, area, region, space


def export_views():
    window, area, region, space = find_viewport()
    obj = bpy.context.active_object
    if obj is None or obj.type != 'MESH':
        raise RuntimeError("请先激活需要导出的 Mesh")
    if obj.mode != 'OBJECT':
        raise RuntimeError("请先切换到物体模式，并激活需要高亮的布料 Mesh")
    if LEFT_SIGN not in (-1, 1) or FRONT_SIGN not in (-1, 1):
        raise ValueError("LEFT_SIGN / FRONT_SIGN 必须为 -1 或 1")
    if (RASTER_PX_PER_MM <= 0 or ORTHO_MARGIN_MM < 0 or PERSPECTIVE_LENS_MM <= 0
            or PERSPECTIVE_PADDING < 1 or not 0 < PERSPECTIVE_ELEVATION_DEG < 90):
        raise ValueError("请检查采样率、焦距、透视留白和俯视角度配置")
    if not 0 <= VIEWPORT_XRAY_ALPHA <= 1:
        raise ValueError("VIEWPORT_XRAY_ALPHA 必须位于 0 到 1 之间")
    if not obj.visible_get(view_layer=window.view_layer, viewport=space):
        raise RuntimeError("活动 Mesh 在目标 3D 视口中不可见，请检查视图层和局部视图")

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

    def perspective_direction(side, end, elevation_sign):
        return ((side + end).normalized() * math.cos(elevation)
                + up * math.sin(elevation) * elevation_sign)

    # 每行两图：左/前、顶/后、左前/左后俯视、右前/右后仰视。
    views = [
        dict(key='LEFT', label='左视 / LEFT', w=length, h=height, direction=left, up=up),
        dict(key='FRONT', label='前视 / FRONT', w=width, h=height, direction=front, up=up),
        dict(key='TOP', label='顶视 / TOP', w=length, h=width, direction=up, up=top_up),
        dict(key='REAR', label='后视 / REAR', w=width, h=height, direction=-front, up=up),
        dict(key='LEFT_FRONT', label='左前俯视 / LEFT FRONT ABOVE — 非测量比例',
             w=length, h=length * 0.65, direction=perspective_direction(left, front, 1), up=up),
        dict(key='LEFT_REAR', label='左后俯视 / LEFT REAR ABOVE — 非测量比例',
             w=length, h=length * 0.65, direction=perspective_direction(left, -front, 1), up=up),
        dict(key='RIGHT_FRONT', label='右前仰视 / RIGHT FRONT BELOW — 非测量比例',
             w=length, h=length * 0.65, direction=perspective_direction(-left, front, -1), up=up),
        dict(key='RIGHT_REAR', label='右后仰视 / RIGHT REAR BELOW — 非测量比例',
             w=length, h=length * 0.65, direction=perspective_direction(-left, -front, -1), up=up),
    ]
    for view in views[:4]:
        view['w'] += 2 * ORTHO_MARGIN_MM
        view['h'] += 2 * ORTHO_MARGIN_MM
    column_widths = [max(v['w'] for v in views[i::2]) for i in range(2)]
    sheet_width = max(MIN_SHEET_WIDTH_MM, sum(column_widths) + GAP_MM + 2 * MARGIN_MM)
    y = MARGIN_MM + 260.0
    for row in range((len(views) + 1) // 2):
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
    shading = space.shading
    region_3d = space.region_3d
    settings = render.image_settings
    backup = snapshot(scene, ['camera'])
    backup += snapshot(render, ['engine', 'resolution_x', 'resolution_y', 'resolution_percentage',
                                'pixel_aspect_x', 'pixel_aspect_y', 'filepath', 'film_transparent',
                                'use_border', 'use_crop_to_border', 'use_compositing', 'use_sequencer',
                                'use_multiview', 'use_file_extension', 'use_stamp'])
    backup += snapshot(settings, ['file_format', 'color_mode', 'color_depth', 'compression'])
    backup += snapshot(scene.display, ['render_aa', 'viewport_aa'])
    backup += snapshot(bpy.context.preferences.system, ['viewport_aa'])
    backup += snapshot(shading, ['type', 'light', 'color_type', 'background_type',
                                'show_backface_culling', 'show_object_outline',
                                'object_outline_color', 'show_specular_highlight',
                                'show_xray', 'xray_alpha', 'show_shadows', 'show_cavity',
                                'cavity_type', 'show_xray_wireframe', 'xray_alpha_wireframe',
                                'wireframe_color_type'])
    backup += snapshot(space, ['use_local_camera', 'camera', 'show_gizmo'])
    backup += snapshot(space.overlay, ['show_overlays', 'show_outline_selected',
                                      'show_extras', 'show_floor', 'show_axis_x', 'show_axis_y',
                                      'show_axis_z', 'show_cursor', 'show_text',
                                      'show_relationship_lines', 'show_stats',
                                      'show_wireframes', 'wireframe_threshold', 'wireframe_opacity'])
    backup += snapshot(region_3d, ['view_location', 'view_rotation', 'view_distance',
                                  'view_camera_zoom', 'view_camera_offset', 'view_perspective'])
    camera_data = bpy.data.cameras.new('__SIX_VIEWS_CAMERA')
    camera = None
    view_layer = window.view_layer
    selection = [(other, other.select_get(view_layer=view_layer))
                 for other in view_layer.objects]
    active = view_layer.objects.active
    try:
        camera = bpy.data.objects.new('__SIX_VIEWS_CAMERA', camera_data)
        scene.collection.objects.link(camera)
        scene.camera = camera
        space.use_local_camera = True
        space.camera = camera
        region_3d.view_perspective = 'CAMERA'
        space.show_gizmo = False
        space.overlay.show_overlays = KEEP_VIEWPORT_OVERLAYS
        render.resolution_percentage = 100
        # X-Ray 与背景混合，使用主题背景才能保持参考图的观感。
        render.film_transparent = False
        render.use_border = render.use_crop_to_border = False
        render.use_compositing = render.use_sequencer = False
        render.use_multiview = render.use_stamp = False
        render.use_file_extension = True
        settings.file_format = 'PNG'
        settings.color_mode = 'RGBA'
        settings.color_depth = '8'
        settings.compression = 100
        scene.display.render_aa = scene.display.viewport_aa = VIEWPORT_AA
        bpy.context.preferences.system.viewport_aa = VIEWPORT_AA
        shading.type = 'SOLID'
        shading.light = 'STUDIO'
        shading.color_type = 'TEXTURE'
        shading.background_type = 'THEME'
        shading.show_backface_culling = False
        shading.show_object_outline = True
        shading.object_outline_color = VIEWPORT_OUTLINE_COLOR
        shading.show_specular_highlight = True
        shading.show_xray = True
        shading.xray_alpha = VIEWPORT_XRAY_ALPHA
        shading.show_shadows = False
        shading.show_cavity = True
        shading.cavity_type = 'SCREEN'
        camera_data.sensor_fit = 'HORIZONTAL'
        camera_data.lens = PERSPECTIVE_LENS_MM
        camera_data.clip_start = max(size) * 0.00001

        for index, view in enumerate(views):
            if view['key'] in {'LEFT', 'TOP'}:
                shading.type = 'SOLID'
                shading.show_object_outline = True
                # 前视线框之后恢复正交纹理图的原选择/叠加设置。
                for owner, name, value in backup:
                    if owner == space.overlay:
                        setattr(owner, name, value)
                for other, selected in selection:
                    other.select_set(selected, view_layer=view_layer)
                view_layer.objects.active = active
                space.overlay.show_overlays = KEEP_VIEWPORT_OVERLAYS
            else:
                # 前后正交及四张透视：线框、选中布料高亮、无绿色轮廓。
                shading.type = 'WIREFRAME'
                shading.show_object_outline = False
                shading.wireframe_color_type = 'THEME'
                shading.show_xray_wireframe = False
                shading.xray_alpha_wireframe = 1.0
                space.overlay.show_overlays = True
                space.overlay.show_outline_selected = True
                space.overlay.show_wireframes = True
                space.overlay.wireframe_threshold = 1.0
                space.overlay.wireframe_opacity = 1.0
                for name in ('show_extras', 'show_floor', 'show_axis_x', 'show_axis_y',
                             'show_axis_z', 'show_cursor', 'show_text',
                             'show_relationship_lines', 'show_stats'):
                    setattr(space.overlay, name, False)
                for other, _ in selection:
                    other.select_set(other == obj, view_layer=view_layer)
                view_layer.objects.active = obj
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
            region_3d.update()
            path = output / f"{safe_name}_{view['key']}.png"
            render.filepath = str(path)
            with bpy.context.temp_override(window=window, area=area, region=region):
                result = bpy.ops.render.opengl(write_still=True, view_context=True)
            if 'FINISHED' not in result:
                raise RuntimeError(f"视口导出未完成：{view['key']} ({result})")
            with path.open('rb') as handle:
                view['data'] = base64.b64encode(handle.read()).decode('ascii')
            print(f"[{index + 1}/{len(views)}] {path}")
    finally:
        for other, selected in selection:
            other.select_set(selected, view_layer=view_layer)
        view_layer.objects.active = active
        for owner, name, value in reversed(backup):
            setattr(owner, name, value)
        region_3d.update()
        if camera is not None:
            bpy.data.objects.remove(camera, do_unlink=True)
        bpy.data.cameras.remove(camera_data)
        area.tag_redraw()

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'width="{sheet_width:.3f}mm" height="{sheet_height:.3f}mm" '
           f'viewBox="0 0 {sheet_width:.3f} {sheet_height:.3f}">',
           '<g font-family="Arial, Microsoft YaHei, sans-serif" fill="#111827">',
           f'<text x="{MARGIN_MM}" y="{MARGIN_MM + 90}" font-size="90">{escape(obj.name)} — 八视图集</text>',
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
    svg_path = output / f'{safe_name}_EIGHT_VIEWS.svg'
    svg_path.write_text('\n'.join(svg), encoding='utf-8')
    print(f'八视图导出完成：{svg_path}')


if __name__ == '__main__':
    export_views()
