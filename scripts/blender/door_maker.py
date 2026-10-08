"""Add a vertical door-position line to both sides of a settled car cover.

Usage in Blender:
1. Go to the settled comparison frame.
2. Select the car-cover mesh and make it active.
3. Ensure it has PANEL_LEFT and PANEL_RIGHT vertex groups.
4. Run this script and enter the distance from the vehicle front.

The line is drawn by the shared CC mark overlay scheme (see the block below),
so its edges are straight, follow the cloth as it deforms, and also show in
Solid view with Color = Texture. Marks written by mirror_markers.py,
plates_maker.py or cloth.py are kept. Cloth is unaffected.
"""

import bpy
import copy


DOOR_MARKER_CONFIG = {
    "front_axis": "-Y",
    "distance_from_front_mm": 1800.0,
    "line_width_mm": 30.0,
    "color_rgba": [0.04, 0.9, 0.16, 1.0],
}


MARK_ATTRIBUTE = "cc_door_marker_faces"
COORDINATE_SOURCE = "cc_door_marker_coordinate_source"
DOOR_MARK_KIND = "door"


# >>> CC MARK OVERLAY >>>
# Shared mark scheme. Keep this block identical in mirror_markers.py,
# door_maker.py, plates_maker.py, cloth.py and cloth_fit_test.py so each script
# still runs on its own from Blender's Text Editor.
#
# A mark is a FLOAT2 face-corner attribute ``cc_mark_<kind>`` holding each
# corner's normalized position inside the mark (inside means |u|, |v| < 1) plus
# a color stored in the object's ``cc_mark_colors`` property. mark_rebuild()
# derives everything else from those attributes, so any script can rebuild
# without losing the marks written by another:
# * faces touching a mark receive a copy of their base material whose Base
#   Color is overlaid by a per-pixel ``max(|u|, |v|) < 1`` test for every mark,
#   giving straight edges that follow the Cloth deformation;
# * Solid view cannot run shader nodes, so each overlay material also holds an
#   unlinked, active Image Texture (Closest) whose centre 2x2 texels are the
#   mark color, sampled through the active ``cc_mark_uv`` UV map.
# No geometry, mass, collision, constraints or modifiers are added.
MARK_ATTRIBUTE_PREFIX = "cc_mark_"
MARK_COLORS_PROPERTY = "cc_mark_colors"
MARK_OVERLAY_BASE_PROPERTY = "cc_marker_base_material"
MARK_OVERLAY_KIND_PROPERTY = "cc_marker_kind"
MARK_SOLID_UV_LAYER = "cc_mark_uv"
MARK_SOLID_TEXTURE_SIZE = 64  # the mark covers the centre 2x2 texels
MARK_OUTSIDE = 1.0e3
MARK_BASE_MATERIAL = "CC Cloth Base"
MARK_DEFAULT_BASE_COLOR = (0.18, 0.22, 0.28, 1.0)
# Per-face marker materials and slot properties written by earlier versions.
MARK_LEGACY_MATERIALS = {
    "CC Mirror Position Mark",
    "CC Charge Port Position Mark",
    "CC Door Position Mark",
    "CC Plate Opening Mockup",
    "CC Seam Color Mark",
    "CC Quick Fit Seam Preview",
}
MARK_LEGACY_PROPERTIES = (
    "cc_mirror_marker_material_slot",
    "cc_door_marker_material_slot",
    "cc_plates_material_slot",
    "cc_seam_marker_material_slot",
)


def mark_write(obj, kind, values, color):
    """Store one mark: flat (u, v) pairs per face corner and its RGBA color."""
    mesh = obj.data
    name = MARK_ATTRIBUTE_PREFIX + kind
    attribute = mesh.attributes.get(name)
    if attribute is not None and (
        attribute.domain != "CORNER" or attribute.data_type != "FLOAT2"
    ):
        mesh.attributes.remove(attribute)
        attribute = None
    if attribute is None:
        attribute = mesh.attributes.new(name, "FLOAT2", "CORNER")
    attribute.data.foreach_set("vector", values)
    colors = _mark_colors(obj)
    colors[kind] = [float(value) for value in color]
    obj[MARK_COLORS_PROPERTY] = colors


def mark_remove(obj, kind):
    attribute = obj.data.attributes.get(MARK_ATTRIBUTE_PREFIX + kind)
    if attribute is not None:
        obj.data.attributes.remove(attribute)
    colors = _mark_colors(obj)
    if colors.pop(kind, None) is not None:
        obj[MARK_COLORS_PROPERTY] = colors


def mark_touches(values, loop_indices):
    """True when the corner coordinates' bounding box meets the mark."""
    us = [values[index * 2] for index in loop_indices]
    vs = [values[index * 2 + 1] for index in loop_indices]
    return min(us) <= 1.0 and max(us) >= -1.0 and min(vs) <= 1.0 and max(vs) >= -1.0


def mark_rebuild(obj):
    """Reassign overlay materials and the Solid-view UV map from all marks.

    Returns {polygon index: kind shown in Solid view}.
    """
    mesh = obj.data
    kinds = _mark_kinds(obj)
    overlay_slots = {
        index for index, material in enumerate(mesh.materials)
        if material is not None and (
            MARK_OVERLAY_BASE_PROPERTY in material
            or material.name in MARK_LEGACY_MATERIALS
        )
    }
    fallback_slot = _mark_base_slot(obj, overlay_slots)
    # Return faces of earlier runs to their base material; legacy per-face
    # marker materials go to the fallback slot.
    restore = {}
    for slot in overlay_slots:
        base_name = mesh.materials[slot].get(MARK_OVERLAY_BASE_PROPERTY)
        base = bpy.data.materials.get(base_name) if base_name else None
        restore[slot] = _mark_material_slot(obj, base) if base else fallback_slot
    for polygon in mesh.polygons:
        if polygon.material_index in restore:
            polygon.material_index = restore[polygon.material_index]
    for name in MARK_LEGACY_PROPERTIES:
        if name in obj:
            del obj[name]

    coordinates = {}
    for kind in kinds:
        values = [0.0] * (len(mesh.loops) * 2)
        mesh.attributes[MARK_ATTRIBUTE_PREFIX + kind].data.foreach_get("vector", values)
        coordinates[kind] = values
    solid_uv = [0.0] * (len(mesh.loops) * 2)
    overlays = {}
    marked = {}
    for polygon in mesh.polygons:
        loop_indices = polygon.loop_indices
        # A face touching several marks shows the first one in Solid view;
        # rendering shows all of them.
        kind = next(
            (kind for kind, values in coordinates.items()
             if mark_touches(values, loop_indices)),
            None,
        )
        if kind is None:
            continue
        values = coordinates[kind]
        for index in loop_indices:
            solid_uv[index * 2:index * 2 + 2] = _mark_solid_uv(
                values[index * 2], values[index * 2 + 1]
            )
        key = (polygon.material_index, kind)
        if key not in overlays:
            base = mesh.materials[key[0]] if key[0] < len(mesh.materials) else None
            overlays[key] = _mark_material_slot(
                obj, _mark_overlay_material(base, kinds, kind)
            )
        polygon.material_index = overlays[key]
        marked[polygon.index] = kind

    layer = mesh.uv_layers.get(MARK_SOLID_UV_LAYER) or mesh.uv_layers.new(
        name=MARK_SOLID_UV_LAYER
    )
    layer.data.foreach_set("uv", solid_uv)
    # Solid view samples the active UV map and ignores UV Map nodes. The
    # render-active map is left unchanged so other textures keep their UVs.
    mesh.uv_layers.active = layer
    mesh.update()
    return marked


def mark_show_solid_texture(context):
    """Switch open 3D views to Solid Color = Texture so marks are visible."""
    screen = getattr(context, "screen", None)
    for area in screen.areas if screen else ():
        if area.type == "VIEW_3D":
            area.spaces.active.shading.color_type = "TEXTURE"


def mark_evaluated_vertices(obj):
    """World positions of the base-mesh vertices at the current frame.

    Modifiers after Cloth (the post-Cloth seam Weld, display Subdivision, ...)
    can change the evaluated topology at frame n. They are switched off only
    while sampling, so the Cloth result is read on the base topology; the Cloth
    cache up to the current frame is kept and the marks, stored on base-mesh
    corners, are carried through those modifiers again for display.
    """
    cloth_index = next(
        (index for index, modifier in enumerate(obj.modifiers) if modifier.type == "CLOTH"),
        len(obj.modifiers),
    )
    downstream = [
        modifier for modifier in list(obj.modifiers)[cloth_index + 1:]
        if modifier.show_viewport
    ]
    disabled = []
    try:
        while True:
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
            try:
                if (
                    len(mesh.vertices) == len(obj.data.vertices)
                    and len(mesh.polygons) == len(obj.data.polygons)
                ):
                    matrix = evaluated.matrix_world
                    return [matrix @ vertex.co for vertex in mesh.vertices]
            finally:
                evaluated.to_mesh_clear()
            if disabled or not downstream:
                raise RuntimeError(
                    "评估网格与基础网格拓扑不一致，且不是 Cloth 之后的修改器造成的；"
                    "请检查 Cloth 之前改变拓扑的修改器。"
                )
            for modifier in downstream:
                modifier.show_viewport = False
            disabled = downstream
    finally:
        for modifier in disabled:
            modifier.show_viewport = True


def _mark_colors(obj):
    stored = obj.get(MARK_COLORS_PROPERTY)
    if not hasattr(stored, "items"):
        return {}
    return {str(kind): [float(value) for value in color] for kind, color in stored.items()}


def _mark_kinds(obj):
    kinds = {}
    for kind, color in sorted(_mark_colors(obj).items()):
        attribute = obj.data.attributes.get(MARK_ATTRIBUTE_PREFIX + kind)
        if (
            attribute is not None
            and attribute.domain == "CORNER"
            and attribute.data_type == "FLOAT2"
        ):
            kinds[kind] = tuple(color)
    return kinds


def _mark_material_slot(obj, material):
    for index, slot_material in enumerate(obj.data.materials):
        if slot_material == material:
            return index
    obj.data.materials.append(material)
    return len(obj.data.materials) - 1


def _mark_base_slot(obj, excluded_slots=()):
    existing = next(
        (index for index in range(len(obj.data.materials)) if index not in excluded_slots),
        None,
    )
    if existing is not None:
        return existing
    base = bpy.data.materials.get(MARK_BASE_MATERIAL)
    if base is None:
        base = bpy.data.materials.new(MARK_BASE_MATERIAL)
        base.diffuse_color = MARK_DEFAULT_BASE_COLOR
    obj.data.materials.append(base)
    return len(obj.data.materials) - 1


def _mark_principled(material):
    if material is None or material.node_tree is None:
        return None
    return next(
        (node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"),
        None,
    )


def _mark_mask_factor(nodes, links, attribute_name, x, y):
    """Return a socket that is 1 inside the normalized mark, else 0."""
    attribute = nodes.new("ShaderNodeAttribute")
    attribute.attribute_type = "GEOMETRY"
    attribute.attribute_name = attribute_name
    attribute.location = (x, y)
    separate = nodes.new("ShaderNodeSeparateXYZ")
    separate.location = (x + 180, y)
    links.new(attribute.outputs["Vector"], separate.inputs[0])
    components = []
    for offset, name in enumerate(("X", "Y")):
        absolute = nodes.new("ShaderNodeMath")
        absolute.operation = "ABSOLUTE"
        absolute.location = (x + 360, y - offset * 160)
        links.new(separate.outputs[name], absolute.inputs[0])
        components.append(absolute.outputs[0])
    largest = nodes.new("ShaderNodeMath")
    largest.operation = "MAXIMUM"
    largest.location = (x + 540, y)
    links.new(components[0], largest.inputs[0])
    links.new(components[1], largest.inputs[1])
    inside = nodes.new("ShaderNodeMath")
    inside.operation = "LESS_THAN"
    inside.inputs[1].default_value = 1.0
    inside.location = (x + 720, y)
    links.new(largest.outputs[0], inside.inputs[0])
    return inside.outputs[0]


def _mark_solid_image(name, base_color, mark_color):
    """Image whose centre 2x2 texels are the mark, sampled with Closest."""
    size = MARK_SOLID_TEXTURE_SIZE
    # Always start fresh: re-packing an already packed image after editing its
    # pixels can store stale data.
    previous = bpy.data.images.get(name)
    if previous is not None:
        bpy.data.images.remove(previous)
    image = bpy.data.images.new(name, size, size, alpha=False, float_buffer=True)
    pixels = [float(base_color[0]), float(base_color[1]), float(base_color[2]), 1.0] * (size * size)
    mark = [float(mark_color[0]), float(mark_color[1]), float(mark_color[2]), 1.0]
    for y in (size // 2 - 1, size // 2):
        for x in (size // 2 - 1, size // 2):
            start = (y * size + x) * 4
            pixels[start:start + 4] = mark
    image.pixels.foreach_set(pixels)
    image.pack()  # generated images are otherwise lost when the .blend is saved
    return image


def _mark_solid_uv(u, v):
    # Maps |u|, |v| <= 1 exactly onto the centre texels of the Solid image.
    size = float(MARK_SOLID_TEXTURE_SIZE)
    return 0.5 + u / size, 0.5 + v / size


def _mark_overlay_material(base, kinds, kind):
    """Copy ``base`` and overlay every mark mask on its Base Color."""
    base_name = base.name if base is not None else ""
    label = kind.replace("_", " ").title()
    name = f"{base_name or MARK_BASE_MATERIAL} + CC {label} Mark"
    if _mark_principled(base) is not None:
        material = base.copy()
    else:
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        color = tuple(base.diffuse_color) if base is not None else MARK_DEFAULT_BASE_COLOR
        _mark_principled(material).inputs["Base Color"].default_value = color
    material[MARK_OVERLAY_BASE_PROPERTY] = base_name
    material[MARK_OVERLAY_KIND_PROPERTY] = kind

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = _mark_principled(material)
    base_input = principled.inputs["Base Color"]
    if base_input.is_linked:
        current = base_input.links[0].from_socket
    else:
        rgb = nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = tuple(base_input.default_value)
        rgb.location = (principled.location.x - 400, principled.location.y + 400)
        current = rgb.outputs[0]

    x = principled.location.x - 1400
    for row, (mask_kind, mask_color) in enumerate(kinds.items()):
        y = principled.location.y + 200 - row * 400
        factor = _mark_mask_factor(nodes, links, MARK_ATTRIBUTE_PREFIX + mask_kind, x, y)
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.location = (principled.location.x - 220, principled.location.y + 200 - row * 220)
        mix.inputs[7].default_value = mask_color
        links.new(factor, mix.inputs[0])
        links.new(current, mix.inputs[6])
        current = mix.outputs[2]
    links.new(current, base_input)
    # Solid view draws unmarked faces with diffuse_color, so the Solid image
    # uses it as background to blend with neighbouring faces.
    solid_base = tuple(base.diffuse_color) if base is not None else MARK_DEFAULT_BASE_COLOR
    material.diffuse_color = solid_base

    # Solid-view preview only: left unlinked so EEVEE/Cycles ignore it.
    preview = nodes.new("ShaderNodeTexImage")
    preview.name = preview.label = "CC Solid View Mark"
    preview.image = _mark_solid_image(name, solid_base, kinds[kind])
    preview.interpolation = "Closest"
    preview.extension = "EXTEND"
    preview.location = (principled.location.x - 700, principled.location.y + 700)
    for node in nodes:
        node.select = False
    preview.select = True
    nodes.active = preview

    existing = bpy.data.materials.get(name)
    if existing is not None and existing != material:
        existing.user_remap(material)
        bpy.data.materials.remove(existing)
    material.name = name
    return material
# <<< CC MARK OVERLAY <<<


def _is_cloth(obj):
    return obj.type == "MESH" and any(mod.type == "CLOTH" for mod in obj.modifiers)


def _active_cloth():
    active = bpy.context.view_layer.objects.active
    if active and _is_cloth(active):
        return active
    selected = [obj for obj in bpy.context.selected_objects if _is_cloth(obj)]
    if len(selected) == 1:
        return selected[0]
    raise RuntimeError("请激活唯一的 Cloth 网格后再运行车门标记脚本。")


def _vertex_group_indices(obj, name):
    group = obj.vertex_groups.get(name)
    if group is None:
        raise RuntimeError(
            f"缺少 {name} 顶点组；请先运行 generate_sewing.py "
            "从语义 SVG 创建 PANEL 顶点组。"
        )
    indices = {
        vertex.index
        for vertex in obj.data.vertices
        if any(item.group == group.index and item.weight > 0.001 for item in vertex.groups)
    }
    if not indices:
        raise RuntimeError(f"{name} 顶点组为空。")
    return indices



def _panel_geometry(obj):
    panels = {}
    for name in ("PANEL_LEFT", "PANEL_RIGHT"):
        vertex_indices = _vertex_group_indices(obj, name)
        polygon_indices = {
            polygon.index
            for polygon in obj.data.polygons
            if all(index in vertex_indices for index in polygon.vertices)
        }
        if not polygon_indices:
            raise RuntimeError(f"{name} 没有包含任何完整布料面。")
        panels[name] = {
            "vertices": vertex_indices,
            "polygons": polygon_indices,
        }
    return panels


def _longitudinal_axis(config):
    axis = str(config["front_axis"]).upper()
    if axis not in {"+X", "-X", "+Y", "-Y"}:
        raise ValueError("front_axis 必须为 '+X'、'-X'、'+Y' 或 '-Y'。")
    return axis, 0 if axis.endswith("X") else 1


def _door_position(evaluated_vertices, panel_vertex_indices, axis, distance_mm):
    component = 0 if axis.endswith("X") else 1
    coordinates = [
        evaluated_vertices[index][component]
        for indices in panel_vertex_indices
        for index in indices
    ]
    front = max(coordinates) if axis.startswith("+") else min(coordinates)
    direction = -1.0 if axis.startswith("+") else 1.0
    return front + direction * float(distance_mm) / 1000.0


def apply_door_marker(cloth=None, config=None):
    config = copy.deepcopy(DOOR_MARKER_CONFIG if config is None else config)
    cloth = cloth or _active_cloth()
    evaluated_vertices = mark_evaluated_vertices(cloth)
    panels = _panel_geometry(cloth)
    axis, longitudinal = _longitudinal_axis(config)
    position = _door_position(
        evaluated_vertices,
        [panel["vertices"] for panel in panels.values()],
        axis,
        config["distance_from_front_mm"],
    )
    half_width = max(float(config["line_width_mm"]) / 2000.0, 1.0e-6)

    # The line is a mark that is unbounded vertically: u is the signed
    # longitudinal offset in half line widths, v stays inside.
    mesh = cloth.data
    values = [MARK_OUTSIDE] * (len(mesh.loops) * 2)
    counts = {}
    for panel_name, panel in panels.items():
        selected = 0
        for index in panel["polygons"]:
            polygon = mesh.polygons[index]
            for loop_index in polygon.loop_indices:
                vertex = evaluated_vertices[mesh.loops[loop_index].vertex_index]
                values[loop_index * 2] = (vertex[longitudinal] - position) / half_width
                values[loop_index * 2 + 1] = 0.0
            selected += mark_touches(values, polygon.loop_indices)
        if not selected:
            raise RuntimeError(
                f"距车头 {config['distance_from_front_mm']:g} mm 处未在 {panel_name} "
                "找到布料面；请检查车头方向、距离或增大线宽。"
            )
        counts[panel_name] = selected
    mark_write(cloth, DOOR_MARK_KIND, values, config["color_rgba"])
    marked = {
        index for index, kind in mark_rebuild(cloth).items() if kind == DOOR_MARK_KIND
    }

    cloth[MARK_ATTRIBUTE] = ",".join(str(index) for index in sorted(marked))
    cloth[COORDINATE_SOURCE] = "evaluated_panel_left_right_front_bound_corner_uv"
    cloth["cc_door_marker_front_offset_mm"] = float(config["distance_from_front_mm"])
    cloth["cc_door_marker_line_width_mm"] = float(config["line_width_mm"])
    print(
        f"Door marker: cloth={cloth.name}, distance_from_front="
        f"{config['distance_from_front_mm']:g} mm, faces={len(marked)}, counts={counts}"
    )
    return marked


class CC_OT_setup_door_marker(bpy.types.Operator):
    """按距车头的长度在左右侧版片上生成平行 Z 轴的车门标记线"""

    bl_idname = "cc.setup_door_marker"
    bl_label = "车门位置标记线"
    bl_options = {"REGISTER", "UNDO"}

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager
        layout.prop(settings, "cc_door_marker_front_axis")
        layout.prop(settings, "cc_door_marker_distance_mm")
        layout.prop(settings, "cc_door_marker_width_mm")

    def execute(self, context):
        settings = context.window_manager
        config = copy.deepcopy(DOOR_MARKER_CONFIG)
        config.update({
            "front_axis": settings.cc_door_marker_front_axis,
            "distance_from_front_mm": settings.cc_door_marker_distance_mm,
            "line_width_mm": settings.cc_door_marker_width_mm,
        })
        try:
            marked = apply_door_marker(config=config)
        except (RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        mark_show_solid_texture(context)
        self.report({"INFO"}, f"已生成车门标记线：{len(marked)} 个面")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)


def launch_door_marker_dialog():
    """Register safely on repeated Text Editor runs and open the dialog."""
    previous = getattr(bpy.types, CC_OT_setup_door_marker.__name__, None)
    if previous is not None:
        try:
            bpy.utils.unregister_class(previous)
        except RuntimeError:
            pass

    wm = bpy.types.WindowManager
    wm.cc_door_marker_front_axis = bpy.props.EnumProperty(
        name="车头方向",
        items=(("-Y", "-Y", "Model X 默认"), ("+Y", "+Y", ""),
               ("-X", "-X", ""), ("+X", "+X", "")),
        default=DOOR_MARKER_CONFIG["front_axis"],
    )
    wm.cc_door_marker_distance_mm = bpy.props.FloatProperty(
        name="距车头长度 (mm)",
        min=0.0,
        default=DOOR_MARKER_CONFIG["distance_from_front_mm"],
    )
    wm.cc_door_marker_width_mm = bpy.props.FloatProperty(
        name="标记线宽 (mm)",
        min=1.0,
        default=DOOR_MARKER_CONFIG["line_width_mm"],
    )
    bpy.utils.register_class(CC_OT_setup_door_marker)
    if bpy.app.background:
        return apply_door_marker(config=copy.deepcopy(DOOR_MARKER_CONFIG))
    return bpy.ops.cc.setup_door_marker("INVOKE_DEFAULT")


if __name__ == "__main__":
    launch_door_marker_dialog()
