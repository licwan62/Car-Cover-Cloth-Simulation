"""Add reflective-strip marks to the side panels of a settled car cover.

A reflective strip is a rectangle, 250 x 50 mm by default, placed on
PANEL_LEFT, PANEL_RIGHT or both. It is positioned by its center:

* orientation: HORIZONTAL puts the long side along the car, VERTICAL puts it
  upright;
* height above the hem: measured from the settled HEM vertices of that panel
  next to the strip, so a hem that is not level does not shift the strip;
* distance from the front or the rear end of the same side panel.

Usage in Blender:
1. Go to the settled comparison frame.
2. Select one or more car-cover meshes; every selected Cloth mesh is marked
   with the same settings (only the active one when none is selected).
3. Ensure it has PANEL_LEFT / PANEL_RIGHT and HEM / HEM_* vertex groups from
   the semantic SVG (002_sew_from_svg.py). A panel without HEM vertices falls
   back to its lowest point.
4. Run this script, adjust the dialog and press OK. Re-running replaces the
   strip; switching it off removes it. The dialog opens with the settings last
   applied to the active cloth (stored in ``cc_reflective_config``).

The strip is drawn by the shared CC mark overlay scheme as mark kind
``reflective``, so it coexists with the marks of 100_marks.py and the seam
mark of 003_cloth_setup.py; re-running either script keeps it. Cloth is
unaffected.
"""

import bpy
import copy
import json
from mathutils import Vector


REFLECTIVE_CONFIG = {
    "front_axis": "-Y",
    "enabled": True,
    "sides": "BOTH",  # BOTH, PANEL_LEFT or PANEL_RIGHT
    "orientation": "HORIZONTAL",  # HORIZONTAL: long side along the car; VERTICAL: upright
    # Strip center: distance from the front/rear end of the side panel, and
    # height above the local hem.
    "reference": "FRONT",  # FRONT or REAR
    "distance_mm": 500.0,
    "height_from_hem_mm": 300.0,
    "length_mm": 250.0,
    "width_mm": 50.0,
    "color_rgba": [0.85, 0.87, 0.9, 1.0],
}

MARK_KIND = "reflective"
CONFIG_PROPERTY = "cc_reflective_config"
RECORD_PREFIX = "cc_reflective_marker"
# 100_marks.py settings; their front_axis seeds the dialog on a first run.
MARKS_CONFIG_PROPERTY = "cc_marks_config"
SIDE_PANELS = ("PANEL_LEFT", "PANEL_RIGHT")
HEM_GROUP_PREFIX = "HEM"
# Local hem height: HEM vertices within this distance of the strip center
# along the car (at least the strip's half extent), else the nearest ones.
HEM_WINDOW_MM = 150.0
HEM_NEAREST_COUNT = 5


# >>> CC MARK OVERLAY >>>
# Shared mark scheme. Keep this block identical in 100_marks.py,
# 101_reflective_strips.py and 003_cloth_setup.py so each script still runs
# on its own from Blender's Text Editor.
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
        raise RuntimeError("请选中至少一个带 Cloth 修改器的网格后再运行反光条脚本。")
    return cloths


def _front_axis(config):
    axis = str(config["front_axis"]).upper()
    if axis not in {"+X", "-X", "+Y", "-Y"}:
        raise ValueError("front_axis 必须为 '+X'、'-X'、'+Y' 或 '-Y'。")
    return axis, 0 if axis.endswith("X") else 1


def _choice(config, key, allowed):
    value = str(config[key]).upper()
    if value not in allowed:
        raise ValueError(f"{key} 必须为 {' 或 '.join(allowed)}。")
    return value


def _panel_names(config):
    sides = _choice(config, "sides", ("BOTH", *SIDE_PANELS))
    return SIDE_PANELS if sides == "BOTH" else (sides,)


def _bounds(points):
    return (
        Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))),
        Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))),
    )


def _side_panel(cloth, world, name):
    """Vertices, whole faces, evaluated bounds and HEM vertices of one panel."""
    group = cloth.vertex_groups.get(name)
    if group is None:
        raise RuntimeError(
            f"缺少 {name} 顶点组；请先运行 002_sew_from_svg.py "
            "从语义 SVG 创建 PANEL 顶点组。"
        )
    hem_groups = {
        item.index for item in cloth.vertex_groups
        if item.name.upper().startswith(HEM_GROUP_PREFIX)
    }
    members, hem = set(), []
    for vertex in cloth.data.vertices:
        weighted = {item.group for item in vertex.groups if item.weight > 0.001}
        if group.index in weighted:
            members.add(vertex.index)
            if weighted & hem_groups:
                hem.append(vertex.index)
    if not members:
        raise RuntimeError(f"{name} 顶点组为空。")
    polygons = [
        polygon.index
        for polygon in cloth.data.polygons
        if all(index in members for index in polygon.vertices)
    ]
    if not polygons:
        raise RuntimeError(f"{name} 没有包含任何完整布料面。")
    return {
        "vertices": members,
        "polygons": polygons,
        "bounds": _bounds([world[index] for index in members]),
        "hem": hem,
    }


def _hem_height(panel, world, longitudinal, center, half_along):
    """Mean settled Z of the panel's HEM vertices next to ``center``.

    Returns (z, source); source is "hem", or "panel_bottom" when the panel has
    no HEM vertices.
    """
    hem = panel["hem"]
    if not hem:
        return panel["bounds"][0].z, "panel_bottom"
    window = max(half_along, HEM_WINDOW_MM / 1000.0)
    local = [index for index in hem if abs(world[index][longitudinal] - center) <= window]
    if not local:
        local = sorted(hem, key=lambda index: abs(world[index][longitudinal] - center))
        local = local[:HEM_NEAREST_COUNT]
    return sum(world[index].z for index in local) / len(local), "hem"


def _strip_extents(config):
    """Half extents (along the car, upright) in metres."""
    length = float(config["length_mm"])
    width = float(config["width_mm"])
    if length <= 0 or width <= 0:
        raise ValueError("反光条长度和宽度必须大于零。")
    if _choice(config, "orientation", ("HORIZONTAL", "VERTICAL")) == "VERTICAL":
        length, width = width, length
    return length / 2000.0, width / 2000.0


def _strip_target(name, panel, world, config, half_along, half_up):
    """Strip center on one side panel, with the hem height it is measured from."""
    axis, longitudinal = _front_axis(config)
    reference = _choice(config, "reference", ("FRONT", "REAR"))
    for key in ("distance_mm", "height_from_hem_mm"):
        if float(config[key]) < 0:
            raise ValueError(f"{key} 不能小于零。")
    low, high = panel["bounds"]
    use_high = axis.startswith("+") == (reference == "FRONT")
    distance = float(config["distance_mm"]) / 1000.0
    center = high[longitudinal] - distance if use_high else low[longitudinal] + distance
    if center - half_along < low[longitudinal] or center + half_along > high[longitudinal]:
        raise ValueError(
            f"反光条超出 {name} 前后范围（版片长 "
            f"{(high[longitudinal] - low[longitudinal]) * 1000.0:.0f} mm）；"
            "请调整距车头/车尾距离或车头方向。"
        )
    hem_z, source = _hem_height(panel, world, longitudinal, center, half_along)
    target = (low + high) * 0.5
    target[longitudinal] = center
    target.z = hem_z + float(config["height_from_hem_mm"]) / 1000.0
    if target.z - half_up < hem_z:
        raise ValueError(f"反光条下边低于 {name} 的 hem；请增大距 hem 距离。")
    if target.z + half_up > high.z:
        raise ValueError(f"反光条上边超出 {name} 顶部；请减小距 hem 距离。")
    return target, hem_z, source


def _strip_mark(cloth, world, config):
    """Corner coordinates of the strip on every selected side panel."""
    _, longitudinal = _front_axis(config)
    half_along, half_up = _strip_extents(config)
    mesh = cloth.data
    values = [MARK_OUTSIDE] * (len(mesh.loops) * 2)
    faces, placements = set(), {}
    for name in _panel_names(config):
        panel = _side_panel(cloth, world, name)
        target, hem_z, source = _strip_target(name, panel, world, config, half_along, half_up)
        selected = 0
        for index in panel["polygons"]:
            polygon = mesh.polygons[index]
            for loop_index in polygon.loop_indices:
                point = world[mesh.loops[loop_index].vertex_index]
                values[loop_index * 2] = (point[longitudinal] - target[longitudinal]) / half_along
                values[loop_index * 2 + 1] = (point.z - target.z) / half_up
            if mark_touches(values, polygon.loop_indices):
                faces.add(index)
                selected += 1
        if not selected:
            raise RuntimeError(
                f"反光条在 {name} 范围内没有布料面；请确认当前帧已经完成落罩，"
                "并检查车头方向、位置及尺寸。"
            )
        placements[name] = {"hem_z": hem_z, "hem_source": source, "faces": selected}
    return {"values": values, "faces": faces, "placements": placements}


# ------------------------------------------------------------------- apply


def _merged_config(config):
    result = copy.deepcopy(REFLECTIVE_CONFIG)
    result.update(copy.deepcopy(config or {}))
    return result


def _stored_config(cloth, name=CONFIG_PROPERTY):
    try:
        stored = json.loads(cloth.get(name, "{}"))
    except (TypeError, ValueError):
        return {}
    return stored if isinstance(stored, dict) else {}


def strip_info_text(config):
    """One-line positioning record (ASCII, also shown in the dialog)."""
    return (
        f"REFLECTIVE {str(config['sides']).upper()}  {str(config['orientation']).upper()}  "
        f"{str(config['reference']).upper()} {float(config['distance_mm']):g}  "
        f"HEM {float(config['height_from_hem_mm']):g}  "
        f"L {float(config['length_mm']):g} x W {float(config['width_mm']):g} mm  "
        f"FRONT AXIS {config['front_axis']}"
    )


def _write_records(cloth, config, result):
    cloth[RECORD_PREFIX + "_faces"] = ",".join(str(index) for index in sorted(result["faces"]))
    cloth[RECORD_PREFIX + "_panels"] = ",".join(result["placements"])
    cloth[RECORD_PREFIX + "_hem_z_mm"] = [
        placement["hem_z"] * 1000.0 for placement in result["placements"].values()
    ]
    cloth[RECORD_PREFIX + "_hem_source"] = ",".join(
        placement["hem_source"] for placement in result["placements"].values()
    )
    cloth[RECORD_PREFIX + "_info"] = strip_info_text(config)


def apply_reflective_strips(cloth, config=None):
    """Write the strip (or remove it when disabled). Returns the face count."""
    config = _merged_config(config)
    _front_axis(config)
    result = None
    if config.get("enabled", True):
        result = _strip_mark(cloth, mark_evaluated_vertices(cloth), config)
        mark_write(cloth, MARK_KIND, result["values"], config["color_rgba"])
    else:
        mark_remove(cloth, MARK_KIND)
    mark_rebuild(cloth)

    for key in [key for key in cloth.keys() if key.startswith(RECORD_PREFIX)]:
        del cloth[key]
    if result is not None:
        _write_records(cloth, config, result)
    cloth[CONFIG_PROPERTY] = json.dumps(config, ensure_ascii=False)

    count = len(result["faces"]) if result else 0
    print(f"CC reflective strips: cloth={cloth.name}, faces={count}"
          + ("" if result else ", removed"))
    if result:
        print("  " + strip_info_text(config))
        for name, placement in result["placements"].items():
            print(f"  {name}: hem Z {placement['hem_z'] * 1000.0:.1f} mm "
                  f"({placement['hem_source']}), faces {placement['faces']}")
    return count


def apply_to_cloths(cloths, config=None):
    """apply_reflective_strips() on each cloth; a failure skips only that cloth.

    Returns ({cloth name: face count}, {cloth name: error message}).
    """
    done, failed = {}, {}
    for cloth in cloths:
        try:
            done[cloth.name] = apply_reflective_strips(cloth, config)
        except (RuntimeError, ValueError) as error:
            failed[cloth.name] = str(error)
            print(f"CC reflective strips: cloth={cloth.name} skipped: {error}")
    return done, failed


# ------------------------------------------------------------------ dialog

ENUM_ITEMS = {
    "front_axis": (("-Y", "-Y", "Model X 默认"), ("+Y", "+Y", ""),
                   ("-X", "-X", ""), ("+X", "+X", "")),
    "sides": (("BOTH", "左右两侧", "PANEL_LEFT 和 PANEL_RIGHT"),
              ("PANEL_LEFT", "PANEL_LEFT", "仅左侧版片"),
              ("PANEL_RIGHT", "PANEL_RIGHT", "仅右侧版片")),
    "orientation": (("HORIZONTAL", "横向", "长边沿车身前后方向"),
                    ("VERTICAL", "竖向", "长边竖直")),
    "reference": (("FRONT", "车头", "中心距版片车头端"),
                  ("REAR", "车尾", "中心距版片车尾端")),
}
# (config key, label)
SETTINGS_FIELDS = (
    ("front_axis", "车头方向"),
    ("enabled", "反光条"),
    ("sides", "版片"),
    ("orientation", "方向"),
    ("reference", "前后基准"),
    ("distance_mm", "中心距车头/车尾 (mm)"),
    ("height_from_hem_mm", "中心距 hem (mm)"),
    ("length_mm", "长 (mm)"),
    ("width_mm", "宽 (mm)"),
)
SETTINGS_PREFIX = "cc_reflective_"


def _register_settings():
    wm = bpy.types.WindowManager
    for key, label in SETTINGS_FIELDS:
        default = REFLECTIVE_CONFIG[key]
        if key in ENUM_ITEMS:
            prop = bpy.props.EnumProperty(name=label, items=ENUM_ITEMS[key], default=default)
        elif isinstance(default, bool):
            prop = bpy.props.BoolProperty(name=label, default=default)
        else:
            minimum = 1.0 if key in {"length_mm", "width_mm"} else 0.0
            prop = bpy.props.FloatProperty(name=label, min=minimum, default=default)
        setattr(wm, SETTINGS_PREFIX + key, prop)


def _settings_to_config(wm):
    config = copy.deepcopy(REFLECTIVE_CONFIG)
    for key, _ in SETTINGS_FIELDS:
        config[key] = getattr(wm, SETTINGS_PREFIX + key)
    return config


def _config_to_settings(wm, config):
    config = _merged_config(config)
    for key, _ in SETTINGS_FIELDS:
        try:
            setattr(wm, SETTINGS_PREFIX + key, config[key])
        except (TypeError, ValueError):
            pass  # keep the dialog value when a stored value no longer fits


class CC_OT_reflective_strips(bpy.types.Operator):
    """在落罩后的车罩左右侧版片上生成反光条标记"""

    bl_idname = "cc.reflective_strips"
    bl_label = "反光条标记"
    bl_options = {"REGISTER", "UNDO"}

    def draw(self, context):
        wm = context.window_manager
        layout = self.layout

        def prop(container, key):
            container.prop(wm, SETTINGS_PREFIX + key)

        try:
            names = [obj.name for obj in target_cloths(context)]
        except RuntimeError as error:
            layout.label(text=str(error), icon="ERROR")
        else:
            shown = "、".join(names[:4]) + (" 等" if len(names) > 4 else "")
            layout.label(text=f"将标记 {len(names)} 个物体：{shown}", icon="OBJECT_DATA")
        prop(layout, "front_axis")

        box = layout.box()
        prop(box, "enabled")
        column = box.column()
        column.active = wm.cc_reflective_enabled
        column.label(text="定位点为反光条中心；距离沿车身量到所选版片的前/后端")
        prop(column, "sides")
        column.row().prop(wm, SETTINGS_PREFIX + "orientation", expand=True)
        row = column.row(align=True)
        prop(row, "reference")
        prop(row, "distance_mm")
        prop(column, "height_from_hem_mm")
        row = column.row(align=True)
        prop(row, "length_mm")
        prop(row, "width_mm")
        column.label(text=strip_info_text(_settings_to_config(wm)), icon="INFO")

    def execute(self, context):
        try:
            cloths = target_cloths(context)
        except RuntimeError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        done, failed = apply_to_cloths(cloths, _settings_to_config(context.window_manager))
        for name, message in failed.items():
            self.report({"WARNING"}, f"{name}：{message}")
        if not done:
            self.report({"ERROR"}, f"{len(failed)} 个物体全部标记失败，详见警告。")
            return {"CANCELLED"}
        mark_show_solid_texture(context)
        self.report(
            {"WARNING" if failed else "INFO"},
            f"已标记 {len(done)} 个物体，反光条共 {sum(done.values())} 面"
            + (f"，{len(failed)} 个失败" if failed else ""),
        )
        return {"FINISHED"}

    def invoke(self, context, event):
        # Start from the settings last applied to this cloth; on a first run
        # take the front axis set by 100_marks.py.
        active = context.view_layer.objects.active
        if active is not None and CONFIG_PROPERTY in active:
            _config_to_settings(context.window_manager, _stored_config(active))
        elif active is not None and MARKS_CONFIG_PROPERTY in active:
            axis = _stored_config(active, MARKS_CONFIG_PROPERTY).get("front_axis")
            if axis in {item[0] for item in ENUM_ITEMS["front_axis"]}:
                context.window_manager.cc_reflective_front_axis = axis
        return context.window_manager.invoke_props_dialog(self, width=520)


def launch_reflective_dialog():
    """Register safely on repeated Text Editor runs and open the dialog."""
    previous = getattr(bpy.types, CC_OT_reflective_strips.__name__, None)
    if previous is not None:
        try:
            bpy.utils.unregister_class(previous)
        except RuntimeError:
            pass
    _register_settings()
    bpy.utils.register_class(CC_OT_reflective_strips)
    if bpy.app.background:
        return apply_to_cloths(target_cloths(), copy.deepcopy(REFLECTIVE_CONFIG))
    return bpy.ops.cc.reflective_strips("INVOKE_DEFAULT")


if __name__ == "__main__":
    launch_reflective_dialog()
