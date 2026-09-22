"""Lightweight standalone Cloth preset for a quick car-cover fit test.

Blender usage:
1. Generate the loose sewing edges first.
2. Add Collision physics to the vehicle/proxy.
3. In Object Mode, select only the car-cover mesh objects and run this file.
4. Return to frame 1 and play/bake through frame 45.
5. Use Material Preview or Rendered view to inspect the procedural seam lines.

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

# Procedural seam preview.  generate_sewing.py creates semantic
# vertex groups such as S001_LEFT / S001_TOP.  Their vertices are written to a
# point-domain mask which the material reads, so the line follows Cloth without
# adding geometry or taking part in the solve.
ENABLE_SEAM_TEXTURE = True
SEAM_MASK_ATTRIBUTE = "CC_SEAM_MASK"
SEAM_MATERIAL_NAME = "CC Quick Fit Seam Preview"
FABRIC_COLOR = (0.035, 0.055, 0.085, 1.0)
SEAM_COLOR = (0.004, 0.006, 0.009, 1.0)
# Higher values make the line thinner.  At the intended 50 mm topology, 0.72
# produces a narrow band along the semantic boundary vertices.
SEAM_MASK_THRESHOLD = 0.72
FABRIC_ROUGHNESS = 0.72


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


def _is_semantic_seam_group(name):
    """Return True for seam paths, excluding their single-point A/B markers."""
    if name.endswith("_A") or name.endswith("_B"):
        return False
    if name.startswith("SEAM_"):
        return True
    seam_id = name.split("_", 1)[0]
    return seam_id.startswith("S") and seam_id[1:].isdigit()


def _write_seam_mask(obj):
    """Combine every semantic seam vertex group into one shader attribute."""
    group_indices = {
        group.index for group in obj.vertex_groups
        if _is_semantic_seam_group(group.name)
    }
    if not group_indices:
        raise RuntimeError(
            f"{obj.name} 没有 SEAM 顶点组；请先运行 generate_sewing.py。"
        )

    attributes = obj.data.attributes
    attribute = attributes.get(SEAM_MASK_ATTRIBUTE)
    if attribute is not None and (
        attribute.domain != "POINT" or attribute.data_type != "FLOAT"
    ):
        attributes.remove(attribute)
        attribute = None
    if attribute is None:
        attribute = attributes.new(
            name=SEAM_MASK_ATTRIBUTE, type="FLOAT", domain="POINT"
        )

    seam_vertices = 0
    for vertex in obj.data.vertices:
        is_seam = any(item.group in group_indices for item in vertex.groups)
        attribute.data[vertex.index].value = 1.0 if is_seam else 0.0
        seam_vertices += int(is_seam)
    return seam_vertices


def _ensure_seam_material():
    """Create an idempotent fabric material with a mask-driven seam line."""
    material = bpy.data.materials.get(SEAM_MATERIAL_NAME)
    if material is None:
        material = bpy.data.materials.new(SEAM_MATERIAL_NAME)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (520, 0)
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.location = (240, 0)
    shader.inputs["Roughness"].default_value = FABRIC_ROUGHNESS

    attribute = nodes.new("ShaderNodeAttribute")
    attribute.attribute_name = SEAM_MASK_ATTRIBUTE
    attribute.label = "Semantic seam mask"
    attribute.location = (-520, 80)

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-280, 80)
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = SEAM_MASK_THRESHOLD
    ramp.color_ramp.elements[0].color = FABRIC_COLOR
    ramp.color_ramp.elements[1].position = SEAM_MASK_THRESHOLD
    ramp.color_ramp.elements[1].color = SEAM_COLOR

    links.new(attribute.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def _apply_seam_texture(obj):
    seam_vertices = _write_seam_mask(obj)
    material = _ensure_seam_material()
    slot = next(
        (index for index, item in enumerate(obj.data.materials) if item == material),
        None,
    )
    if slot is None:
        obj.data.materials.append(material)
        slot = len(obj.data.materials) - 1
    for polygon in obj.data.polygons:
        polygon.material_index = slot
    obj["cloth_seam_texture"] = material.name
    obj["cloth_seam_mask_attribute"] = SEAM_MASK_ATTRIBUTE
    obj["cloth_seam_mask_vertex_count"] = seam_vertices
    return material.name, seam_vertices


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
