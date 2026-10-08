"""Lightweight standalone Cloth preset for a quick car-cover fit test.

Blender usage:
1. Generate the loose sewing edges first.
2. Add Collision physics to the vehicle/proxy.
3. In Object Mode, select only the car-cover mesh objects and run this file.
4. Return to frame 1 and play/bake through frame 45.
5. Inspect the seam lines in Solid (Color = Texture), Material Preview or
   Rendered view.

This intentionally omits staged guides, HEM correction, force fields, Weld,
Subdivision and handlers.  It is a fast topology/fit check, not a final bake.
One Blender unit is assumed to be one metre.
"""

import bpy


PRESET_NAME = "CarCover_QuickFit_45F_V1"
SIMULATION_FRAMES = 45

# Lower values than the production preset make iteration substantially faster.
QUALITY_STEPS = 8
COLLISION_QUALITY = 4
MASS_PER_VERTEX = 0.25
AIR_DAMPING = 3.0

TENSION_STIFFNESS = 45.0
COMPRESSION_STIFFNESS = 40.0
SHEAR_STIFFNESS = 40.0
BENDING_STIFFNESS = 5.0
TENSION_DAMPING = 8.0
COMPRESSION_DAMPING = 8.0
SHEAR_DAMPING = 8.0
BENDING_DAMPING = 2.0

ENABLE_SEWING = True
SEWING_FORCE_MAX = 10.0
ENABLE_OBJECT_COLLISION = True
OBJECT_COLLISION_DISTANCE_MM = 10.0
OBJECT_COLLISION_FRICTION = 0.2
COLLIDER_SURFACE_FRICTION = 3.0

# Disable this first for the quickest gross-fit test.  Enable it when panels
# fold through one another and that prevents a meaningful result.
ENABLE_SELF_COLLISION = False
SELF_COLLISION_DISTANCE_MM = 3.0
SELF_COLLISION_FRICTION = 0.2

COLLISION_PROXY_TAG = "car_cover_generated_collision_proxy"
MAX_SEWING_CONNECTORS_PER_VERTEX = 2

# Seam preview.  generate_sewing.py creates semantic vertex groups such as
# S001_LEFT / S001_TOP.  They are drawn by the shared CC mark overlay scheme as
# a straight band of SEAM_MARK_WIDTH_MM on each side of the seam, following
# Cloth without adding geometry or taking part in the solve.
ENABLE_SEAM_TEXTURE = True
SEAM_MARK_WIDTH_MM = 12.0
FABRIC_MATERIAL_NAME = "CC Quick Fit Fabric"
FABRIC_COLOR = (0.035, 0.055, 0.085, 1.0)
SEAM_COLOR = (0.004, 0.006, 0.009, 1.0)
FABRIC_ROUGHNESS = 0.72
LEGACY_SEAM_MASK_ATTRIBUTE = "CC_SEAM_MASK"


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


# >>> CC SEAM MARK >>>
# Semantic seams drawn as a CC mark. Keep this block identical in cloth.py and
# cloth_fit_test.py. Every face touching a seam vertex stores, per corner, the
# rest-pose distance to the nearby seam edges divided by the band width, so the
# mask |u| < 1 draws a straight band along each side of the seam.
SEAM_MARK_KIND = "seam"


def is_semantic_seam_group(name):
    """Identify seam paths while excluding their single-vertex A/B markers."""

    if name.endswith(("_A", "_B")):
        return False
    if name.startswith("SEAM_"):
        return True
    seam_id = name.split("_", 1)[0]
    return seam_id.startswith("S") and seam_id[1:].isdigit()


def semantic_seam_edges(obj):
    """Return face edges lying on one semantic seam group, and the seam vertex count."""

    seam_groups = [
        group for group in obj.vertex_groups if is_semantic_seam_group(group.name)
    ]
    if not seam_groups:
        return set(), 0

    vertices_by_group = {}
    for group in seam_groups:
        vertices_by_group[group.index] = {
            vertex.index
            for vertex in obj.data.vertices
            if any(
                membership.group == group.index and membership.weight > 0.001
                for membership in vertex.groups
            )
        }

    edges = set()
    for polygon in obj.data.polygons:
        vertices = tuple(polygon.vertices)
        for first, second in zip(vertices, vertices[1:] + vertices[:1]):
            if any(
                first in group_vertices and second in group_vertices
                for group_vertices in vertices_by_group.values()
            ):
                edges.add((min(first, second), max(first, second)))
    return edges, len(set().union(*vertices_by_group.values()))


def seam_mark_coordinates(obj, edges, width):
    """Return flat corner (u, v) mark values and the number of touched faces."""

    mesh = obj.data
    points = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
    edges_by_vertex = {}
    for edge in edges:
        for vertex_index in edge:
            edges_by_vertex.setdefault(vertex_index, []).append(edge)
    values = [MARK_OUTSIDE] * (len(mesh.loops) * 2)
    faces = 0
    for polygon in mesh.polygons:
        nearby = {
            edge for vertex_index in polygon.vertices
            for edge in edges_by_vertex.get(vertex_index, ())
        }
        if not nearby:
            continue
        for loop_index in polygon.loop_indices:
            point = points[mesh.loops[loop_index].vertex_index]
            distance = min(
                _segment_distance(point, points[first], points[second])
                for first, second in nearby
            )
            values[loop_index * 2] = distance / width
            values[loop_index * 2 + 1] = 0.0
        faces += mark_touches(values, polygon.loop_indices)
    return values, faces


def _segment_distance(point, start, end):
    direction = end - start
    length_squared = direction.length_squared
    factor = 0.0
    if length_squared > 0.0:
        factor = max(0.0, min(1.0, (point - start).dot(direction) / length_squared))
    return (point - (start + direction * factor)).length
# <<< CC SEAM MARK <<<


def _is_collider(obj):
    return (
        obj.get(COLLISION_PROXY_TAG, False)
        or any(modifier.type == "COLLISION" for modifier in obj.modifiers)
    )


def _selected_cloth_meshes():
    return [
        obj for obj in bpy.context.selected_objects
        if obj.type == "MESH" and obj.data.polygons and not _is_collider(obj)
    ]


def _scene_colliders():
    return [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH"
        and any(modifier.type == "COLLISION" for modifier in obj.modifiers)
    ]


def _loose_edges(obj):
    return [edge for edge in obj.data.edges if edge.is_loose]


def _ensure_fabric_material(obj):
    """Give an unmaterialed (or legacy-preview-only) mesh the fabric material."""
    if any(
        material is not None
        and MARK_OVERLAY_BASE_PROPERTY not in material
        and material.name not in MARK_LEGACY_MATERIALS
        for material in obj.data.materials
    ):
        return
    material = bpy.data.materials.get(FABRIC_MATERIAL_NAME)
    if material is None:
        material = bpy.data.materials.new(FABRIC_MATERIAL_NAME)
    material.use_nodes = True
    material.diffuse_color = FABRIC_COLOR
    shader = _mark_principled(material)
    if shader is not None:
        shader.inputs["Base Color"].default_value = FABRIC_COLOR
        shader.inputs["Roughness"].default_value = FABRIC_ROUGHNESS
    # mark_rebuild() returns faces of legacy previews to this first base slot.
    obj.data.materials.append(material)


def _apply_seam_texture(obj):
    edges, seam_vertices = semantic_seam_edges(obj)
    if not seam_vertices:
        raise RuntimeError(
            f"{obj.name} 没有 SEAM 顶点组；请先运行 generate_sewing.py。"
        )
    values, _touched = seam_mark_coordinates(obj, edges, SEAM_MARK_WIDTH_MM / 1000.0)
    _ensure_fabric_material(obj)
    mark_write(obj, SEAM_MARK_KIND, values, SEAM_COLOR)
    mark_rebuild(obj)
    mark_show_solid_texture(bpy.context)
    legacy = obj.data.attributes.get(LEGACY_SEAM_MASK_ATTRIBUTE)
    if legacy is not None:
        obj.data.attributes.remove(legacy)
    obj["cloth_seam_texture"] = MARK_ATTRIBUTE_PREFIX + SEAM_MARK_KIND
    obj["cloth_seam_mask_attribute"] = MARK_ATTRIBUTE_PREFIX + SEAM_MARK_KIND
    obj["cloth_seam_mask_vertex_count"] = seam_vertices
    return obj["cloth_seam_texture"], seam_vertices


def _validate_sewing(obj):
    loose = _loose_edges(obj)
    if ENABLE_SEWING and not loose:
        raise RuntimeError(
            f"{obj.name} 没有 Loose Edge；请先运行 generate_sewing.py。"
        )

    degree = {}
    for edge in loose:
        for vertex_index in edge.vertices:
            degree[vertex_index] = degree.get(vertex_index, 0) + 1
    hubs = [(index, count) for index, count in degree.items()
            if count > MAX_SEWING_CONNECTORS_PER_VERTEX]
    if hubs:
        preview = ", ".join(f"v{index}:{count}" for index, count in hubs[:8])
        raise RuntimeError(
            f"{obj.name} 存在 Sewing 多对一顶点（{preview}），请重新生成缝线。"
        )
    return len(loose)


def _cloth_modifier(obj):
    modifier = next(
        (item for item in obj.modifiers if item.type == "CLOTH"), None
    )
    if modifier is None:
        modifier = obj.modifiers.new(name="CC Quick Fit Cloth", type="CLOTH")
    return modifier


def _set_if_present(target, name, value):
    """Tolerate small Cloth API differences between Blender releases."""
    if hasattr(target, name):
        setattr(target, name, value)


def apply_quick_fit(obj, frame_start, frame_end, colliders):
    loose_count = _validate_sewing(obj)
    modifier = _cloth_modifier(obj)
    settings = modifier.settings
    collision = modifier.collision_settings
    cache = modifier.point_cache

    was_baked = bool(getattr(cache, "is_baked", False))
    if not was_baked:
        cache.frame_start = frame_start
        cache.frame_end = frame_end

    settings.quality = QUALITY_STEPS
    settings.time_scale = 1.0
    settings.mass = MASS_PER_VERTEX
    settings.air_damping = AIR_DAMPING
    settings.tension_stiffness = TENSION_STIFFNESS
    settings.compression_stiffness = COMPRESSION_STIFFNESS
    settings.shear_stiffness = SHEAR_STIFFNESS
    settings.bending_stiffness = BENDING_STIFFNESS
    _set_if_present(settings, "bending_model", "ANGULAR")
    settings.tension_damping = TENSION_DAMPING
    settings.compression_damping = COMPRESSION_DAMPING
    settings.shear_damping = SHEAR_DAMPING
    settings.bending_damping = BENDING_DAMPING
    _set_if_present(settings, "use_pressure", False)

    settings.use_sewing_springs = ENABLE_SEWING
    settings.sewing_force_max = SEWING_FORCE_MAX

    # An empty pin group is important when reusing a mesh configured by the
    # full preset; otherwise an old PIN_ROOF can silently hold the cover up.
    settings.vertex_group_mass = ""

    collision.use_collision = ENABLE_OBJECT_COLLISION
    collision.collision_quality = COLLISION_QUALITY
    collision.distance_min = OBJECT_COLLISION_DISTANCE_MM / 1000.0
    collision.friction = OBJECT_COLLISION_FRICTION
    collision.collection = None
    collision.use_self_collision = ENABLE_SELF_COLLISION
    collision.self_distance_min = SELF_COLLISION_DISTANCE_MM / 1000.0
    collision.self_friction = SELF_COLLISION_FRICTION

    for collider in colliders:
        collider.collision.cloth_friction = COLLIDER_SURFACE_FRICTION
    for polygon in obj.data.polygons:
        polygon.use_smooth = True

    seam_texture = ("disabled", 0)
    if ENABLE_SEAM_TEXTURE:
        seam_texture = _apply_seam_texture(obj)

    obj["cloth_preset"] = PRESET_NAME
    obj["cloth_quick_fit"] = True
    obj["cloth_loose_sewing_edge_count"] = loose_count
    obj["cloth_collision_objects"] = ", ".join(item.name for item in colliders)
    obj["cloth_self_collision"] = ENABLE_SELF_COLLISION
    return modifier, loose_count, was_baked, seam_texture


def main():
    if bpy.context.mode != "OBJECT":
        raise RuntimeError("请切换到 Object Mode，并只选择车罩 Cloth Mesh。")

    cloth_objects = _selected_cloth_meshes()
    if not cloth_objects:
        raise RuntimeError("没有选中有效的车罩面网格；碰撞体不会被当作 Cloth。")

    colliders = _scene_colliders()
    if ENABLE_OBJECT_COLLISION and not colliders:
        raise RuntimeError("场景中没有带 Collision Physics 的 Mesh 碰撞体。")

    scene = bpy.context.scene
    frame_start = scene.frame_start
    frame_end = frame_start + SIMULATION_FRAMES - 1
    scene.frame_end = frame_end

    print("\n" + "=" * 60)
    print(f"QUICK FIT TEST: {PRESET_NAME}")
    print("Colliders: " + ", ".join(obj.name for obj in colliders))
    baked = []
    for obj in cloth_objects:
        _modifier, loose_count, was_baked, seam_texture = apply_quick_fit(
            obj, frame_start, frame_end, colliders
        )
        if was_baked:
            baked.append(obj.name)
        print(
            f"{obj.name}: loose sewing edges={loose_count}, "
            f"quality={QUALITY_STEPS}, collision quality={COLLISION_QUALITY}, "
            f"self collision={'ON' if ENABLE_SELF_COLLISION else 'OFF'}, "
            f"seam texture={seam_texture[0]} ({seam_texture[1]} vertices)"
        )

    scene.frame_set(frame_start)
    print(f"完成。回到第 {frame_start} 帧，播放或烘焙到第 {frame_end} 帧。")
    if baked:
        print("[IMPORTANT] 先 Free Bake，再重新运行：" + ", ".join(baked))
    if not ENABLE_SELF_COLLISION:
        print("快速模式已关闭自碰撞；若布片互穿影响判断，将 ENABLE_SELF_COLLISION 改为 True。")
    print("=" * 60)


if __name__ == "__main__":
    main()
