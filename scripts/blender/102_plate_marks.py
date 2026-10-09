"""Paint plate-opening mockups on the settled PANEL_TOP cloth.

Select the Cloth mesh, go to the comparison frame, then run in Blender's Text
Editor. The dark rectangles are drawn by the shared CC mark overlay scheme (see
the block below), not physical cutouts; they do not change Cloth topology,
mass, or collision, keep straight edges as the cloth deforms, and also show in
Solid view with Color = Texture. Distances are measured inward from the front
and rear ends of PANEL_TOP in evaluated world coordinates.
"""

import bpy
import re


PLATES_CONFIG = {
    "front_axis": "-Y",
    "front_distance_mm": 300.0,
    "rear_distance_mm": 300.0,
    "length_mm": 440.0,
    "width_mm": 140.0,
    "front_only": False,
    "material_name": "CC Plate Opening Mockup",
    "color_rgba": (0.012, 0.012, 0.016, 1.0),
    "color_hex": "#1C1C21",
}

FACES_KEY = "cc_plates_faces"
PLATES_MARK_KIND = "plates"


# >>> CC MARK OVERLAY >>>
# Shared mark scheme. Keep this block identical in 100_mirror_marks.py,
# 101_door_marks.py, 102_plate_marks.py and 003_cloth_setup.py so each script
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


def _active_cloth():
    obj = bpy.context.view_layer.objects.active
    if obj and obj.type == "MESH" and any(m.type == "CLOTH" for m in obj.modifiers):
        return obj
    raise RuntimeError("请先选中并激活带 Cloth 修改器的车衣网格")


def _top_faces(obj):
    group = obj.vertex_groups.get("PANEL_TOP")
    if group is None:
        raise RuntimeError("缺少 PANEL_TOP 顶点组")
    vertices = {
        v.index for v in obj.data.vertices
        if any(g.group == group.index and g.weight > 0.001 for g in v.groups)
    }
    faces = [p for p in obj.data.polygons if all(i in vertices for i in p.vertices)]
    if not faces:
        raise RuntimeError("PANEL_TOP 没有完整的布料面")
    return faces



def _plate_color(config):
    color_hex = config.get("color_hex")
    if color_hex is None:
        return tuple(config["color_rgba"])
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", color_hex.strip())
    if not match:
        raise ValueError("颜色色值须为 #RRGGBB 或 #RRGGBBAA")
    channels = [int(match.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                for c in channels)
    alpha = int(match.group(2), 16) / 255 if match.group(2) else 1.0
    return (*rgb, alpha)


def apply_plate_marks(cloth=None, config=None):
    config = dict(PLATES_CONFIG if config is None else config)
    for key in ("front_distance_mm", "rear_distance_mm"):
        if float(config[key]) < 0:
            raise ValueError(f"{key} 不能小于零")
    for key in ("length_mm", "width_mm"):
        if float(config[key]) <= 0:
            raise ValueError(f"{key} 必须大于零")
    axis = config["front_axis"].upper()
    if axis not in ("-X", "+X", "-Y", "+Y"):
        raise ValueError("front_axis 必须是 ±X 或 ±Y")
    longitudinal = 0 if axis.endswith("X") else 1
    transverse = 1 - longitudinal
    color = _plate_color(config)
    cloth = cloth or _active_cloth()
    faces = _top_faces(cloth)
    world = mark_evaluated_vertices(cloth)
    indices = {i for face in faces for i in face.vertices}
    positions = [world[i][longitudinal] for i in indices]
    cross_positions = [world[i][transverse] for i in indices]
    low, high = min(positions), max(positions)
    front = high if axis.startswith("+") else low
    rear = low if axis.startswith("+") else high
    direction = -1 if axis.startswith("+") else 1
    mid_cross = (min(cross_positions) + max(cross_positions)) / 2
    half_length = float(config["length_mm"]) / 2000
    half_width = float(config["width_mm"]) / 2000
    # The UI distance is an edge gap, rather than a distance to the center.
    centers = [
        front + direction * (float(config["front_distance_mm"]) / 1000 + half_length),
    ]
    if not config.get("front_only", False):
        centers.append(
            rear - direction * (float(config["rear_distance_mm"]) / 1000 + half_length)
        )
    for center in centers:
        if center - half_length < low or center + half_length > high:
            raise ValueError("矩形超出 PANEL_TOP 前后范围；请调整距离或长度")
    if mid_cross - half_width < min(cross_positions) or mid_cross + half_width > max(cross_positions):
        raise ValueError("矩形宽度超出 PANEL_TOP 横向范围")

    # Both rectangles share one mark. Every corner of a face is measured from
    # the rectangle nearer to that face, so each face interpolates one frame.
    mesh = cloth.data
    values = [MARK_OUTSIDE] * (len(mesh.loops) * 2)
    marks = [set() for _ in centers]
    for face in faces:
        mean = sum(world[i][longitudinal] for i in face.vertices) / len(face.vertices)
        nearest = min(range(len(centers)), key=lambda item: abs(mean - centers[item]))
        for loop_index in face.loop_indices:
            point = world[mesh.loops[loop_index].vertex_index]
            values[loop_index * 2] = (point[longitudinal] - centers[nearest]) / half_length
            values[loop_index * 2 + 1] = (point[transverse] - mid_cross) / half_width
        if mark_touches(values, face.loop_indices):
            marks[nearest].add(face.index)
    if any(not marked_faces for marked_faces in marks):
        raise RuntimeError("矩形没有覆盖布料面；请增大长宽或检查车头方向")

    mark_write(cloth, PLATES_MARK_KIND, values, color)
    mark_rebuild(cloth)
    marked = set().union(*marks)
    cloth[FACES_KEY] = ",".join(map(str, sorted(marked)))
    cloth["cc_plates_front_distance_mm"] = float(config["front_distance_mm"])
    cloth["cc_plates_rear_distance_mm"] = float(config["rear_distance_mm"])
    cloth["cc_plates_length_mm"] = float(config["length_mm"])
    cloth["cc_plates_width_mm"] = float(config["width_mm"])
    cloth["cc_plates_front_only"] = bool(config.get("front_only", False))
    counts = f"{len(marks[0])} front faces"
    if len(marks) > 1:
        counts += f", {len(marks[1])} rear faces"
    print(f"Plate opening mockups: {counts}")
    return marks




class CC_OT_setup_plates_maker(bpy.types.Operator):
    bl_idname = "cc.setup_plates_maker"
    bl_label = "车牌开孔模拟标记"
    bl_options = {"REGISTER", "UNDO"}

    def draw(self, context):
        wm = context.window_manager
        self.layout.prop(wm, "cc_plates_front_axis")
        self.layout.prop(wm, "cc_plates_front_only")
        self.layout.prop(wm, "cc_plates_front_distance_mm")
        if not wm.cc_plates_front_only:
            self.layout.prop(wm, "cc_plates_rear_distance_mm")
        for name in ("length_mm", "width_mm"):
            self.layout.prop(wm, "cc_plates_" + name)
        self.layout.prop(wm, "cc_plates_color_hex")

    def execute(self, context):
        wm = context.window_manager
        config = dict(PLATES_CONFIG)
        for name in ("front_axis", "front_distance_mm", "rear_distance_mm", "length_mm", "width_mm"):
            config[name] = getattr(wm, "cc_plates_" + name)
        config["front_only"] = wm.cc_plates_front_only
        config["color_hex"] = wm.cc_plates_color_hex
        try:
            marks = apply_plate_marks(config=config)
        except (RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        marked = set().union(*marks)
        label = "车头矩形" if len(marks) == 1 else "前后两个矩形"
        mark_show_solid_texture(context)
        self.report({"INFO"}, f"已标记{label}，共 {len(marked)} 个面")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)


def launch_plates_dialog():
    previous = getattr(bpy.types, CC_OT_setup_plates_maker.__name__, None)
    if previous is not None:
        bpy.utils.unregister_class(previous)
    wm = bpy.types.WindowManager
    wm.cc_plates_front_axis = bpy.props.EnumProperty(
        name="车头方向", items=(("-Y", "-Y", ""), ("+Y", "+Y", ""),
                              ("-X", "-X", ""), ("+X", "+X", "")),
        default=PLATES_CONFIG["front_axis"],
    )
    wm.cc_plates_front_only = bpy.props.BoolProperty(
        name="仅添加车头矩形",
        description="启用后不添加车尾矩形",
        default=PLATES_CONFIG["front_only"],
    )
    for key, label in (
        ("front_distance_mm", "车头端净距 (mm)"),
        ("rear_distance_mm", "车尾端净距 (mm)"),
        ("length_mm", "矩形长度 (mm)"),
        ("width_mm", "矩形宽度 (mm)"),
    ):
        setattr(wm, "cc_plates_" + key, bpy.props.FloatProperty(
            name=label,
            min=0.0 if "distance" in key else 1.0,
            default=PLATES_CONFIG[key],
        ))
    wm.cc_plates_color_hex = bpy.props.StringProperty(
        name="颜色色值", description="十六进制颜色，例如 #FF6600", default=PLATES_CONFIG["color_hex"])
    bpy.utils.register_class(CC_OT_setup_plates_maker)
    if bpy.app.background:
        return apply_plate_marks()
    return bpy.ops.cc.setup_plates_maker("INVOKE_DEFAULT")


if __name__ == "__main__":
    launch_plates_dialog()
