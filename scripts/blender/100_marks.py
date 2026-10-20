"""Add non-physical reference marks to a settled car cover from one dialog.

Replaces the former 100_mirror_marks.py, 101_door_marks.py and
102_plate_marks.py. Every mark can be switched on or off in the dialog:

* mirror: half-ellipse mirror pocket on PANEL_LEFT and PANEL_RIGHT, with a
  text label below each one recording every mark setting on the cloth;
* charge_port: rectangle on one side panel;
* door: vertical line on both side panels;
* plates: front/rear plate-opening rectangles on PANEL_TOP.

Usage in Blender:
1. Go to the settled comparison frame.
2. Select one or more car-cover meshes; every selected Cloth mesh is marked
   with the same settings (only the active one when none is selected).
3. Ensure it has PANEL_LEFT and PANEL_RIGHT vertex groups (and PANEL_TOP for
   plates) from the semantic SVG.
4. Run this script, adjust the dialog and press OK. Re-running replaces the
   enabled marks and removes the switched-off ones. The dialog opens with the
   settings last applied to the active cloth (stored in ``cc_marks_config``).
   A cloth that fails is reported and left unchanged; the others are marked.

The marks are drawn by the shared CC mark overlay scheme (see the block
below): at the settled frame each face corner stores its normalized position
inside the mark, so the shader draws exact edges that follow the cloth as it
deforms, and Solid view with Color = Texture shows the same shape. The seam
mark written by 003_cloth_setup.py is kept. Cloth is unaffected; the mirror
labels are separate Text objects placed at the settled frame.
"""

import bpy
import copy
import json
import re
from mathutils import Matrix, Vector


MARKS_CONFIG = {
    "front_axis": "-Y",
    "mirror": {
        "enabled": True,
        # Center of the rectangle enclosing the half ellipse (not the
        # ellipse center, which lies on the straight edge).
        "distance_from_front_mm": 1600.0,
        "height_from_bottom_mm": 1020.0,
        "width_mm": 430.0,  # straight edge length
        "height_mm": 300.0,  # straight edge to apex
        "flat_edge": "BOTTOM",  # BOTTOM: dome points up; TOP: dome points down
        "label": True,
        "label_size_mm": 40.0,
        "color_rgba": [1.0, 0.12, 0.015, 1.0],
    },
    "charge_port": {
        "enabled": True,
        "side": "PANEL_LEFT",
        "distance_from_rear_mm": 340.0,
        "height_from_bottom_mm": 820.0,
        "width_mm": 180.0,
        "height_mm": 160.0,
        "color_rgba": [0.02, 0.35, 1.0, 1.0],
    },
    "door": {
        "enabled": True,
        "distance_from_front_mm": 1800.0,
        "line_width_mm": 30.0,
        "color_rgba": [0.04, 0.9, 0.16, 1.0],
    },
    "plates": {
        "enabled": True,
        # Edge gaps from the PANEL_TOP ends, not distances to the centers.
        "front_distance_mm": 300.0,
        "rear_distance_mm": 300.0,
        "length_mm": 440.0,
        "width_mm": 140.0,
        "front_only": False,
        "color_hex": "#1C1C21",
    },
}

MARK_KINDS = ("mirror", "charge_port", "door", "plates")
CONFIG_PROPERTY = "cc_marks_config"
# Custom properties written for each mark; removed when the mark is disabled.
RECORD_PREFIXES = {
    "mirror": "cc_mirror_marker",
    "charge_port": "cc_charge_marker",
    "door": "cc_door_marker",
    "plates": "cc_plates_",
}
LABEL_COLLECTION = "CC Mark Labels"  # one per scene, see _label_collection()
LABEL_COLLECTION_PROPERTY = "cc_mark_label_collection"
LABEL_MATERIAL = "CC Mirror Label"
LABEL_OWNER_PROPERTY = "cc_mark_label_owner"
LABEL_SURFACE_OFFSET = 0.01  # m outside the settled cloth surface


# >>> CC MARK OVERLAY >>>
# Shared mark scheme. Keep this block identical in 100_marks.py and
# 003_cloth_setup.py so each script still runs on its own from Blender's Text
# Editor.
#
# A mark is a FLOAT2 face-corner attribute ``cc_mark_<kind>`` holding each
# corner's normalized position inside the mark's box (|u|, |v| < 1) plus a
# color and a shape stored in the object's ``cc_mark_colors`` and
# ``cc_mark_shapes`` properties. Shapes:
# * ``rect`` (default): the whole box, ``max(|u|, |v|) < 1``;
# * ``half_ellipse``: straight edge on v = -1, apex on v = 1,
#   ``v > -1 and u^2 + ((v + 1) / 2)^2 < 1``.
# mark_rebuild() derives everything else from those attributes, so any script
# can rebuild without losing the marks written by another:
# * faces touching a mark's box receive a copy of their base material whose
#   Base Color is overlaid by a per-pixel shape test for every mark, giving
#   exact edges that follow the Cloth deformation;
# * Solid view cannot run shader nodes, so each overlay material also holds an
#   unlinked, active Image Texture (Closest) whose centre texels draw the mark
#   shape, sampled through the active ``cc_mark_uv`` UV map.
# No geometry, mass, collision, constraints or modifiers are added.
MARK_ATTRIBUTE_PREFIX = "cc_mark_"
MARK_COLORS_PROPERTY = "cc_mark_colors"
MARK_SHAPES_PROPERTY = "cc_mark_shapes"
MARK_SHAPE_RECT = "rect"
MARK_SHAPE_HALF_ELLIPSE = "half_ellipse"
# Solid-image texels from the centre to the edge of the mark box: a rect needs
# only 2x2 texels for exact edges, a curve needs more to look smooth.
MARK_SOLID_HALF_TEXELS = {MARK_SHAPE_RECT: 1, MARK_SHAPE_HALF_ELLIPSE: 16}
MARK_OVERLAY_BASE_PROPERTY = "cc_marker_base_material"
MARK_OVERLAY_KIND_PROPERTY = "cc_marker_kind"
MARK_SOLID_UV_LAYER = "cc_mark_uv"
MARK_SOLID_TEXTURE_SIZE = 64
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


def mark_write(obj, kind, values, color, shape=MARK_SHAPE_RECT):
    """Store one mark: flat (u, v) pairs per face corner, RGBA color, shape."""
    if shape not in MARK_SOLID_HALF_TEXELS:
        raise ValueError(f"未知标记形状：{shape}")
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
    shapes = _mark_shapes(obj)
    shapes[kind] = shape
    obj[MARK_SHAPES_PROPERTY] = shapes


def mark_remove(obj, kind):
    attribute = obj.data.attributes.get(MARK_ATTRIBUTE_PREFIX + kind)
    if attribute is not None:
        obj.data.attributes.remove(attribute)
    colors = _mark_colors(obj)
    if colors.pop(kind, None) is not None:
        obj[MARK_COLORS_PROPERTY] = colors
    shapes = _mark_shapes(obj)
    if shapes.pop(kind, None) is not None:
        obj[MARK_SHAPES_PROPERTY] = shapes


def mark_touches(values, loop_indices):
    """True when the corner coordinates' bounding box meets the mark box."""
    us = [values[index * 2] for index in loop_indices]
    vs = [values[index * 2 + 1] for index in loop_indices]
    return min(us) <= 1.0 and max(us) >= -1.0 and min(vs) <= 1.0 and max(vs) >= -1.0


def mark_inside(u, v, shape):
    """Python twin of the shader test for one normalized point."""
    if shape == MARK_SHAPE_HALF_ELLIPSE:
        return v > -1.0 and u * u + ((v + 1.0) * 0.5) ** 2 < 1.0
    return max(abs(u), abs(v)) < 1.0


def mark_rebuild(obj):
    """Reassign overlay materials and the Solid-view UV map from all marks.

    Returns {polygon index: kind shown in Solid view}.
    """
    mesh = obj.data
    kinds = _mark_kinds(obj)
    shapes = _mark_shapes(obj)
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
                values[index * 2], values[index * 2 + 1], _mark_shape(shapes, kind)
            )
        key = (polygon.material_index, kind)
        if key not in overlays:
            base = mesh.materials[key[0]] if key[0] < len(mesh.materials) else None
            overlays[key] = _mark_material_slot(
                obj, _mark_overlay_material(obj, base, kinds, shapes, kind)
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


def _mark_shapes(obj):
    stored = obj.get(MARK_SHAPES_PROPERTY)
    if not hasattr(stored, "items"):
        return {}
    return {str(kind): str(shape) for kind, shape in stored.items()}


def _mark_shape(shapes, kind):
    shape = shapes.get(kind, MARK_SHAPE_RECT)
    return shape if shape in MARK_SOLID_HALF_TEXELS else MARK_SHAPE_RECT


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


def _mark_math(nodes, links, operation, inputs, location):
    node = nodes.new("ShaderNodeMath")
    node.operation = operation
    node.location = location
    for index, value in enumerate(inputs):
        if isinstance(value, (int, float)):
            node.inputs[index].default_value = value
        else:
            links.new(value, node.inputs[index])
    return node.outputs[0]


def _mark_mask_factor(nodes, links, attribute_name, shape, x, y):
    """Return a socket that is 1 inside the normalized mark shape, else 0."""
    attribute = nodes.new("ShaderNodeAttribute")
    attribute.attribute_type = "GEOMETRY"
    attribute.attribute_name = attribute_name
    attribute.location = (x, y)
    separate = nodes.new("ShaderNodeSeparateXYZ")
    separate.location = (x + 180, y)
    links.new(attribute.outputs["Vector"], separate.inputs[0])
    u, v = separate.outputs["X"], separate.outputs["Y"]
    if shape == MARK_SHAPE_HALF_ELLIPSE:
        rise = _mark_math(nodes, links, "MULTIPLY_ADD", (v, 0.5, 0.5), (x + 360, y - 160))
        u_squared = _mark_math(nodes, links, "MULTIPLY", (u, u), (x + 360, y))
        rise_squared = _mark_math(nodes, links, "MULTIPLY", (rise, rise), (x + 540, y - 160))
        radius = _mark_math(nodes, links, "ADD", (u_squared, rise_squared), (x + 540, y))
        within = _mark_math(nodes, links, "LESS_THAN", (radius, 1.0), (x + 720, y))
        above = _mark_math(nodes, links, "GREATER_THAN", (v, -1.0), (x + 720, y - 160))
        return _mark_math(nodes, links, "MULTIPLY", (within, above), (x + 900, y))
    absolute_u = _mark_math(nodes, links, "ABSOLUTE", (u,), (x + 360, y))
    absolute_v = _mark_math(nodes, links, "ABSOLUTE", (v,), (x + 360, y - 160))
    largest = _mark_math(nodes, links, "MAXIMUM", (absolute_u, absolute_v), (x + 540, y))
    return _mark_math(nodes, links, "LESS_THAN", (largest, 1.0), (x + 720, y))


def _mark_solid_image(name, base_color, mark_color, shape):
    """Image whose centre texels draw the mark shape, sampled with Closest."""
    size = MARK_SOLID_TEXTURE_SIZE
    half = MARK_SOLID_HALF_TEXELS[shape]
    centre = size // 2
    # Always start fresh: re-packing an already packed image after editing its
    # pixels can store stale data.
    previous = bpy.data.images.get(name)
    if previous is not None:
        bpy.data.images.remove(previous)
    image = bpy.data.images.new(name, size, size, alpha=False, float_buffer=True)
    pixels = [float(base_color[0]), float(base_color[1]), float(base_color[2]), 1.0] * (size * size)
    mark = [float(mark_color[0]), float(mark_color[1]), float(mark_color[2]), 1.0]
    for y in range(centre - half, centre + half):
        for x in range(centre - half, centre + half):
            if mark_inside((x + 0.5 - centre) / half, (y + 0.5 - centre) / half, shape):
                start = (y * size + x) * 4
                pixels[start:start + 4] = mark
    image.pixels.foreach_set(pixels)
    image.pack()  # generated images are otherwise lost when the .blend is saved
    return image


def _mark_solid_uv(u, v, shape):
    # Maps |u|, |v| <= 1 exactly onto the centre texels of the Solid image.
    scale = MARK_SOLID_HALF_TEXELS[shape] / float(MARK_SOLID_TEXTURE_SIZE)
    return 0.5 + u * scale, 0.5 + v * scale


def _mark_overlay_material(obj, base, kinds, shapes, kind):
    """Copy ``base`` and overlay every mark mask on its Base Color.

    The name carries the object: objects sharing a base material can hold
    different marks, and a shared overlay would be replaced by the last
    rebuild.
    """
    base_name = base.name if base is not None else ""
    label = kind.replace("_", " ").title()
    name = f"{base_name or MARK_BASE_MATERIAL} + CC {label} Mark ({obj.name})"
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

    x = principled.location.x - 1600
    for row, (mask_kind, mask_color) in enumerate(kinds.items()):
        y = principled.location.y + 200 - row * 400
        factor = _mark_mask_factor(
            nodes, links, MARK_ATTRIBUTE_PREFIX + mask_kind,
            _mark_shape(shapes, mask_kind), x, y,
        )
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
    preview.image = _mark_solid_image(name, solid_base, kinds[kind], _mark_shape(shapes, kind))
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


# ---------------------------------------------------------------- geometry


def _is_cloth(obj):
    return obj.type == "MESH" and any(mod.type == "CLOTH" for mod in obj.modifiers)


def _active_cloth():
    active = bpy.context.view_layer.objects.active
    if active and _is_cloth(active):
        return active
    selected = [obj for obj in bpy.context.selected_objects if _is_cloth(obj)]
    if len(selected) == 1:
        return selected[0]
    raise RuntimeError("请激活唯一的 Cloth 网格后再运行标记脚本。")


def target_cloths(context=None):
    """Selected Cloth meshes, active first; the active one if none is selected."""
    context = context or bpy.context
    active = context.view_layer.objects.active
    cloths = sorted(
        (obj for obj in context.selected_objects if _is_cloth(obj)),
        key=lambda obj: (obj != active, obj.name),
    )
    if not cloths and active is not None and _is_cloth(active):
        cloths = [active]
    if not cloths:
        raise RuntimeError("请选中至少一个带 Cloth 修改器的网格后再运行标记脚本。")
    return cloths


def _front_axis(config):
    axis = str(config["front_axis"]).upper()
    if axis not in {"+X", "-X", "+Y", "-Y"}:
        raise ValueError("front_axis 必须为 '+X'、'-X'、'+Y' 或 '-Y'。")
    return axis, 0 if axis.endswith("X") else 1


def _bounds(points):
    return (
        Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))),
        Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))),
    )


class _Panels:
    """Lazily collected vertex/face sets and evaluated bounds per panel."""

    def __init__(self, obj, world):
        self.obj = obj
        self.world = world
        self._cache = {}

    def __getitem__(self, name):
        if name not in self._cache:
            self._cache[name] = self._collect(name)
        return self._cache[name]

    def _collect(self, name):
        obj = self.obj
        group = obj.vertex_groups.get(name)
        if group is None:
            raise RuntimeError(
                f"缺少 {name} 顶点组；请先运行 002_sew_from_svg.py "
                "从语义 SVG 创建 PANEL 顶点组。"
            )
        vertices = {
            vertex.index
            for vertex in obj.data.vertices
            if any(item.group == group.index and item.weight > 0.001 for item in vertex.groups)
        }
        if not vertices:
            raise RuntimeError(f"{name} 顶点组为空。")
        polygons = [
            polygon.index
            for polygon in obj.data.polygons
            if all(index in vertices for index in polygon.vertices)
        ]
        if not polygons:
            raise RuntimeError(f"{name} 没有包含任何完整布料面。")
        return {
            "vertices": vertices,
            "polygons": polygons,
            "bounds": _bounds([self.world[index] for index in vertices]),
        }


def _side_target(bounds, axis, distance_mm, from_front, height_mm):
    """Point at a longitudinal distance from the front/rear and a height."""
    low, high = bounds
    longitudinal = 0 if axis.endswith("X") else 1
    front_is_high = axis.startswith("+")
    use_high = front_is_high if from_front else not front_is_high
    distance = float(distance_mm) / 1000.0
    result = (low + high) * 0.5
    result[longitudinal] = high[longitudinal] - distance if use_high else low[longitudinal] + distance
    result.z = low.z + float(height_mm) / 1000.0
    return result


def _panel_values(cloth, world, panels, label, targets, coordinates):
    """Corner coordinates of one mark over its panels.

    ``targets`` is [(panel name, target)]; ``coordinates(point, target)``
    returns the normalized (u, v). Returns (values, marked face indices).
    """
    mesh = cloth.data
    values = [MARK_OUTSIDE] * (len(mesh.loops) * 2)
    faces = set()
    for panel_name, target in targets:
        selected = 0
        for index in panels[panel_name]["polygons"]:
            polygon = mesh.polygons[index]
            for loop_index in polygon.loop_indices:
                point = world[mesh.loops[loop_index].vertex_index]
                values[loop_index * 2:loop_index * 2 + 2] = coordinates(point, target)
            if mark_touches(values, polygon.loop_indices):
                faces.add(index)
                selected += 1
        if not selected:
            raise RuntimeError(
                f"{label}在 {panel_name} 范围内没有布料面；请确认当前帧已经完成落罩，"
                "并检查车头方向、位置及尺寸。"
            )
    return values, faces


def _charge_panel_name(side):
    value = str(side).upper()
    if value in {"PANEL_LEFT", "LEFT", "-LATERAL"}:
        return "PANEL_LEFT"
    if value in {"PANEL_RIGHT", "RIGHT", "+LATERAL"}:
        return "PANEL_RIGHT"
    raise ValueError("charge_port.side 必须为 PANEL_LEFT 或 PANEL_RIGHT。")


def _flat_edge(mirror):
    value = str(mirror.get("flat_edge", "BOTTOM")).upper()
    if value not in {"BOTTOM", "TOP"}:
        raise ValueError("mirror.flat_edge 必须为 BOTTOM 或 TOP。")
    return value


def _plate_color(config):
    color_hex = config.get("color_hex")
    if color_hex is None:
        return tuple(config["color_rgba"])
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", color_hex.strip())
    if not match:
        raise ValueError("车牌颜色色值须为 #RRGGBB 或 #RRGGBBAA")
    channels = [int(match.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                for c in channels)
    alpha = int(match.group(2), 16) / 255 if match.group(2) else 1.0
    return (*rgb, alpha)


# ------------------------------------------------------------------- marks
# Each _*_mark() only computes; apply_marks() writes once everything succeeded,
# so an error never leaves half of the marks updated.


def _mirror_mark(cloth, world, panels, config):
    mirror = config["mirror"]
    axis, longitudinal = _front_axis(config)
    half_width = max(float(mirror["width_mm"]) / 2000.0, 1.0e-6)
    half_height = max(float(mirror["height_mm"]) / 2000.0, 1.0e-6)
    upward = _flat_edge(mirror) == "BOTTOM"
    targets = [
        (name, _side_target(
            panels[name]["bounds"], axis, mirror["distance_from_front_mm"], True,
            mirror["height_from_bottom_mm"],
        ))
        for name in ("PANEL_LEFT", "PANEL_RIGHT")
    ]

    def coordinates(point, target):
        # ``target`` is the center of the enclosing rectangle: straight edge
        # on v = -1, apex on v = 1.
        rise = point.z - target.z if upward else target.z - point.z
        return (
            (point[longitudinal] - target[longitudinal]) / half_width,
            rise / half_height,
        )

    values, faces = _panel_values(cloth, world, panels, "后视镜耳位", targets, coordinates)
    return {
        "values": values,
        "faces": faces,
        "color": mirror["color_rgba"],
        "shape": MARK_SHAPE_HALF_ELLIPSE,
        "targets": targets,
    }


def _charge_mark(cloth, world, panels, config):
    charge = config["charge_port"]
    axis, longitudinal = _front_axis(config)
    half_width = max(float(charge["width_mm"]) / 2000.0, 1.0e-6)
    half_height = max(float(charge["height_mm"]) / 2000.0, 1.0e-6)
    panel_name = _charge_panel_name(charge["side"])
    targets = [(panel_name, _side_target(
        panels[panel_name]["bounds"], axis, charge["distance_from_rear_mm"], False,
        charge["height_from_bottom_mm"],
    ))]

    def coordinates(point, target):
        # ``target`` is the rectangle center.
        return (
            (point[longitudinal] - target[longitudinal]) / half_width,
            (point.z - target.z) / half_height,
        )

    values, faces = _panel_values(cloth, world, panels, "充电口", targets, coordinates)
    return {"values": values, "faces": faces, "color": charge["color_rgba"],
            "shape": MARK_SHAPE_RECT, "panel": panel_name}


def _door_mark(cloth, world, panels, config):
    door = config["door"]
    axis, longitudinal = _front_axis(config)
    names = ("PANEL_LEFT", "PANEL_RIGHT")
    coordinates_along = [
        world[index][longitudinal] for name in names for index in panels[name]["vertices"]
    ]
    front = max(coordinates_along) if axis.startswith("+") else min(coordinates_along)
    direction = -1.0 if axis.startswith("+") else 1.0
    position = front + direction * float(door["distance_from_front_mm"]) / 1000.0
    half_width = max(float(door["line_width_mm"]) / 2000.0, 1.0e-6)

    def coordinates(point, _target):
        # Unbounded vertically: u is the signed offset in half line widths.
        return (point[longitudinal] - position) / half_width, 0.0

    values, faces = _panel_values(
        cloth, world, panels, f"距车头 {door['distance_from_front_mm']:g} mm 的车门线",
        [(name, None) for name in names], coordinates,
    )
    return {"values": values, "faces": faces, "color": door["color_rgba"],
            "shape": MARK_SHAPE_RECT}


def _plates_mark(cloth, world, panels, config):
    plates = config["plates"]
    for key in ("front_distance_mm", "rear_distance_mm"):
        if float(plates[key]) < 0:
            raise ValueError(f"plates.{key} 不能小于零")
    for key in ("length_mm", "width_mm"):
        if float(plates[key]) <= 0:
            raise ValueError(f"plates.{key} 必须大于零")
    axis, longitudinal = _front_axis(config)
    transverse = 1 - longitudinal
    color = _plate_color(plates)
    top = panels["PANEL_TOP"]
    positions = [world[i][longitudinal] for i in top["vertices"]]
    cross_positions = [world[i][transverse] for i in top["vertices"]]
    low, high = min(positions), max(positions)
    front = high if axis.startswith("+") else low
    rear = low if axis.startswith("+") else high
    direction = -1 if axis.startswith("+") else 1
    mid_cross = (min(cross_positions) + max(cross_positions)) / 2
    half_length = float(plates["length_mm"]) / 2000
    half_width = float(plates["width_mm"]) / 2000
    # The distance is an edge gap, rather than a distance to the center.
    centers = [front + direction * (float(plates["front_distance_mm"]) / 1000 + half_length)]
    if not plates.get("front_only", False):
        centers.append(rear - direction * (float(plates["rear_distance_mm"]) / 1000 + half_length))
    for center in centers:
        if center - half_length < low or center + half_length > high:
            raise ValueError("车牌矩形超出 PANEL_TOP 前后范围；请调整距离或长度")
    if mid_cross - half_width < min(cross_positions) or mid_cross + half_width > max(cross_positions):
        raise ValueError("车牌矩形宽度超出 PANEL_TOP 横向范围")

    # Both rectangles share one mark. Every corner of a face is measured from
    # the rectangle nearer to that face, so each face interpolates one frame.
    mesh = cloth.data
    values = [MARK_OUTSIDE] * (len(mesh.loops) * 2)
    per_center = [set() for _ in centers]
    for index in top["polygons"]:
        face = mesh.polygons[index]
        mean = sum(world[i][longitudinal] for i in face.vertices) / len(face.vertices)
        nearest = min(range(len(centers)), key=lambda item: abs(mean - centers[item]))
        for loop_index in face.loop_indices:
            point = world[mesh.loops[loop_index].vertex_index]
            values[loop_index * 2] = (point[longitudinal] - centers[nearest]) / half_length
            values[loop_index * 2 + 1] = (point[transverse] - mid_cross) / half_width
        if mark_touches(values, face.loop_indices):
            per_center[nearest].add(index)
    if any(not faces for faces in per_center):
        raise RuntimeError("车牌矩形没有覆盖布料面；请增大长宽或检查车头方向")
    return {"values": values, "faces": set().union(*per_center), "color": color,
            "shape": MARK_SHAPE_RECT}


MARK_BUILDERS = {
    "mirror": _mirror_mark,
    "charge_port": _charge_mark,
    "door": _door_mark,
    "plates": _plates_mark,
}


# ------------------------------------------------------------ mirror labels


def mirror_label_text(mirror, side=""):
    """Mirror positioning record (the first lines of marks_label_text)."""
    name = f"MIRROR {side}".rstrip()
    return (
        f"{name}  X {float(mirror['distance_from_front_mm']):g}  "
        f"Y {float(mirror['height_from_bottom_mm']):g}\n"
        f"W {float(mirror['width_mm']):g} x H {float(mirror['height_mm']):g} mm  "
        f"FLAT {str(mirror.get('flat_edge', 'BOTTOM')).upper()}"
    )


def marks_label_text(config, side=""):
    """Every mark setting, shown below each mirror mark and in the dialog.

    Sections missing from ``config`` are left out; switched-off ones read OFF.
    ASCII only: Blender's built-in font has no CJK glyphs.
    """
    def mm(section, key):
        return f"{float(section[key]):g}"

    lines = [mirror_label_text(config["mirror"], side)]
    charge = config.get("charge_port")
    if charge is not None:
        if charge.get("enabled", True):
            lines.append(
                f"CHARGE {str(charge['side']).upper()}  REAR X {mm(charge, 'distance_from_rear_mm')}  "
                f"Y {mm(charge, 'height_from_bottom_mm')}\n"
                f"W {mm(charge, 'width_mm')} x H {mm(charge, 'height_mm')} mm"
            )
        else:
            lines.append("CHARGE OFF")
    door = config.get("door")
    if door is not None:
        if door.get("enabled", True):
            lines.append(
                f"DOOR  X {mm(door, 'distance_from_front_mm')}  LINE {mm(door, 'line_width_mm')} mm"
            )
        else:
            lines.append("DOOR OFF")
    plates = config.get("plates")
    if plates is not None:
        if not plates.get("enabled", True):
            lines.append("PLATES OFF")
        elif plates.get("front_only", False):
            lines.append(f"PLATES  FRONT {mm(plates, 'front_distance_mm')}  (FRONT ONLY)")
        else:
            lines.append(
                f"PLATES  FRONT {mm(plates, 'front_distance_mm')}  "
                f"REAR {mm(plates, 'rear_distance_mm')}"
            )
        if plates.get("enabled", True):
            lines.append(
                f"L {mm(plates, 'length_mm')} x W {mm(plates, 'width_mm')} mm  "
                f"{plates.get('color_hex', '')}".rstrip()
            )
    lines.append(f"FRONT AXIS {config.get('front_axis', MARKS_CONFIG['front_axis'])}")
    return "\n".join(lines)


def _remove_labels(cloth):
    for obj in list(bpy.data.objects):
        if obj.get(LABEL_OWNER_PROPERTY) == cloth.name:
            curve = obj.data
            bpy.data.objects.remove(obj)
            if curve is not None and curve.users == 0:
                bpy.data.curves.remove(curve)


def _scenes_using(collection):
    return [
        scene for scene in bpy.data.scenes
        if collection in scene.collection.children_recursive
    ]


def _is_label_collection(collection):
    # Untagged "CC Mark Labels[.001]" collections come from earlier versions
    # (the suffix from a Full Copy of the scene).
    return bool(collection.get(LABEL_COLLECTION_PROPERTY)) or re.fullmatch(
        re.escape(LABEL_COLLECTION) + r"(\.\d{3,})?", collection.name
    ) is not None


def _new_label_collection(scene):
    """A fresh label collection linked to ``scene`` only.

    The plain name goes to the first scene; a later scene finding it taken
    gets a name carrying the scene, so no two scenes share one collection.
    """
    name = LABEL_COLLECTION
    if bpy.data.collections.get(name) is not None:
        name = f"{LABEL_COLLECTION} ({scene.name})"
    collection = bpy.data.collections.new(name)
    collection[LABEL_COLLECTION_PROPERTY] = True
    scene.collection.children.link(collection)
    return collection


def _label_collection(scene=None):
    """The current scene's own label collection, never shared with another.

    Earlier versions looked the collection up by name across the file and
    linked it into every scene that ran the script. A collection found shared
    is unlinked from this scene, and this scene's labels move to a new one.
    """
    scene = scene or bpy.context.scene
    root = scene.collection
    found = [item for item in root.children_recursive if _is_label_collection(item)]
    collection = next((item for item in found if _scenes_using(item) == [scene]), None)
    if collection is None:
        collection = _new_label_collection(scene)
    collection[LABEL_COLLECTION_PROPERTY] = True

    for shared in found:
        others = [other for other in _scenes_using(shared) if other != scene]
        if shared == collection or not others:
            continue
        for label in list(shared.objects):
            owner = bpy.data.objects.get(label.get(LABEL_OWNER_PROPERTY, ""))
            if owner is None or scene not in owner.users_scene:
                continue
            if label.name not in collection.objects:
                collection.objects.link(label)
            # A cloth also present in another scene keeps its label there.
            if not any(other in owner.users_scene for other in others):
                shared.objects.unlink(label)
        # Unlink only from parents this scene owns; a parent shared with
        # another scene would take the collection away from that scene too.
        for parent in [root, *root.children_recursive]:
            if shared.name in parent.children and (
                parent == root or _scenes_using(parent) == [scene]
            ):
                parent.children.unlink(shared)
    return collection


def _label_material(color):
    material = bpy.data.materials.get(LABEL_MATERIAL) or bpy.data.materials.new(LABEL_MATERIAL)
    material.diffuse_color = tuple(color)
    material.use_nodes = True
    principled = _mark_principled(material)
    if principled is not None:
        principled.inputs["Base Color"].default_value = tuple(color)
    return material


def _add_mirror_labels(cloth, world, panels, config, targets, label_config):
    """Text below each mirror mark, facing outward from its side panel.

    ``label_config`` is every setting stored on the cloth (marks_label_text).
    """
    mirror = config["mirror"]
    text_lines = marks_label_text(label_config).count("\n") + 1
    _, longitudinal = _front_axis(config)
    lateral = 1 - longitudinal
    size = max(float(mirror.get("label_size_mm", 40.0)) / 1000.0, 1.0e-3)
    half_width = float(mirror["width_mm"]) / 2000.0
    half_height = float(mirror["height_mm"]) / 2000.0
    centers = {
        name: (panels[name]["bounds"][0][lateral] + panels[name]["bounds"][1][lateral]) * 0.5
        for name in ("PANEL_LEFT", "PANEL_RIGHT")
    }
    middle = sum(centers.values()) * 0.5
    collection = _label_collection()
    material = _label_material(mirror["color_rgba"])
    labels = []
    for panel_name, target in targets:
        sign = 1.0 if centers[panel_name] >= middle else -1.0
        mark_bottom = target.z - half_height
        top = mark_bottom - size * 0.5
        # Sit just outside the settled cloth around the text area.
        nearby = [
            sign * world[index][lateral]
            for index in panels[panel_name]["vertices"]
            if abs(world[index][longitudinal] - target[longitudinal]) <= half_width
            and top - size * (text_lines + 1.0) <= world[index].z <= mark_bottom
        ] or [sign * world[index][lateral] for index in panels[panel_name]["vertices"]]
        location = target.copy()
        location.z = top
        location[lateral] = sign * (max(nearby) + LABEL_SURFACE_OFFSET)

        normal = Vector((0.0, 0.0, 0.0))
        normal[lateral] = sign
        up = Vector((0.0, 0.0, 1.0))
        right = (-normal).cross(up)  # reading direction seen from outside
        matrix = Matrix((right, up, normal)).transposed().to_4x4()
        matrix.translation = location

        side = "L" if panel_name == "PANEL_LEFT" else "R"
        name = f"{cloth.name} Mirror Label {side}"
        curve = bpy.data.curves.new(name, type="FONT")
        curve.body = marks_label_text(label_config, side)
        curve.size = size
        curve.align_x = "CENTER"
        curve.align_y = "TOP"
        curve.materials.append(material)
        label = bpy.data.objects.new(name, curve)
        collection.objects.link(label)
        label.matrix_world = matrix
        label[LABEL_OWNER_PROPERTY] = cloth.name
        labels.append(label)
    return labels


# ------------------------------------------------------------------- apply


def _merged_config(config):
    """MARKS_CONFIG overlaid with a (possibly partial) config."""
    result = copy.deepcopy(MARKS_CONFIG)
    for key, value in (config or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key].update(copy.deepcopy(value))
        else:
            result[key] = copy.deepcopy(value)
    return result


def _clear_records(cloth, kind):
    for key in [key for key in cloth.keys() if key.startswith(RECORD_PREFIXES[kind])]:
        del cloth[key]


def _write_records(cloth, kind, config, result):
    faces = ",".join(str(index) for index in sorted(result["faces"]))
    if kind == "mirror":
        mirror = config["mirror"]
        cloth["cc_mirror_marker"] = faces
        cloth["cc_mirror_marker_coordinate_source"] = "evaluated_panel_left_right_bounds_corner_uv"
        cloth["cc_mirror_marker_shape"] = f"half_ellipse_flat_{_flat_edge(mirror).lower()}"
        cloth["cc_mirror_marker_front_offset_mm"] = float(mirror["distance_from_front_mm"])
        cloth["cc_mirror_marker_height_mm"] = float(mirror["height_from_bottom_mm"])
        cloth["cc_mirror_marker_size_mm"] = [float(mirror["width_mm"]), float(mirror["height_mm"])]
        cloth["cc_mirror_marker_info"] = mirror_label_text(mirror).replace("\n", "  ")
    elif kind == "charge_port":
        charge = config["charge_port"]
        cloth["cc_charge_marker_faces"] = faces
        cloth["cc_charge_marker_panel"] = result["panel"]
        cloth["cc_charge_marker_rear_offset_mm"] = float(charge["distance_from_rear_mm"])
        cloth["cc_charge_marker_height_mm"] = float(charge["height_from_bottom_mm"])
        cloth["cc_charge_marker_size_mm"] = [float(charge["width_mm"]), float(charge["height_mm"])]
    elif kind == "door":
        door = config["door"]
        cloth["cc_door_marker_faces"] = faces
        cloth["cc_door_marker_coordinate_source"] = "evaluated_panel_left_right_front_bound_corner_uv"
        cloth["cc_door_marker_front_offset_mm"] = float(door["distance_from_front_mm"])
        cloth["cc_door_marker_line_width_mm"] = float(door["line_width_mm"])
    elif kind == "plates":
        plates = config["plates"]
        cloth["cc_plates_faces"] = faces
        for key in ("front_distance_mm", "rear_distance_mm", "length_mm", "width_mm"):
            cloth["cc_plates_" + key] = float(plates[key])
        cloth["cc_plates_front_only"] = bool(plates.get("front_only", False))


def apply_marks(cloth=None, config=None, kinds=MARK_KINDS):
    """Write the enabled marks of ``kinds``, remove the disabled ones.

    Marks outside ``kinds`` are left untouched. Returns {kind: face count}.
    """
    config = _merged_config(config)
    _front_axis(config)
    cloth = cloth or _active_cloth()
    world = mark_evaluated_vertices(cloth)
    panels = _Panels(cloth, world)
    results = {
        kind: MARK_BUILDERS[kind](cloth, world, panels, config)
        for kind in kinds if config[kind].get("enabled", True)
    }

    for kind in kinds:
        if kind in results:
            result = results[kind]
            mark_write(cloth, kind, result["values"], result["color"], result["shape"])
        else:
            mark_remove(cloth, kind)
    mark_rebuild(cloth)

    for kind in kinds:
        _clear_records(cloth, kind)
        if kind in results:
            _write_records(cloth, kind, config, results[kind])
    stored = _stored_config(cloth)
    stored["front_axis"] = config["front_axis"]
    for kind in kinds:
        stored[kind] = config[kind]
    cloth[CONFIG_PROPERTY] = json.dumps(stored, ensure_ascii=False)

    if "mirror" in kinds:
        _remove_labels(cloth)
        if "mirror" in results and config["mirror"].get("label", True):
            # Marks outside ``kinds`` show their stored settings; marks never
            # applied to this cloth are left off the label.
            merged = _merged_config(stored)
            label_config = {key: merged[key] for key in stored if key in merged}
            _add_mirror_labels(
                cloth, world, panels, config, results["mirror"]["targets"], label_config
            )

    counts = {kind: len(result["faces"]) for kind, result in results.items()}
    disabled = [kind for kind in kinds if kind not in results]
    print(f"CC marks: cloth={cloth.name}, faces={counts}, removed={disabled}")
    if "mirror" in results:
        print("  " + mirror_label_text(config["mirror"]).replace("\n", "  "))
    return counts


def apply_marks_to_cloths(cloths, config=None, kinds=MARK_KINDS):
    """apply_marks() on each cloth; a failure skips only that cloth.

    Returns ({cloth name: {kind: face count}}, {cloth name: error message}).
    """
    done, failed = {}, {}
    for cloth in cloths:
        try:
            done[cloth.name] = apply_marks(cloth, config, kinds)
        except (RuntimeError, ValueError) as error:
            failed[cloth.name] = str(error)
            print(f"CC marks: cloth={cloth.name} skipped: {error}")
    return done, failed


def apply_mirror_markers(cloth=None, config=None):
    """Mirror and charge-port marks only (config-driven entry point)."""
    return apply_marks(cloth, config, kinds=("mirror", "charge_port"))


def _stored_config(cloth):
    try:
        stored = json.loads(cloth.get(CONFIG_PROPERTY, "{}"))
    except (TypeError, ValueError):
        return {}
    return stored if isinstance(stored, dict) else {}


# ------------------------------------------------------------------ dialog

AXIS_ITEMS = (("-Y", "-Y", "Model X 默认"), ("+Y", "+Y", ""),
              ("-X", "-X", ""), ("+X", "+X", ""))
ENUM_ITEMS = {
    "front_axis": AXIS_ITEMS,
    "flat_edge": (("BOTTOM", "底边（向上拱）", "直边在下，半椭圆向上"),
                  ("TOP", "顶边（向下拱）", "直边在上，半椭圆向下")),
    "side": (("PANEL_LEFT", "PANEL_LEFT", "左侧版片"),
             ("PANEL_RIGHT", "PANEL_RIGHT", "右侧版片")),
}
# (WindowManager property suffix, config section or None, key, label)
SETTINGS_FIELDS = (
    ("front_axis", None, "front_axis", "车头方向"),
    ("mirror_enabled", "mirror", "enabled", "后视镜耳位（半椭圆）"),
    ("mirror_x_mm", "mirror", "distance_from_front_mm", "外接矩形中心距车头 X (mm)"),
    ("mirror_y_mm", "mirror", "height_from_bottom_mm", "外接矩形中心距底部 Y (mm)"),
    ("mirror_width_mm", "mirror", "width_mm", "宽 (mm)"),
    ("mirror_height_mm", "mirror", "height_mm", "高 (mm)"),
    ("mirror_flat_edge", "mirror", "flat_edge", "直边位置"),
    ("mirror_label", "mirror", "label", "在耳位下方标注定位信息"),
    ("mirror_label_size_mm", "mirror", "label_size_mm", "标注字高 (mm)"),
    ("charge_enabled", "charge_port", "enabled", "充电口"),
    ("charge_side", "charge_port", "side", "充电口版片"),
    ("charge_x_mm", "charge_port", "distance_from_rear_mm", "中心距车尾 X (mm)"),
    ("charge_y_mm", "charge_port", "height_from_bottom_mm", "中心距底部 Y (mm)"),
    ("charge_width_mm", "charge_port", "width_mm", "宽 (mm)"),
    ("charge_height_mm", "charge_port", "height_mm", "高 (mm)"),
    ("door_enabled", "door", "enabled", "车门线"),
    ("door_distance_mm", "door", "distance_from_front_mm", "距车头长度 (mm)"),
    ("door_width_mm", "door", "line_width_mm", "标记线宽 (mm)"),
    ("plates_enabled", "plates", "enabled", "车牌开孔"),
    ("plates_front_only", "plates", "front_only", "仅添加车头矩形"),
    ("plates_front_distance_mm", "plates", "front_distance_mm", "车头端净距 (mm)"),
    ("plates_rear_distance_mm", "plates", "rear_distance_mm", "车尾端净距 (mm)"),
    ("plates_length_mm", "plates", "length_mm", "矩形长度 (mm)"),
    ("plates_width_mm", "plates", "width_mm", "矩形宽度 (mm)"),
    ("plates_color_hex", "plates", "color_hex", "颜色色值"),
)
SETTINGS_PREFIX = "cc_marks_"


def _config_value(config, section, key):
    return config[key] if section is None else config[section][key]


def _register_settings():
    wm = bpy.types.WindowManager
    for suffix, section, key, label in SETTINGS_FIELDS:
        default = _config_value(MARKS_CONFIG, section, key)
        if key in ENUM_ITEMS:
            prop = bpy.props.EnumProperty(name=label, items=ENUM_ITEMS[key], default=default)
        elif isinstance(default, bool):
            prop = bpy.props.BoolProperty(name=label, default=default)
        elif isinstance(default, float):
            minimum = 0.0 if "distance" in key or "from" in key else 1.0
            prop = bpy.props.FloatProperty(name=label, min=minimum, default=default)
        else:
            prop = bpy.props.StringProperty(name=label, default=default)
        setattr(wm, SETTINGS_PREFIX + suffix, prop)


def _settings_to_config(wm):
    config = copy.deepcopy(MARKS_CONFIG)
    for suffix, section, key, _ in SETTINGS_FIELDS:
        value = getattr(wm, SETTINGS_PREFIX + suffix)
        if section is None:
            config[key] = value
        else:
            config[section][key] = value
    return config


def _config_to_settings(wm, config):
    config = _merged_config(config)
    try:
        config["charge_port"]["side"] = _charge_panel_name(config["charge_port"]["side"])
    except ValueError:
        pass
    for suffix, section, key, _ in SETTINGS_FIELDS:
        try:
            setattr(wm, SETTINGS_PREFIX + suffix, _config_value(config, section, key))
        except (TypeError, ValueError):
            pass  # keep the dialog value when a stored value no longer fits


class CC_OT_setup_marks(bpy.types.Operator):
    """在落罩后的车罩上生成后视镜耳位、充电口、车门线和车牌开孔标记"""

    bl_idname = "cc.setup_marks"
    bl_label = "车罩标记"
    bl_options = {"REGISTER", "UNDO"}

    def draw(self, context):
        wm = context.window_manager
        layout = self.layout

        def prop(container, suffix):
            container.prop(wm, SETTINGS_PREFIX + suffix)

        def section(enabled_suffix):
            box = layout.box()
            prop(box, enabled_suffix)
            column = box.column()
            column.active = getattr(wm, SETTINGS_PREFIX + enabled_suffix)
            return column

        try:
            names = [obj.name for obj in target_cloths(context)]
        except RuntimeError as error:
            layout.label(text=str(error), icon="ERROR")
        else:
            shown = "、".join(names[:4]) + (" 等" if len(names) > 4 else "")
            layout.label(text=f"将标记 {len(names)} 个物体：{shown}", icon="OBJECT_DATA")
        prop(layout, "front_axis")

        mirror = section("mirror_enabled")
        mirror.label(text="半椭圆外接矩形中心为定位点；宽为直边长，高为直边到顶点")
        prop(mirror, "mirror_x_mm")
        prop(mirror, "mirror_y_mm")
        row = mirror.row(align=True)
        prop(row, "mirror_width_mm")
        prop(row, "mirror_height_mm")
        prop(mirror, "mirror_flat_edge")
        row = mirror.row(align=True)
        prop(row, "mirror_label")
        sub = row.row(align=True)
        sub.active = wm.cc_marks_mirror_label
        prop(sub, "mirror_label_size_mm")
        for line in marks_label_text(_settings_to_config(wm)).splitlines():
            mirror.label(text=line, icon="INFO")

        charge = section("charge_enabled")
        charge.label(text="车尾底部端点为原点，坐标为矩形中心")
        prop(charge, "charge_side")
        prop(charge, "charge_x_mm")
        prop(charge, "charge_y_mm")
        row = charge.row(align=True)
        prop(row, "charge_width_mm")
        prop(row, "charge_height_mm")

        door = section("door_enabled")
        prop(door, "door_distance_mm")
        prop(door, "door_width_mm")

        plates = section("plates_enabled")
        prop(plates, "plates_front_only")
        prop(plates, "plates_front_distance_mm")
        if not wm.cc_marks_plates_front_only:
            prop(plates, "plates_rear_distance_mm")
        row = plates.row(align=True)
        prop(row, "plates_length_mm")
        prop(row, "plates_width_mm")
        prop(plates, "plates_color_hex")

    def execute(self, context):
        try:
            cloths = target_cloths(context)
        except RuntimeError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        done, failed = apply_marks_to_cloths(
            cloths, _settings_to_config(context.window_manager)
        )
        for name, message in failed.items():
            self.report({"WARNING"}, f"{name}：{message}")
        if not done:
            self.report({"ERROR"}, f"{len(failed)} 个物体全部标记失败，详见警告。")
            return {"CANCELLED"}
        mark_show_solid_texture(context)
        if len(done) == 1 and not failed:
            counts = next(iter(done.values()))
            summary = "，".join(f"{kind} {count} 面" for kind, count in counts.items()) or "无"
            self.report({"INFO"}, f"已生成标记：{summary}")
        else:
            self.report(
                {"WARNING" if failed else "INFO"},
                f"已标记 {len(done)} 个物体" + (f"，{len(failed)} 个失败" if failed else ""),
            )
        return {"FINISHED"}

    def invoke(self, context, event):
        # Start from the settings last applied to this cloth.
        active = context.view_layer.objects.active
        if active is not None and CONFIG_PROPERTY in active:
            _config_to_settings(context.window_manager, _stored_config(active))
        return context.window_manager.invoke_props_dialog(self, width=560)


def launch_marks_dialog():
    """Register safely on repeated Text Editor runs and open the dialog."""
    previous = getattr(bpy.types, CC_OT_setup_marks.__name__, None)
    if previous is not None:
        try:
            bpy.utils.unregister_class(previous)
        except RuntimeError:
            pass
    _register_settings()
    bpy.utils.register_class(CC_OT_setup_marks)
    if bpy.app.background:
        return apply_marks_to_cloths(target_cloths(), copy.deepcopy(MARKS_CONFIG))
    return bpy.ops.cc.setup_marks("INVOKE_DEFAULT")


if __name__ == "__main__":
    launch_marks_dialog()
