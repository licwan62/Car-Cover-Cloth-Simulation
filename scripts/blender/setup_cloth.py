"""Apply a self-contained 75-frame sew, drape and HEM-level car-cover preset.

Usage in Blender:
1. Open the Scripting workspace and create a new Text block.
2. Paste this entire file into the Text Editor.
3. Select one or more 50 mm cloth mesh objects in Object Mode.
4. Clear any old Cloth bake, run Script, then simulate frames 1 through 75
   (or Scene Start through Scene Start + 74).
5. Start with non-intersecting panels. Self-collision is active from the start;
   the final stage applies per-vertex animated soft pin spring forces.
   Replay sequentially from Scene Start after clearing the cache; rerun this
   script to resample if the cloth or collision geometry changes.

This file deliberately has no project imports and reads no JSON, so saving it
inside a .blend file is enough to reproduce the preset.
"""

import bpy
from mathutils import Vector


# ============================================================
# EMBEDDED PRESET: CarCover_HemFeedback_75F_V28
# Assumptions:
# - 1 Blender Unit = 1 metre
# - Average cloth mesh edge length is approximately 50 mm
# - Final-stage soft HEM pin springs follow sampled free-drape X/Y
# ============================================================

PRESET_NAME = "CarCover_HemFeedback_75F_V28"
MATERIAL_PRESET_NAME = "Car Cover Natural Drape (uncalibrated)"
MESH_EDGE_TARGET_MM = 50.0
SIMULATION_END_OFFSET = 74

QUALITY_STEPS = 20
TIME_SCALE = 1.0
MASS_PER_VERTEX = 0.25
AIR_DAMPING = 3.0

TENSION_STIFFNESS = 60.0
COMPRESSION_STIFFNESS = 50.0
SHEAR_STIFFNESS = 50.0
BENDING_STIFFNESS = 8.0
BENDING_STIFFNESS_DURING_SEWING = 8.0
BENDING_RECOVERY_START = 7
BENDING_RECOVERY_END = 17
BENDING_MODEL = "ANGULAR"

TENSION_DAMPING = 10.0
COMPRESSION_DAMPING = 10.0
SHEAR_DAMPING = 10.0
BENDING_DAMPING = 3.0

ENABLE_SEWING = True
SEWING_FORCE_START = 4.0
MAX_SEWING_FORCE = 12.0
SEWING_FORCE_SUSTAIN = 6.0
SEWING_RAMP_START = 0
SEWING_RAMP_END = 19
SEWING_RELEASE_START = 24
SEWING_RELEASE_END = 34
SEWING_GRAVITY_FACTOR = 0.65
GRAVITY_RAMP_START = 0
GRAVITY_RAMP_END = 19

ENABLE_OBJECT_COLLISION = True
COLLISION_QUALITY = 8
OBJECT_COLLISION_DISTANCE_MM = 10.0
OBJECT_COLLISION_FRICTION = 0.2
COLLIDER_SURFACE_FRICTION = 3.0
COLLISION_PROXY_TAG = "car_cover_generated_collision_proxy"

ENABLE_SELF_COLLISION = True
SELF_COLLISION_START = 0
SELF_COLLISION_DISTANCE_MM = 2.5
SELF_COLLISION_FRICTION = 0.2

PIN_GROUP_NAME = "PIN_ROOF"
PIN_STIFFNESS = 0.85
PIN_VERTEX_WEIGHT = 0.85
ENABLE_ROOF_PIN_DURING_SIMULATION = True
AUTO_CREATE_ROOF_PIN = True
AUTO_ROOF_PIN_VERTEX_COUNT = 12
ROOF_PIN_HOLD_END = 19
ROOF_PIN_RELEASE_END = 29

SHADE_SMOOTH = True
ENABLE_DISPLAY_SUBSURF = True

# Seam preview. As with setup_mirror_markers.py, semantic seam groups are
# visualised by assigning a high-contrast material to existing cloth faces.
# This follows Cloth deformation and adds no solve geometry or constraints.
ENABLE_SEAM_TEXTURE = True
SEAM_MATERIAL_NAME = "CC Seam Color Mark"
SEAM_MATERIAL_SLOT_PROPERTY = "cc_seam_marker_material_slot"
SEAM_FACE_PROPERTY = "cc_seam_marker_faces"
BASE_MATERIAL_NAME = "CC Cloth Base"
FABRIC_COLOR = (0.035, 0.055, 0.085, 1.0)
SEAM_COLOR = (1.0, 0.12, 0.015, 1.0)
FABRIC_ROUGHNESS = 0.72

# A post-Weld Catmull-Clark modifier must rebuild its topology whenever seam
# vertices cross the Weld threshold. Keep it out of viewport playback so frame
# 19 does not appear to freeze the timeline at frame 18. Render evaluation
# remains enabled, and the modifier can still be enabled manually for a settled
# frame preview.
DISPLAY_SUBSURF_IN_VIEWPORT = False
DISPLAY_SUBSURF_LEVELS = 1
DISPLAY_SUBSURF_RENDER_LEVELS = 2

# Legacy front/rear fitting guide, disabled in V27 so the hem settles freely.
# Keep its parameters and cleanup routines to deactivate existing V26 drivers.
ENABLE_HEM_DRAG = False
ENABLE_REAR_DRAG = False  # Legacy force-field implementation stays disabled.
FRONT_DRAG_GROUP_NAME = "HEM_FRONT"
REAR_DRAG_GROUP_NAME = "HEM_REAR"
HEM_DRAG_GROUP_NAMES = (FRONT_DRAG_GROUP_NAME, REAR_DRAG_GROUP_NAME)
# V16/V24 generated names are retained so V27 can remove their stale Pin,
# trajectory-key and force-field data when the script is rerun.
REAR_DRAG_PIN_GROUP_NAME = "CC_REAR_DRAG_PIN"
REAR_DRAG_WEIGHT_GROUP_NAME = "CC_REAR_DRAG_WEIGHT"
REAR_DRAG_MIX_MODIFIER_NAME = "CC Rear Drag Weight"
ROOF_PIN_RELEASE_MIX_MODIFIER_NAME = "CC Roof Pin Release"
REAR_DRAG_SHAPE_KEY_NAME = "CC_REAR_DRAG_TARGET"
HEM_LEVEL_SHAPE_KEY_NAME = "CC_HEM_LEVEL_TRIM"
HEM_CAPTURE_SHAPE_KEY_NAME = "CC_HEM_GRAB_FRAME18"
HEM_TRAJECTORY_SHAPE_KEY_PREFIX = "CC_HEM_FREE_F"
REAR_DRAG_DISTANCE_MM = 250.0
REAR_DRAG_OUTWARD_MM = 0.0
REAR_DRAG_LEVEL_TO_LOWEST = True
REAR_DRAG_PIN_STIFFNESS = 1.0
REAR_DRAG_VERTEX_WEIGHT = 1.0
REAR_DRAG_SUSTAIN_FACTOR = 1.0
REAR_DRAG_SUSTAIN_PIN_FACTOR = 0.0
REAR_DRAG_RELEASE_VERTEX_WEIGHT = 0.005
MAX_SAFE_REAR_DRAG_DISTANCE_MM = 500.0
MAX_SAFE_REAR_DRAG_OUTWARD_MM = 300.0

HEM_TENSION_DISTANCE_MM = 50.0
HEM_LEVELING_BIAS_MM = 30.0
HEM_FRONT_TENSION_DISTANCE_MM = 80.0
HEM_REAR_TENSION_DISTANCE_MM = 20.0
MAX_SAFE_HEM_TENSION_DISTANCE_MM = 80.0

HEM_DOWN_OBJECT_PREFIX = "CC_HEM_DOWN_"
HEM_DOWN_FIELD_COUNT_PER_GROUP = 3
HEM_DOWN_STRENGTH = 160.0
HEM_DOWN_EARLY_STRENGTH = 45.0
HEM_DOWN_SUSTAIN_STRENGTH = 25.0
HEM_DOWN_HEIGHT_MM = 200.0
HEM_DOWN_MIN_DISTANCE_MM = 350.0
HEM_DOWN_MAX_DISTANCE_MM = 900.0
HEM_DOWN_FALLOFF_POWER = 0.5
# 0.08 horizontal for every 1.0 downward: about 99.7% of the normalized
# direction remains vertical, while the small front/rear component aids slide.
HEM_SLIDE_HORIZONTAL_FACTOR = 0.08

HEM_DRAG_START = 17
HEM_DRAG_END = 40
HEM_LEVEL_START = 31
HEM_LEVEL_END = 44
HEM_DRAG_SETTLE_END = 74
HEM_EQUAL_HEIGHT_TOLERANCE_MM = 20.0
ENABLE_HEM_HEIGHT_FEEDBACK = False
HEM_HEIGHT_FEEDBACK_GAIN = 0.5
MAX_HEM_FRONT_EXTRA_MM = 250.0
HEM_FEEDBACK_SHAPE_KEY_NAME = "CC_HEM_FRONT_HEIGHT_CORRECTION"

# Names from V7/V8 are retained only so rerunning V9 can stop and hide the old
# generated rear Wind fields rather than allowing both guides to act at once.
LEGACY_REAR_PULL_OBJECT_PREFIX = "CC_REAR_PULL_"

# V27 keeps the old TOP directional guide disabled. Cleanup paths make rerunning
# the script deactivate stale fields already stored in the .blend file.
# script disable old V7/V8
# TOP Wind objects already stored in the .blend file.
ENABLE_TOP_DOWN_GUIDE = False
TOP_DOWN_OBJECT_PREFIX = "CC_TOP_DOWN_"
TOP_PANEL_GROUP_NAMES = ("PANEL_TOP", "TOP")
TOP_DOWN_HEIGHT_MM = 450.0
TOP_DOWN_STRENGTH = 120.0
TOP_DOWN_MIN_DISTANCE_MM = 150.0
TOP_DOWN_MAX_DISTANCE_MM = 1300.0
TOP_DOWN_FALLOFF_POWER = 0.5
TOP_DOWN_RAMP_END = 1
TOP_DOWN_HOLD_END = 3
TOP_DOWN_RELEASE_END = 5

# Legacy staged expansion parameters are retained for deterministic cleanup and
# easy comparison, but V27 keeps this entire expansion guide disabled.
ENABLE_STAGED_EXPANSION = False
REQUIRE_PIN_FOR_EXPANSION = True
EXPANSION_CENTER_OBJECT_NAME = "COVER_AIR_CENTER"
EXPANSION_OBJECT_PREFIX = "CC_EXPAND_"
EXPANSION_FIELD_COUNT = 5
EXPANSION_AXIS_SPREAD = 0.42
EXPANSION_FORCE_ABOVE_TOP_MM = 300.0
# Five fields overlap, so a high per-field peak can overpower sewing springs and
# reopen seams. Use a gentler peak and turn every field off before HEM fitting.
EXPANSION_STRENGTH = 1.5
EXPANSION_SUSTAIN_STRENGTH = 0.6
EXPANSION_MIN_DISTANCE_MM = 250.0
EXPANSION_MAX_DISTANCE_MM = 1600.0
EXPANSION_FALLOFF_POWER = 1.0

# Stage offsets are relative to Scene Start.
EXPANSION_RAMP_START = 29
EXPANSION_RAMP_END = 39
EXPANSION_HOLD_END = 44
EXPANSION_SUSTAIN_START = 46
EXPANSION_RELEASE_START = 46
EXPANSION_RELEASE_END = 49

# Legacy Wind timing retained only for cleaning up older generated fields.
REAR_DRAG_START = 17
REAR_DRAG_RAMP_START = 23
REAR_DRAG_RAMP_END = 35
REAR_DRAG_HOLD_END = 40
REAR_DRAG_RELEASE_END = 46
REAR_DRAG_SUSTAIN_END = 49

# Print one compact line per evaluated frame so the active guide forces can be
# checked in Blender's System Console while playing or baking the simulation.
ENABLE_FORCE_STAGE_LOG = True

# Base-mesh seam length diagnostics. Lengths are measured from connected mesh
# edges in world space before simulation, so loose sewing connector edges do
# not inflate either seam path.
SEAM_LENGTH_COMPARE_PAIRS = (
    ("SEAM_TOP_LEFT", "SEAM_LEFT_TOP"),
    ("SEAM_TOP_RIGHT", "SEAM_RIGHT_TOP"),
)
SEAM_LENGTH_WARN_PERCENT = 10.0

ENABLE_POST_CLOTH_SEAM_WELD = True
SEAM_WELD_MODIFIER_NAME = "CC Post-Cloth Seam Weld"
SEAM_WELD_GROUP_NAME = "CC_SEAM_WELD"
SEAM_WELD_DISTANCE_MM = 6.0
SEAM_WELD_ENABLE_OFFSET = 35
ABORT_ON_SEWING_HUBS = True
MAX_SEWING_CONNECTORS_PER_VERTEX = 2


def collision_proxy_reason(obj):
    """Explain why a selected mesh is a collider rather than cloth."""

    if obj.get(COLLISION_PROXY_TAG, False):
        return f"has generated-proxy tag '{COLLISION_PROXY_TAG}'"

    if any(modifier.type == "COLLISION" for modifier in obj.modifiers):
        return "has a Collision modifier"

    return None


def selected_cloth_meshes():
    """Return selected cloth candidates while rejecting collision proxies."""

    cloth_objects = []
    rejected = []
    for obj in bpy.context.selected_objects:
        if obj.type != "MESH":
            continue
        reason = collision_proxy_reason(obj)
        if reason is None:
            cloth_objects.append(obj)
        else:
            rejected.append((obj, reason))
    return cloth_objects, rejected


def resolve_collision_scope():
    """Use every Collision mesh in the current scene.

    Returning ``None`` as the collection is Blender's explicit all-scene
    collision scope.  Keep the collider list for friction configuration and
    diagnostics, but do not let generated-proxy tags narrow the solver scope.
    """

    scene = bpy.context.scene
    colliders = [
        obj
        for obj in scene.objects
        if obj.type == "MESH"
        and any(modifier.type == "COLLISION" for modifier in obj.modifiers)
    ]
    scope = f"all Collision objects in current scene '{scene.name}'"
    return None, colliders, scope


def get_or_create_cloth_modifier(obj):
    """Return the first Cloth modifier, creating one when necessary."""

    for modifier in obj.modifiers:
        if modifier.type == "CLOTH":
            return modifier

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj.modifiers.new(name="Car Cover Cloth", type="CLOTH")


def get_or_create_display_subsurf(obj):
    """Create a post-Cloth subdivision modifier used only for presentation."""

    modifier_name = "CC Display Smooth"
    modifier = obj.modifiers.get(modifier_name)
    if modifier is not None and modifier.type != "SUBSURF":
        modifier = None
    if modifier is None:
        modifier = obj.modifiers.new(name=modifier_name, type="SUBSURF")

    modifier.subdivision_type = "CATMULL_CLARK"
    modifier.levels = DISPLAY_SUBSURF_LEVELS
    modifier.render_levels = DISPLAY_SUBSURF_RENDER_LEVELS
    modifier.show_viewport = DISPLAY_SUBSURF_IN_VIEWPORT
    modifier.show_render = True

    # The display modifier must evaluate after Cloth/Weld and must never affect
    # the physical solve. Fit analysis should inspect the mesh before it.
    current_index = obj.modifiers.find(modifier.name)
    last_index = len(obj.modifiers) - 1
    if current_index != last_index:
        obj.modifiers.move(current_index, last_index)
    return modifier


def is_semantic_seam_group(name):
    """Identify seam paths while excluding their single-vertex A/B markers."""

    if name.endswith(("_A", "_B")):
        return False
    if name.startswith("SEAM_"):
        return True
    seam_id = name.split("_", 1)[0]
    return seam_id.startswith("S") and seam_id[1:].isdigit()


def get_or_create_color_material(name, color, roughness):
    """Create an idempotent viewport/render material, like mirror markers."""

    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    nodes = material.node_tree.nodes
    shader = nodes.get("Principled BSDF")
    if shader is not None:
        shader.inputs["Base Color"].default_value = color
        shader.inputs["Roughness"].default_value = roughness
        if "Emission Color" in shader.inputs:
            shader.inputs["Emission Color"].default_value = color
            shader.inputs["Emission Strength"].default_value = 0.12
    return material


def material_slot(obj, material):
    """Return a stable material slot without disturbing existing markers."""

    for index, slot_material in enumerate(obj.data.materials):
        if slot_material == material:
            return index
    obj.data.materials.append(material)
    return len(obj.data.materials) - 1


def semantic_seam_faces(obj):
    """Find faces containing an edge from any semantic seam vertex group."""

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

    marked_faces = set()
    marked_vertices = set().union(*vertices_by_group.values())
    for polygon in obj.data.polygons:
        vertices = tuple(polygon.vertices)
        polygon_edges = zip(vertices, vertices[1:] + vertices[:1])
        if any(
            first in group_vertices and second in group_vertices
            for first, second in polygon_edges
            for group_vertices in vertices_by_group.values()
        ):
            marked_faces.add(polygon.index)
    return marked_faces, len(marked_vertices)


def configure_seam_texture(obj):
    """Color existing faces beside semantic seam edges without adding physics."""

    if not ENABLE_SEAM_TEXTURE:
        return "disabled"
    marked_faces, seam_vertices = semantic_seam_faces(obj)
    if not seam_vertices:
        status = "missing semantic Sxxx_* / SEAM_* vertex groups"
        obj["cloth_seam_texture_status"] = status
        return status
    if not marked_faces:
        status = f"semantic seams found ({seam_vertices} vertices), but no seam faces"
        obj["cloth_seam_texture_status"] = status
        return status

    base_material = get_or_create_color_material(
        BASE_MATERIAL_NAME, FABRIC_COLOR, FABRIC_ROUGHNESS
    )
    seam_material = get_or_create_color_material(
        SEAM_MATERIAL_NAME, SEAM_COLOR, 0.48
    )
    base_slot = material_slot(obj, base_material)
    seam_slot = material_slot(obj, seam_material)

    # Repair assignments made by the former whole-object seam shader and clear
    # only our own previous marks. Other face markers remain untouched.
    previous_faces = {
        int(value) for value in str(obj.get(SEAM_FACE_PROPERTY, "")).split(",")
        if value.strip().isdigit()
    }
    for polygon in obj.data.polygons:
        if polygon.material_index == seam_slot and (
            not previous_faces or polygon.index in previous_faces
        ):
            polygon.material_index = base_slot
    for face_index in marked_faces:
        obj.data.polygons[face_index].material_index = seam_slot

    obj["cloth_seam_texture"] = seam_material.name
    obj[SEAM_MATERIAL_SLOT_PROPERTY] = seam_slot
    obj[SEAM_FACE_PROPERTY] = ",".join(str(i) for i in sorted(marked_faces))
    obj["cloth_seam_mask_vertex_count"] = seam_vertices
    obj["cloth_seam_marker_face_count"] = len(marked_faces)
    obj.data.update()
    status = (
        f"{seam_material.name} ({len(marked_faces)} faces, "
        f"{seam_vertices} vertices)"
    )
    obj["cloth_seam_texture_status"] = status
    return status


def configure_post_cloth_seam_weld(obj, cloth_modifier):
    """Weld only sewing endpoints after Cloth without changing its solve."""

    modifier = obj.modifiers.get(SEAM_WELD_MODIFIER_NAME)
    if modifier is not None and modifier.type != "WELD":
        raise RuntimeError(
            f"{SEAM_WELD_MODIFIER_NAME} exists but is not a Weld modifier"
        )

    if not ENABLE_POST_CLOTH_SEAM_WELD:
        if modifier is not None:
            modifier.show_viewport = False
            modifier.show_render = False
        return "disabled"

    seam_indices = sorted(
        {
            vertex_index
            for edge in obj.data.edges
            if getattr(edge, "is_loose", False)
            for vertex_index in edge.vertices
        }
    )
    if not seam_indices:
        if modifier is not None:
            modifier.show_viewport = False
            modifier.show_render = False
        return "skipped: no loose sewing edges"

    group = obj.vertex_groups.get(SEAM_WELD_GROUP_NAME)
    if group is None:
        group = obj.vertex_groups.new(name=SEAM_WELD_GROUP_NAME)
    all_indices = list(range(len(obj.data.vertices)))
    if all_indices:
        group.remove(all_indices)
    group.add(seam_indices, 1.0, "REPLACE")

    if modifier is None:
        modifier = obj.modifiers.new(
            name=SEAM_WELD_MODIFIER_NAME,
            type="WELD",
        )
    modifier.vertex_group = SEAM_WELD_GROUP_NAME
    modifier.mode = "ALL"
    modifier.show_viewport = True
    modifier.show_render = True

    # Keep the evaluated topology unchanged during active Sewing. The threshold
    # turns on after the sewing-force release. This is downstream of Cloth and
    # cannot feed a topology change back into the physics cache. The downstream
    # display Subsurf is disabled in the viewport by default because rebuilding
    # Catmull-Clark over this changing Weld topology is expensive.
    enable_frame = bpy.context.scene.frame_start + SEAM_WELD_ENABLE_OFFSET
    modifier.driver_remove("merge_threshold")
    driver = modifier.driver_add("merge_threshold").driver
    driver.type = "SCRIPTED"
    driver.expression = (
        f"{SEAM_WELD_DISTANCE_MM / 1000.0:g}*"
        f"max(0.0,min(1.0,frame-{enable_frame - 1:g}))"
    )

    # Put Weld at the end for now. Display Subsurf is moved behind it later,
    # giving a stable Cloth -> seam-only Weld -> display smoothing stack.
    current_index = obj.modifiers.find(modifier.name)
    last_index = len(obj.modifiers) - 1
    if current_index != last_index:
        obj.modifiers.move(current_index, last_index)

    obj["cloth_post_seam_weld_group"] = SEAM_WELD_GROUP_NAME
    obj["cloth_post_seam_weld_vertices"] = len(seam_indices)
    obj["cloth_post_seam_weld_distance_mm"] = SEAM_WELD_DISTANCE_MM
    obj["cloth_post_seam_weld_enable_frame"] = enable_frame
    return (
        f"ready ({len(seam_indices)} seam vertices, "
        f"{SEAM_WELD_DISTANCE_MM:g} mm from frame {enable_frame}, "
        "post-Cloth only)"
    )


def vertex_group_world_centroid(obj, group_name):
    """Return a semantic vertex group's world centroid, or None when missing."""

    group = obj.vertex_groups.get(group_name)
    if group is None:
        return None

    points = []
    for vertex in obj.data.vertices:
        if any(item.group == group.index and item.weight > 0.001 for item in vertex.groups):
            points.append(obj.matrix_world @ vertex.co)

    if not points:
        return None

    centroid = points[0].copy()
    for point in points[1:]:
        centroid += point
    centroid /= len(points)
    return centroid


def vertex_group_world_points(obj, group_name):
    """Return all weighted group vertices in world space."""

    group = obj.vertex_groups.get(group_name)
    if group is None:
        return []
    return [
        obj.matrix_world @ vertex.co
        for vertex in obj.data.vertices
        if any(
            item.group == group.index and item.weight > 0.001
            for item in vertex.groups
        )
    ]


def vertex_group_connected_length(obj, group_name):
    """Measure connected, non-sewing mesh edges inside a seam vertex group."""

    group = obj.vertex_groups.get(group_name)
    if group is None:
        return None
    members = {
        vertex.index
        for vertex in obj.data.vertices
        if any(
            item.group == group.index and item.weight > 0.001
            for item in vertex.groups
        )
    }
    if len(members) < 2:
        return None

    total = 0.0
    for edge in obj.data.edges:
        index_a, index_b = edge.vertices
        if index_a not in members or index_b not in members:
            continue
        if getattr(edge, "is_loose", False):
            continue
        point_a = obj.matrix_world @ obj.data.vertices[index_a].co
        point_b = obj.matrix_world @ obj.data.vertices[index_b].co
        total += (point_a - point_b).length
    return total if total > 0.0 else None


def report_sewing_preflight(obj):
    """Print connector count and paired seam-length differences."""

    loose_edges = [
        edge for edge in obj.data.edges if getattr(edge, "is_loose", False)
    ]
    loose_count = len(loose_edges)
    obj["cloth_loose_sewing_edge_count"] = loose_count
    print(f"  [CC SEAM] loose sewing edges={loose_count}")
    if ENABLE_SEWING and loose_count == 0:
        print("  [CC SEAM WARNING] 没有 loose edges；Sewing Springs 不会产生拉力。")

    connector_degree = {}
    for edge in loose_edges:
        for vertex_index in edge.vertices:
            connector_degree[vertex_index] = connector_degree.get(vertex_index, 0) + 1
    hub_vertices = sorted(
        (vertex_index, degree)
        for vertex_index, degree in connector_degree.items()
        if degree > MAX_SEWING_CONNECTORS_PER_VERTEX
    )
    obj["cloth_sewing_hub_vertex_count"] = len(hub_vertices)
    if hub_vertices:
        preview = ", ".join(
            f"v{vertex_index}:degree{degree}"
            for vertex_index, degree in hub_vertices[:8]
        )
        print(
            f"  [CC SEAM BLACK-HOLE WARNING] {len(hub_vertices)} 个顶点连接超过 "
            f"{MAX_SEWING_CONNECTORS_PER_VERTEX} 条 "
            f"loose sewing edges ({preview})；这些连接会持续把布料聚到同一点。"
        )
        if ABORT_ON_SEWING_HUBS:
            raise RuntimeError(
                "检测到 Sewing 黑洞拓扑，已停止添加/更新 Cloth。"
                f"每个缝线顶点最多允许 {MAX_SEWING_CONNECTORS_PER_VERTEX} 条 "
                "loose sewing edge；请重新运行 generate_sewing.py 修复配对。"
            )

    for name_a, name_b in SEAM_LENGTH_COMPARE_PAIRS:
        length_a = vertex_group_connected_length(obj, name_a)
        length_b = vertex_group_connected_length(obj, name_b)
        if length_a is None or length_b is None:
            print(f"  [CC SEAM WARNING] 无法测量 {name_a} <-> {name_b}")
            continue
        difference = abs(length_a - length_b) / max(length_a, length_b)
        level = "WARNING" if difference * 100.0 > SEAM_LENGTH_WARN_PERCENT else "OK"
        print(
            f"  [CC SEAM {level}] {name_a}={length_a * 1000.0:.1f} mm, "
            f"{name_b}={length_b * 1000.0:.1f} mm, diff={difference:.1%}"
        )


def create_force_field_object(name, location):
    """Create a real Blender Force effector and restore object selection."""

    selected_before = list(bpy.context.selected_objects)
    active_before = bpy.context.view_layer.objects.active

    try:
        bpy.ops.object.select_all(action="DESELECT")
        bpy.ops.object.effector_add(
            type="FORCE",
            location=location,
        )
        field_object = bpy.context.object
        if field_object is None or field_object.field is None:
            raise RuntimeError("Blender 未能创建 Force Field 对象。")
        field_object.name = name
        field_object["car_cover_generated_effector"] = True
        return field_object
    finally:
        bpy.ops.object.select_all(action="DESELECT")
        for selected_object in selected_before:
            if bpy.context.view_layer.objects.get(selected_object.name) is not None:
                selected_object.select_set(True)
        if (
            active_before is not None
            and bpy.context.view_layer.objects.get(active_before.name) is not None
        ):
            bpy.context.view_layer.objects.active = active_before


def get_or_create_force_field_object(name, location):
    """Return a valid generated Force effector, replacing invalid empties."""

    field_object = bpy.data.objects.get(name)
    if field_object is not None and field_object.field is None:
        bpy.data.objects.remove(field_object, do_unlink=True)
        field_object = None
    if field_object is None:
        field_object = create_force_field_object(name, location)
    if field_object.field is None:
        raise RuntimeError(
            f"{field_object.name} 不是有效的 Force Field；请删除后重新运行脚本。"
        )
    return field_object


def disable_generated_field(field_object):
    """Stop and hide one generated field without deleting user scene data."""

    if field_object is None or not field_object.get(
        "car_cover_generated_effector",
        False,
    ):
        return False

    field_object.animation_data_clear()
    for property_name in (
        "car_cover_force_schedule",
        "car_cover_force_frames",
        "car_cover_force_strengths",
    ):
        if property_name in field_object:
            del field_object[property_name]
    if field_object.field is not None:
        field_object.field.strength = 0.0
    field_object.hide_set(True)
    return True


def scheduled_strength(frames, strengths, frame):
    """Evaluate a piecewise-linear force schedule without an Action."""

    if not frames:
        return 0.0
    if frame <= frames[0]:
        return strengths[0]
    if frame >= frames[-1]:
        return strengths[-1]

    for index in range(1, len(frames)):
        frame_a = frames[index - 1]
        frame_b = frames[index]
        if frame <= frame_b:
            if frame_b == frame_a:
                return strengths[index]
            factor = (frame - frame_a) / (frame_b - frame_a)
            return strengths[index - 1] + factor * (
                strengths[index] - strengths[index - 1]
            )
    return strengths[-1]


def car_cover_force_stage_handler(scene, depsgraph=None):
    """Update generated force fields without Blender Action dependencies."""

    for field_object in bpy.data.objects:
        if not field_object.get("car_cover_force_schedule", False):
            continue
        if field_object.field is None:
            continue
        frames = list(field_object.get("car_cover_force_frames", ()))
        strengths = list(field_object.get("car_cover_force_strengths", ()))
        if len(frames) != len(strengths) or not frames:
            continue
        field_object.field.strength = scheduled_strength(
            frames,
            strengths,
            scene.frame_current,
        )

    log_force_stage(scene)


_LAST_FORCE_LOG_KEY = None


def log_force_stage(scene):
    """Print one compact, deduplicated summary of the current force stage."""

    global _LAST_FORCE_LOG_KEY
    if not ENABLE_FORCE_STAGE_LOG:
        return

    frame = float(scene.frame_current)
    log_key = (scene.as_pointer(), frame)
    if log_key == _LAST_FORCE_LOG_KEY:
        return
    _LAST_FORCE_LOG_KEY = log_key

    frames = staged_frames()
    sewing = scheduled_strength(
        [
            frames["sewing_ramp_start"],
            frames["sewing_ramp_end"],
            frames["sewing_release_start"],
            frames["sewing_release_end"],
        ],
        [
            SEWING_FORCE_START,
            MAX_SEWING_FORCE,
            MAX_SEWING_FORCE,
            SEWING_FORCE_SUSTAIN,
        ],
        frame,
    ) if ENABLE_SEWING else 0.0
    gravity = scheduled_strength(
        [frames["gravity_ramp_start"], frames["gravity_ramp_end"]],
        [SEWING_GRAVITY_FACTOR, 1.0],
        frame,
    )
    roof_pin = scheduled_strength(
        [frames["roof_pin_hold_end"], frames["roof_pin_release_end"]],
        [PIN_STIFFNESS, 0.0],
        frame,
    ) if ENABLE_ROOF_PIN_DURING_SIMULATION else 0.0
    self_collision = (
        "ON" if ENABLE_SELF_COLLISION
        and frame >= frames["self_collision_start"] else "OFF"
    )
    expansion = scheduled_strength(
        [
            frames["expand_ramp_start"],
            frames["expand_ramp_end"],
            frames["expand_hold_end"],
            frames["expand_sustain_start"],
            frames["expand_release_start"],
            frames["expand_release_end"],
        ],
        [
            0.0,
            EXPANSION_STRENGTH,
            EXPANSION_STRENGTH,
            EXPANSION_SUSTAIN_STRENGTH,
            EXPANSION_SUSTAIN_STRENGTH,
            0.0,
        ],
        frame,
    ) if ENABLE_STAGED_EXPANSION else 0.0

    if not ENABLE_HEM_DRAG:
        phase = (
            "SEW_GRAVITY"
            if frame <= frames["sewing_release_end"]
            else "GRAVITY_SETTLE"
        )
        print(
            f"[CC FORCE] F{scene.frame_current:03d} phase={phase} "
            f"sew={sewing:.2f} gravity={gravity:.2f} "
            f"roofPin={roof_pin:.2f} selfCollision={self_collision} "
            f"expand=OFF hem=GRAVITY_ONLY generatedFields=OFF "
            f"effectorForce=0 effectorWind=0"
        )
        return

    hem_drag = scheduled_strength(
        [
            frames["hem_drag_start"],
            frames["hem_drag_end"],
        ],
        [
            0.0,
            1.0,
        ],
        frame,
    )
    hem_level = scheduled_strength(
        [
            frames["hem_level_start"],
            frames["hem_level_end"],
        ],
        [
            0.0,
            1.0,
        ],
        frame,
    )

    if frame <= frames["sewing_release_end"]:
        phase = "SEW_GRAVITY"
    elif frame <= frames["hem_level_start"]:
        phase = "HEM_BASE_TENSION"
    elif frame <= frames["hem_level_end"]:
        phase = "HEM_LEVEL_TRIM"
    else:
        phase = "HEM_HOLD"

    print(
        f"[CC FORCE] F{scene.frame_current:03d} phase={phase} "
        f"sew={sewing:.2f} gravity={gravity:.2f} expand={expansion:.2f} "
        f"hemBase={hem_drag:.3f} hemLevel={hem_level:.3f} "
        f"hemFields=0 hemPin=OFF "
        f"collisionSlide=ON"
    )


def ensure_force_stage_handler():
    """Register exactly one current-version frame handler."""

    handlers = bpy.app.handlers.frame_change_pre
    for handler in list(handlers):
        if getattr(handler, "car_cover_force_stage_handler", False):
            handlers.remove(handler)
    car_cover_force_stage_handler.car_cover_force_stage_handler = True
    handlers.append(car_cover_force_stage_handler)


def animate_field_strength(field_object, keyed_strengths):
    """Store a linear schedule evaluated by a frame handler, not an Action."""

    # Remove V5/V6 Action data that can trigger RIGIDBODY_REBUILD dependency
    # errors for force-field empties in Blender 5.x.
    field_object.animation_data_clear()

    ordered = sorted((float(frame), float(value)) for frame, value in keyed_strengths)
    field_object["car_cover_force_schedule"] = True
    field_object["car_cover_force_frames"] = [item[0] for item in ordered]
    field_object["car_cover_force_strengths"] = [item[1] for item in ordered]

    ensure_force_stage_handler()
    car_cover_force_stage_handler(bpy.context.scene)


def staged_frames():
    """Return absolute stage frames derived from the scene start frame."""

    start = bpy.context.scene.frame_start
    return {
        "start": start,
        "top_down_ramp_end": start + TOP_DOWN_RAMP_END,
        "top_down_hold_end": start + TOP_DOWN_HOLD_END,
        "top_down_release_end": start + TOP_DOWN_RELEASE_END,
        "sewing_ramp_start": start + SEWING_RAMP_START,
        "sewing_ramp_end": start + SEWING_RAMP_END,
        "sewing_release_start": start + SEWING_RELEASE_START,
        "sewing_release_end": start + SEWING_RELEASE_END,
        "bending_recovery_start": start + BENDING_RECOVERY_START,
        "bending_recovery_end": start + BENDING_RECOVERY_END,
        "gravity_ramp_start": start + GRAVITY_RAMP_START,
        "gravity_ramp_end": start + GRAVITY_RAMP_END,
        "roof_pin_hold_end": start + ROOF_PIN_HOLD_END,
        "roof_pin_release_end": start + ROOF_PIN_RELEASE_END,
        "self_collision_start": start + SELF_COLLISION_START,
        "expand_ramp_start": start + EXPANSION_RAMP_START,
        "expand_ramp_end": start + EXPANSION_RAMP_END,
        "expand_hold_end": start + EXPANSION_HOLD_END,
        "expand_sustain_start": start + EXPANSION_SUSTAIN_START,
        "expand_release_start": start + EXPANSION_RELEASE_START,
        "expand_release_end": start + EXPANSION_RELEASE_END,
        "hem_drag_start": start + HEM_DRAG_START,
        "hem_drag_end": start + HEM_DRAG_END,
        "hem_level_start": start + HEM_LEVEL_START,
        "hem_level_end": start + HEM_LEVEL_END,
        "hem_drag_settle_end": start + HEM_DRAG_SETTLE_END,
        "drag_start": start + REAR_DRAG_START,
        "drag_ramp_start": start + REAR_DRAG_RAMP_START,
        "drag_ramp_end": start + REAR_DRAG_RAMP_END,
        "drag_hold_end": start + REAR_DRAG_HOLD_END,
        "drag_release_end": start + REAR_DRAG_RELEASE_END,
        "drag_sustain_end": start + REAR_DRAG_SUSTAIN_END,
    }


def configure_sewing_force_driver(obj, modifier):
    """Close seams gradually, then reduce their persistent convergence force."""

    settings = modifier.settings
    settings.driver_remove("sewing_force_max")
    if not ENABLE_SEWING:
        settings.sewing_force_max = 0.0
        return "disabled"
    if not (0.0 < SEWING_FORCE_START <= MAX_SEWING_FORCE):
        raise RuntimeError(
            "SEWING_FORCE_START 必须大于 0 且不高于 MAX_SEWING_FORCE。"
        )

    if not (0.0 < SEWING_FORCE_SUSTAIN < MAX_SEWING_FORCE):
        raise RuntimeError(
            "SEWING_FORCE_SUSTAIN 必须大于 0 且低于 MAX_SEWING_FORCE。"
        )

    frames = staged_frames()
    ramp_start = float(frames["sewing_ramp_start"])
    ramp_end = float(frames["sewing_ramp_end"])
    release_start = float(frames["sewing_release_start"])
    release_end = float(frames["sewing_release_end"])
    if ramp_end <= ramp_start:
        settings.sewing_force_max = MAX_SEWING_FORCE
        return f"constant {MAX_SEWING_FORCE:g}"
    if release_start < ramp_end or release_end <= release_start:
        raise RuntimeError("Sewing release 必须在 ramp 完成后开始并具有正帧长。")

    driver = settings.driver_add("sewing_force_max").driver
    driver.type = "SCRIPTED"
    driver.expression = (
        f"{SEWING_FORCE_START:g}+"
        f"{MAX_SEWING_FORCE - SEWING_FORCE_START:g}*"
        f"max(0.0,min(1.0,(frame-{ramp_start:g})/"
        f"{ramp_end - ramp_start:g}))-"
        f"{MAX_SEWING_FORCE - SEWING_FORCE_SUSTAIN:g}*"
        f"max(0.0,min(1.0,(frame-{release_start:g})/"
        f"{release_end - release_start:g}))"
    )
    obj["cloth_sewing_force_start"] = SEWING_FORCE_START
    obj["cloth_sewing_force"] = MAX_SEWING_FORCE
    obj["cloth_sewing_force_sustain"] = SEWING_FORCE_SUSTAIN
    return (
        f"{SEWING_FORCE_START:g} -> {MAX_SEWING_FORCE:g} "
        f"by frame {ramp_end:g} -> {SEWING_FORCE_SUSTAIN:g} "
        f"by frame {release_end:g}"
    )


def configure_bending_stiffness_driver(obj, modifier):
    """Keep curved panels pliable while sewing, then restore denim bending."""

    settings = modifier.settings
    settings.driver_remove("bending_stiffness")
    if not 0.0 < BENDING_STIFFNESS_DURING_SEWING <= BENDING_STIFFNESS:
        raise RuntimeError(
            "BENDING_STIFFNESS_DURING_SEWING must be positive and no "
            "greater than BENDING_STIFFNESS"
        )

    frames = staged_frames()
    recovery_start = float(frames["bending_recovery_start"])
    recovery_end = float(frames["bending_recovery_end"])
    if recovery_end <= recovery_start:
        raise RuntimeError("Bending recovery requires a positive frame range")

    driver = settings.driver_add("bending_stiffness").driver
    driver.type = "SCRIPTED"
    driver.expression = (
        f"{BENDING_STIFFNESS_DURING_SEWING:g}+"
        f"{BENDING_STIFFNESS - BENDING_STIFFNESS_DURING_SEWING:g}*"
        f"max(0.0,min(1.0,(frame-{recovery_start:g})/"
        f"{recovery_end - recovery_start:g}))"
    )
    obj["cloth_bending_during_sewing"] = BENDING_STIFFNESS_DURING_SEWING
    obj["cloth_bending_final"] = BENDING_STIFFNESS
    return (
        f"{BENDING_STIFFNESS_DURING_SEWING:g} through frame "
        f"{recovery_start:g} -> {BENDING_STIFFNESS:g} by "
        f"frame {recovery_end:g}"
    )


def configure_gravity_driver(modifier):
    """Apply gravity from frame one and ramp it to full strength smoothly."""

    effector_weights = getattr(modifier.settings, "effector_weights", None)
    if effector_weights is None:
        return "unavailable"

    frames = staged_frames()
    ramp_start = float(frames["gravity_ramp_start"])
    ramp_end = float(frames["gravity_ramp_end"])
    effector_weights.driver_remove("gravity")
    driver = effector_weights.driver_add("gravity").driver
    driver.type = "SCRIPTED"
    driver.expression = (
        f"{SEWING_GRAVITY_FACTOR:g}+"
        f"{1.0 - SEWING_GRAVITY_FACTOR:g}*"
        f"max(0.0,min(1.0,(frame-{ramp_start:g})/"
        f"{ramp_end - ramp_start:g}))"
    )
    return (
        f"{SEWING_GRAVITY_FACTOR:g} -> 1 by frame {ramp_end:g}"
    )


def cloth_world_bounds(obj):
    """Return base-mesh world bounds and spans for expansion placement."""

    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    if not points:
        raise RuntimeError(f"{obj.name} 没有可用于定位展开力场的顶点。")

    minimum = points[0].copy()
    maximum = points[0].copy()
    for point in points[1:]:
        minimum.x = min(minimum.x, point.x)
        minimum.y = min(minimum.y, point.y)
        minimum.z = min(minimum.z, point.z)
        maximum.x = max(maximum.x, point.x)
        maximum.y = max(maximum.y, point.y)
        maximum.z = max(maximum.z, point.z)
    return minimum, maximum


def semantic_top_group_names(obj):
    """Return explicit groups that identify TOP without spatial guessing."""

    names = []
    for group in obj.vertex_groups:
        name = group.name
        is_named_panel = name in TOP_PANEL_GROUP_NAMES
        is_legacy_top_seam = name.startswith("SEAM_TOP_")
        parts = name.split("_")
        sewing_id = parts[0] if parts else ""
        is_semantic_top_seam = (
            len(parts) >= 2
            and sewing_id.startswith("S")
            and sewing_id[1:].isdigit()
            and parts[1] == "TOP"
            and not name.endswith(("_A", "_B"))
        )
        if is_named_panel or is_legacy_top_seam or is_semantic_top_seam:
            names.append(name)
    return names


def vertex_indices_in_groups(obj, group_names):
    """Return vertices with a non-zero weight in any named group."""

    group_indices = {
        obj.vertex_groups[name].index
        for name in group_names
        if obj.vertex_groups.get(name) is not None
    }
    return {
        vertex.index
        for vertex in obj.data.vertices
        if any(
            item.group in group_indices and item.weight > 0.001
            for item in vertex.groups
        )
    }


def panel_component_from_seeds(obj, seed_indices):
    """Find the face-connected panel containing the most semantic TOP seeds."""

    adjacency = [[] for _vertex in obj.data.vertices]
    for edge in obj.data.edges:
        # Loose edges are sewing springs. They must not merge separate pattern
        # panels while we identify the physical TOP panel.
        if getattr(edge, "is_loose", False):
            continue
        index_a, index_b = edge.vertices
        adjacency[index_a].append(index_b)
        adjacency[index_b].append(index_a)

    remaining = set(range(len(obj.data.vertices)))
    best_component = set()
    best_seed_count = 0
    while remaining:
        start = remaining.pop()
        component = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbor in adjacency[current]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        seed_count = len(component.intersection(seed_indices))
        if seed_count > best_seed_count:
            best_component = component
            best_seed_count = seed_count
    return best_component


def ensure_roof_pin_group(obj):
    """Return or create a small center anchor on the semantic TOP panel."""

    group = obj.vertex_groups.get(PIN_GROUP_NAME)
    existing = (
        vertex_indices_in_groups(obj, (PIN_GROUP_NAME,))
        if group is not None
        else set()
    )
    if existing:
        group.add(sorted(existing), PIN_VERTEX_WEIGHT, "REPLACE")
        return group, sorted(existing), f"existing ({len(existing)} vertices)"
    if not AUTO_CREATE_ROOF_PIN:
        return group, [], "missing; auto-create disabled"

    top_groups = semantic_top_group_names(obj)
    top_seeds = vertex_indices_in_groups(obj, top_groups)
    if not top_seeds:
        return group, [], "missing semantic TOP groups"
    component = panel_component_from_seeds(obj, top_seeds)
    if not component:
        return group, [], "could not identify a face-connected TOP panel"

    centroid = Vector((0.0, 0.0, 0.0))
    for vertex_index in component:
        centroid += obj.data.vertices[vertex_index].co
    centroid /= len(component)
    count = min(max(1, AUTO_ROOF_PIN_VERTEX_COUNT), len(component))
    pin_indices = sorted(
        component,
        key=lambda index: (
            obj.data.vertices[index].co - centroid
        ).length_squared,
    )[:count]

    if group is None:
        group = obj.vertex_groups.new(name=PIN_GROUP_NAME)
    all_indices = list(range(len(obj.data.vertices)))
    if all_indices:
        group.remove(all_indices)
    group.add(pin_indices, PIN_VERTEX_WEIGHT, "REPLACE")
    obj["cloth_auto_roof_pin"] = True
    obj["cloth_auto_roof_pin_source_groups"] = ",".join(top_groups)
    obj["cloth_auto_roof_pin_panel_vertices"] = len(component)
    return group, sorted(pin_indices), (
        f"auto-created {len(pin_indices)} center vertices from "
        f"{', '.join(top_groups)}"
    )


def configure_roof_pin_driver(obj, modifier, pin_group, pin_indices):
    """Hold TOP briefly during sewing, then fully release its XYZ anchor."""

    settings = modifier.settings
    settings.driver_remove("pin_stiffness")
    if (
        not ENABLE_ROOF_PIN_DURING_SIMULATION
        or pin_group is None
        or not pin_indices
    ):
        settings.vertex_group_mass = ""
        settings.pin_stiffness = 0.0
        return "disabled"

    hold_end = bpy.context.scene.frame_start + ROOF_PIN_HOLD_END
    release_end = bpy.context.scene.frame_start + ROOF_PIN_RELEASE_END
    if release_end <= hold_end:
        raise RuntimeError("ROOF_PIN_RELEASE_END must be after ROOF_PIN_HOLD_END")

    pin_group.add(pin_indices, PIN_VERTEX_WEIGHT, "REPLACE")
    settings.vertex_group_mass = pin_group.name
    settings.pin_stiffness = PIN_STIFFNESS
    driver = settings.driver_add("pin_stiffness").driver
    driver.type = "SCRIPTED"
    driver.expression = (
        f"{PIN_STIFFNESS:g}*(1-max(0.0,min(1.0,(frame-{hold_end:g})/"
        f"{release_end - hold_end:g})))"
    )
    obj["cloth_roof_pin_hold_end"] = hold_end
    obj["cloth_roof_pin_release_end"] = release_end
    return (
        f"{PIN_STIFFNESS:g} through frame {hold_end} -> 0 at frame "
        f"{release_end} ({len(pin_indices)} vertices)"
    )


def configure_self_collision_driver(obj, modifier):
    """Enable self-collision at the configured offset (V27: scene start)."""

    collision = modifier.collision_settings
    collision.driver_remove("use_self_collision")
    if not ENABLE_SELF_COLLISION:
        collision.use_self_collision = False
        return "disabled"

    enable_frame = bpy.context.scene.frame_start + SELF_COLLISION_START
    collision.use_self_collision = True
    driver = collision.driver_add("use_self_collision").driver
    driver.type = "SCRIPTED"
    driver.expression = f"1 if frame>={enable_frame} else 0"
    obj["cloth_self_collision_enable_frame"] = enable_frame
    return f"OFF before frame {enable_frame}; ON from frame {enable_frame}"


def vertex_groups_world_centroid(obj, group_names):
    """Return the world centroid of the union of explicit vertex groups."""

    group_indices = {
        obj.vertex_groups[name].index
        for name in group_names
        if obj.vertex_groups.get(name) is not None
    }
    points = []
    for vertex in obj.data.vertices:
        if any(
            item.group in group_indices and item.weight > 0.001
            for item in vertex.groups
        ):
            points.append(obj.matrix_world @ vertex.co)

    if not points:
        return None
    centroid = points[0].copy()
    for point in points[1:]:
        centroid += point
    centroid /= len(points)
    return centroid


def configure_top_down_guide(obj):
    """Create a temporary downward Wind above the explicitly named TOP."""

    if not ENABLE_TOP_DOWN_GUIDE:
        old_name = str(
            obj.get(
                "cloth_top_down_object",
                f"{TOP_DOWN_OBJECT_PREFIX}{obj.name}",
            )
        )
        old_object = bpy.data.objects.get(old_name)
        cleared = disable_generated_field(old_object)
        obj["cloth_top_down_object"] = ""
        return None, "disabled; old field cleared" if cleared else "disabled"

    top_groups = semantic_top_group_names(obj)
    top_center = vertex_groups_world_centroid(obj, top_groups)
    if top_center is None:
        return None, "missing PANEL_TOP / Sxxx_TOP / SEAM_TOP_* groups"

    location = top_center.copy()
    location.z += TOP_DOWN_HEIGHT_MM / 1000.0
    field_name = f"{TOP_DOWN_OBJECT_PREFIX}{obj.name}"
    field_object = get_or_create_force_field_object(field_name, location)
    field_object.location = location
    field_object.rotation_euler = (3.141592653589793, 0.0, 0.0)
    field_object.empty_display_type = "CIRCLE"
    field_object.empty_display_size = 0.18
    field_object.show_in_front = True

    field = field_object.field
    field.type = "WIND"
    field.shape = "PLANE"
    field.apply_to_location = True
    field.apply_to_rotation = False
    field.falloff_type = "SPHERE"
    field.falloff_power = TOP_DOWN_FALLOFF_POWER
    field.use_min_distance = True
    field.distance_min = TOP_DOWN_MIN_DISTANCE_MM / 1000.0
    field.use_max_distance = True
    field.distance_max = TOP_DOWN_MAX_DISTANCE_MM / 1000.0

    frames = staged_frames()
    animate_field_strength(
        field_object,
        [
            (frames["start"], 0.0),
            (frames["top_down_ramp_end"], TOP_DOWN_STRENGTH),
            (frames["top_down_hold_end"], TOP_DOWN_STRENGTH),
            (frames["top_down_release_end"], 0.0),
        ],
    )

    obj["cloth_top_down_object"] = field_object.name
    obj["cloth_top_down_groups"] = ",".join(top_groups)
    obj["cloth_top_down_peak_strength"] = TOP_DOWN_STRENGTH
    return field_object, f"ready from {', '.join(top_groups)}"


def configure_expansion_fields(obj, has_pin):
    """Create bounded radial fields that unfold and weakly sustain the cover."""

    if not ENABLE_STAGED_EXPANSION:
        old_names = {
            f"{EXPANSION_OBJECT_PREFIX}{index + 1}_{obj.name}"
            for index in range(EXPANSION_FIELD_COUNT)
        }
        stored_names = str(obj.get("cloth_expansion_objects", ""))
        old_names.update(name for name in stored_names.split(",") if name)

        cleared = 0
        for field_name in old_names:
            field_object = bpy.data.objects.get(field_name)
            if field_object is None:
                continue
            field_object.animation_data_clear()
            for property_name in (
                "car_cover_force_schedule",
                "car_cover_force_frames",
                "car_cover_force_strengths",
            ):
                if property_name in field_object:
                    del field_object[property_name]
            if field_object.field is not None:
                field_object.field.strength = 0.0
            field_object.hide_set(True)
            cleared += 1

        obj["cloth_expansion_objects"] = ""
        return [], f"disabled; cleared {cleared} old fields"
    if REQUIRE_PIN_FOR_EXPANSION and not has_pin:
        return [], f"missing {PIN_GROUP_NAME}"

    minimum, maximum = cloth_world_bounds(obj)
    span_x = maximum.x - minimum.x
    span_y = maximum.y - minimum.y
    marker = bpy.data.objects.get(EXPANSION_CENTER_OBJECT_NAME)
    if marker is not None:
        center = marker.matrix_world.translation.copy()
        placement_source = f"{EXPANSION_CENTER_OBJECT_NAME} X/Y + forced-above Z"
    else:
        center = minimum.copy()
        center.x = (minimum.x + maximum.x) * 0.5
        center.y = (minimum.y + maximum.y) * 0.5
        placement_source = "cloth bounds + forced-above Z"
    # A radial Force located inside/below the cover pushes upper panels upward.
    # Force every expansion center above the highest base-mesh vertex so all
    # vertical components point down while horizontal components still unfold.
    center.z = maximum.z + EXPANSION_FORCE_ABOVE_TOP_MM / 1000.0

    use_x_axis = span_x >= span_y
    length_span = span_x if use_x_axis else span_y
    frames = staged_frames()
    fields = []

    for index in range(EXPANSION_FIELD_COUNT):
        fraction = 0.0
        if EXPANSION_FIELD_COUNT > 1:
            fraction = (index / (EXPANSION_FIELD_COUNT - 1)) * 2.0 - 1.0

        location = center.copy()
        offset = fraction * length_span * EXPANSION_AXIS_SPREAD
        if use_x_axis:
            location.x += offset
        else:
            location.y += offset

        field_name = f"{EXPANSION_OBJECT_PREFIX}{index + 1}_{obj.name}"
        field_object = get_or_create_force_field_object(field_name, location)
        field_object.hide_set(False)
        field_object.location = location
        field_object.empty_display_type = "SPHERE"
        field_object.empty_display_size = 0.16
        field_object.show_in_front = True

        field = field_object.field
        field.type = "FORCE"
        field.shape = "POINT"
        field.apply_to_location = True
        field.apply_to_rotation = False
        field.falloff_type = "SPHERE"
        field.falloff_power = EXPANSION_FALLOFF_POWER
        field.use_min_distance = True
        field.distance_min = EXPANSION_MIN_DISTANCE_MM / 1000.0
        field.use_max_distance = True
        field.distance_max = EXPANSION_MAX_DISTANCE_MM / 1000.0

        animate_field_strength(
            field_object,
            [
                (frames["start"], 0.0),
                (frames["expand_ramp_start"], 0.0),
                (frames["expand_ramp_end"], EXPANSION_STRENGTH),
                (frames["expand_hold_end"], EXPANSION_STRENGTH),
                (
                    frames["expand_sustain_start"],
                    EXPANSION_SUSTAIN_STRENGTH,
                ),
                (
                    frames["expand_release_start"],
                    EXPANSION_SUSTAIN_STRENGTH,
                ),
                (frames["expand_release_end"], 0.0),
            ],
        )
        fields.append(field_object)

    obj["cloth_expansion_objects"] = ",".join(item.name for item in fields)
    obj["cloth_expansion_peak_strength"] = EXPANSION_STRENGTH
    obj["cloth_expansion_sustain_strength"] = EXPANSION_SUSTAIN_STRENGTH
    return fields, f"ready from {placement_source}"


def clear_legacy_rear_pull_fields(obj):
    """Disable rear Wind fields generated by the V7/V8 implementation."""

    names = {
        name
        for name in str(obj.get("cloth_rear_pull_objects", "")).split(",")
        if name
    }
    names.add(f"{LEGACY_REAR_PULL_OBJECT_PREFIX}{obj.name}")
    for candidate in bpy.data.objects:
        if candidate.name.startswith(LEGACY_REAR_PULL_OBJECT_PREFIX) and (
            candidate.name.endswith(f"_{obj.name}")
            or candidate.name == f"{LEGACY_REAR_PULL_OBJECT_PREFIX}{obj.name}"
        ):
            names.add(candidate.name)

    cleared = 0
    for name in names:
        if disable_generated_field(bpy.data.objects.get(name)):
            cleared += 1

    obj["cloth_rear_pull_objects"] = ""
    obj["cloth_rear_pull_object"] = ""
    return cleared


def clear_hem_down_fields(obj):
    """Disable HEM directional winds previously generated for this cloth."""

    names = {
        name
        for name in str(obj.get("cloth_hem_down_objects", "")).split(",")
        if name
    }
    suffix = f"_{obj.name}"
    for candidate in bpy.data.objects:
        if candidate.name.startswith(HEM_DOWN_OBJECT_PREFIX) and (
            candidate.name.endswith(suffix) or candidate.name in names
        ):
            names.add(candidate.name)

    cleared = 0
    for name in names:
        if disable_generated_field(bpy.data.objects.get(name)):
            cleared += 1
    obj["cloth_hem_down_objects"] = ""
    return cleared


def source_group_vertex_weights(obj, group_name):
    """Return ``(vertex index, weight)`` pairs from one vertex group."""

    group = obj.vertex_groups.get(group_name)
    if group is None:
        return []

    result = []
    for vertex in obj.data.vertices:
        for item in vertex.groups:
            if item.group == group.index and item.weight > 0.001:
                result.append((vertex.index, item.weight))
                break
    return result


def replace_weight_group(obj, group_name, weighted_indices):
    """Replace one generated group without modifying semantic source groups."""

    old_group = obj.vertex_groups.get(group_name)
    if old_group is not None:
        obj.vertex_groups.remove(old_group)
    group = obj.vertex_groups.new(name=group_name)
    for vertex_index, weight in weighted_indices:
        group.add([vertex_index], min(1.0, max(0.0, weight)), "REPLACE")
    return group


def rebuild_rear_drag_pin_groups(obj, source_weights, roof_weights):
    """Build a roof base group plus a separately animated HEM contribution."""

    base_weights = {}
    for vertex_index, source_weight in roof_weights:
        # PIN_ROOF already contains the configured pin weight.
        base_weights[vertex_index] = min(1.0, source_weight)
    # Keep a tiny HEM membership so Cloth creates its pin constraints at frame
    # start. The animated mix adds the usable weight only during the drag.
    for vertex_index, source_weight in source_weights:
        base_weights[vertex_index] = max(
            base_weights.get(vertex_index, 0.0),
            min(1.0, source_weight * REAR_DRAG_RELEASE_VERTEX_WEIGHT),
        )
    pin_group = replace_weight_group(
        obj,
        REAR_DRAG_PIN_GROUP_NAME,
        base_weights.items(),
    )
    drag_group = replace_weight_group(
        obj,
        REAR_DRAG_WEIGHT_GROUP_NAME,
        (
            (vertex_index, source_weight * REAR_DRAG_VERTEX_WEIGHT)
            for vertex_index, source_weight in source_weights
        ),
    )
    return pin_group, drag_group


def get_or_create_rear_drag_weight_modifier(obj, cloth_modifier):
    """Create a VGroup mixer and place it immediately before Cloth."""

    modifier = obj.modifiers.get(REAR_DRAG_MIX_MODIFIER_NAME)
    if modifier is not None and modifier.type != "VERTEX_WEIGHT_MIX":
        modifier = None
    if modifier is None:
        modifier = obj.modifiers.new(
            name=REAR_DRAG_MIX_MODIFIER_NAME,
            type="VERTEX_WEIGHT_MIX",
        )

    modifier.vertex_group_a = REAR_DRAG_PIN_GROUP_NAME
    modifier.vertex_group_b = REAR_DRAG_WEIGHT_GROUP_NAME
    modifier.mix_mode = "ADD"
    modifier.mix_set = "OR"
    modifier.normalize = False
    modifier.show_viewport = True
    modifier.show_render = True

    mix_index = obj.modifiers.find(modifier.name)
    cloth_index = obj.modifiers.find(cloth_modifier.name)
    if mix_index > cloth_index:
        obj.modifiers.move(mix_index, cloth_index)
    return modifier


def get_or_create_roof_pin_release_modifier(obj, cloth_modifier):
    """Remove PIN_ROOF from the combined pin group during frames 10-16."""

    modifier = obj.modifiers.get(ROOF_PIN_RELEASE_MIX_MODIFIER_NAME)
    if modifier is not None and modifier.type != "VERTEX_WEIGHT_MIX":
        raise RuntimeError(
            f"{ROOF_PIN_RELEASE_MIX_MODIFIER_NAME} exists but is not a "
            "Vertex Weight Mix modifier"
        )
    if modifier is None:
        modifier = obj.modifiers.new(
            name=ROOF_PIN_RELEASE_MIX_MODIFIER_NAME,
            type="VERTEX_WEIGHT_MIX",
        )

    modifier.vertex_group_a = REAR_DRAG_PIN_GROUP_NAME
    modifier.vertex_group_b = PIN_GROUP_NAME
    modifier.mix_mode = "SUB"
    modifier.mix_set = "A"
    modifier.normalize = False
    modifier.show_viewport = True
    modifier.show_render = True
    if hasattr(modifier, "default_weight_b"):
        modifier.default_weight_b = 0.0

    frames = staged_frames()
    release_start = float(frames["roof_pin_hold_end"])
    release_end = float(frames["roof_pin_release_end"])
    modifier.driver_remove("mask_constant")
    driver = modifier.driver_add("mask_constant").driver
    driver.type = "SCRIPTED"
    driver.expression = (
        f"max(0.0,min(1.0,(frame-{release_start:g})/"
        f"{release_end - release_start:g}))"
    )

    current_index = obj.modifiers.find(modifier.name)
    cloth_index = obj.modifiers.find(cloth_modifier.name)
    if current_index > cloth_index:
        obj.modifiers.move(current_index, cloth_index)
    return modifier


def order_dynamic_pin_modifiers(obj, roof_release, hem_add, cloth_modifier):
    """Keep roof release and HEM acquisition directly before Cloth."""

    for modifier in (roof_release, hem_add):
        current_index = obj.modifiers.find(modifier.name)
        cloth_index = obj.modifiers.find(cloth_modifier.name)
        target_index = max(0, cloth_index - 1)
        if current_index != target_index:
            obj.modifiers.move(current_index, target_index)


def get_or_rebuild_rear_drag_shape_key(
    obj,
    source_weights,
    source_weights_by_group,
):
    """Create independent straight-down targets for the front and rear hems."""

    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)

    key_blocks = obj.data.shape_keys.key_blocks
    basis = key_blocks[0]
    target = key_blocks.get(REAR_DRAG_SHAPE_KEY_NAME)
    if target is None:
        target = obj.shape_key_add(name=REAR_DRAG_SHAPE_KEY_NAME, from_mix=False)

    for vertex_index in range(len(obj.data.vertices)):
        target.data[vertex_index].co = basis.data[vertex_index].co

    inverse_world = obj.matrix_world.inverted_safe()
    source_world_points = {
        vertex_index: obj.matrix_world @ basis.data[vertex_index].co
        for vertex_index, _source_weight in source_weights
    }
    target_z_by_vertex = {}
    group_target_z = {}
    group_vertex_indices = {}
    for group_name, group_weights in source_weights_by_group.items():
        if not group_weights:
            continue
        group_vertex_indices[group_name] = {
            vertex_index for vertex_index, _source_weight in group_weights
        }
        lowest_source_z = min(
            source_world_points[vertex_index].z
            for vertex_index, _source_weight in group_weights
        )
        target_z = lowest_source_z - REAR_DRAG_DISTANCE_MM / 1000.0
        group_target_z[group_name] = target_z
        for vertex_index, _source_weight in group_weights:
            target_z_by_vertex[vertex_index] = min(
                target_z_by_vertex.get(vertex_index, target_z),
                target_z,
            )

    actual_down_distances_mm = []
    actual_down_by_group = {name: [] for name in source_weights_by_group}

    for vertex_index, _source_weight in source_weights:
        world_point = source_world_points[vertex_index]
        world_target = world_point.copy()
        if REAR_DRAG_LEVEL_TO_LOWEST:
            world_target.z = target_z_by_vertex[vertex_index]
        else:
            world_target.z -= REAR_DRAG_DISTANCE_MM / 1000.0
        actual_down_mm = (world_point.z - world_target.z) * 1000.0
        actual_down_distances_mm.append(actual_down_mm)
        for group_name, vertex_indices in group_vertex_indices.items():
            if vertex_index in vertex_indices:
                actual_down_by_group[group_name].append(actual_down_mm)
        target.data[vertex_index].co = inverse_world @ world_target

    obj["cloth_rear_drag_level_to_lowest"] = REAR_DRAG_LEVEL_TO_LOWEST
    obj["cloth_rear_drag_target_z_world"] = min(group_target_z.values())
    obj["cloth_rear_drag_min_actual_down_mm"] = min(actual_down_distances_mm)
    obj["cloth_rear_drag_max_actual_down_mm"] = max(actual_down_distances_mm)
    for group_name, distances in actual_down_by_group.items():
        if distances:
            obj[f"cloth_{group_name}_target_z_world"] = group_target_z[group_name]
            obj[f"cloth_{group_name}_min_actual_down_mm"] = min(distances)
            obj[f"cloth_{group_name}_max_actual_down_mm"] = max(distances)
    target.value = 0.0
    return target


def disable_rear_drag(obj, modifier):
    """Deactivate a previously generated drag while retaining reusable data."""

    obj["car_cover_rear_drag_schedule"] = False
    shape_keys = getattr(obj.data, "shape_keys", None)
    if shape_keys is not None:
        target_names = {
            HEM_FEEDBACK_SHAPE_KEY_NAME,
            REAR_DRAG_SHAPE_KEY_NAME,
            HEM_LEVEL_SHAPE_KEY_NAME,
            str(
                obj.get(
                    "car_cover_rear_drag_shape_key",
                    REAR_DRAG_SHAPE_KEY_NAME,
                )
            ),
            str(obj.get("cloth_hem_drag_shape_key", "")),
            str(obj.get("cloth_hem_level_shape_key", "")),
        }
        for target_name in target_names:
            target = shape_keys.key_blocks.get(target_name)
            if target is not None:
                target.driver_remove("value")
                target.value = 0.0

    mix_modifier = obj.modifiers.get(REAR_DRAG_MIX_MODIFIER_NAME)
    if mix_modifier is not None and mix_modifier.type == "VERTEX_WEIGHT_MIX":
        mix_modifier.driver_remove("mask_constant")
        mix_modifier.mask_constant = 0.0
        mix_modifier.show_viewport = False
        mix_modifier.show_render = False
    generated_pin_name = str(
        obj.get("car_cover_rear_drag_pin_group", REAR_DRAG_PIN_GROUP_NAME)
    )
    if modifier.settings.vertex_group_mass == generated_pin_name:
        modifier.settings.driver_remove("pin_stiffness")
        modifier.settings.vertex_group_mass = ""
        modifier.settings.pin_stiffness = 0.0


def configure_rear_drag(obj, modifier):
    """Create localized, mostly vertical winds for both semantic HEM groups."""

    old_field_count = clear_legacy_rear_pull_fields(obj)
    old_field_count += clear_hem_down_fields(obj)

    # Explicitly remove the V16 XYZ HEM goal. Its fixed Basis X/Y coordinates
    # are the source of the unwanted front/rear snap seen after frame 50.
    disable_rear_drag(obj, modifier)

    if not ENABLE_REAR_DRAG:
        return None, f"disabled; cleared {old_field_count} old fields"

    if HEM_DOWN_FIELD_COUNT_PER_GROUP < 1:
        raise RuntimeError("HEM_DOWN_FIELD_COUNT_PER_GROUP 必须至少为 1。")
    if HEM_DOWN_STRENGTH <= 0.0:
        raise RuntimeError("HEM_DOWN_STRENGTH 必须大于 0。")
    if not (
        0.0 < HEM_DOWN_SUSTAIN_STRENGTH
        <= HEM_DOWN_EARLY_STRENGTH
        < HEM_DOWN_STRENGTH
    ):
        raise RuntimeError(
            "HEM down 强度必须满足 0 < sustain <= early < peak。"
        )
    if not (0.0 <= HEM_SLIDE_HORIZONTAL_FACTOR <= 0.25):
        raise RuntimeError("HEM_SLIDE_HORIZONTAL_FACTOR 必须在 0 到 0.25 之间。")
    if not (0.0 < HEM_DOWN_MIN_DISTANCE_MM < HEM_DOWN_MAX_DISTANCE_MM):
        raise RuntimeError("HEM down Wind 的最小作用距离必须小于最大作用距离。")

    all_source_weights_by_group = {
        group_name: source_group_vertex_weights(obj, group_name)
        for group_name in HEM_DRAG_GROUP_NAMES
    }
    missing_groups = [
        group_name
        for group_name, weights in all_source_weights_by_group.items()
        if not weights
    ]
    source_weights_by_group = {
        group_name: weights
        for group_name, weights in all_source_weights_by_group.items()
        if weights
    }
    if not source_weights_by_group:
        return None, f"missing or empty {' / '.join(HEM_DRAG_GROUP_NAMES)}"

    minimum, maximum = cloth_world_bounds(obj)
    cloth_center = (minimum + maximum) * 0.5
    frames = staged_frames()
    field_objects = []
    direction_notes = []

    for group_name, group_weights in source_weights_by_group.items():
        points = [
            obj.matrix_world @ obj.data.vertices[vertex_index].co
            for vertex_index, _weight in group_weights
        ]
        center = points[0].copy()
        for point in points[1:]:
            center += point
        center /= len(points)

        span_x = max(point.x for point in points) - min(point.x for point in points)
        span_y = max(point.y for point in points) - min(point.y for point in points)
        spread_axis = 0 if span_x >= span_y else 1
        ordered_points = sorted(points, key=lambda point: point[spread_axis])

        outward = Vector((center.x - cloth_center.x, center.y - cloth_center.y, 0.0))
        if outward.length_squared > 1.0e-12:
            outward.normalize()
        direction = Vector(
            (
                outward.x * HEM_SLIDE_HORIZONTAL_FACTOR,
                outward.y * HEM_SLIDE_HORIZONTAL_FACTOR,
                -1.0,
            )
        )
        direction.normalize()

        for field_index in range(HEM_DOWN_FIELD_COUNT_PER_GROUP):
            fraction = (field_index + 0.5) / HEM_DOWN_FIELD_COUNT_PER_GROUP
            point_index = round(fraction * (len(ordered_points) - 1))
            location = ordered_points[point_index].copy()
            location.z += HEM_DOWN_HEIGHT_MM / 1000.0
            field_name = (
                f"{HEM_DOWN_OBJECT_PREFIX}{group_name}_{field_index + 1}_"
                f"{obj.name}"
            )
            field_object = get_or_create_force_field_object(field_name, location)
            field_object.hide_set(False)
            field_object.location = location
            field_object.rotation_euler = Vector(
                (0.0, 0.0, 1.0)
            ).rotation_difference(direction).to_euler()
            field_object.empty_display_type = "CIRCLE"
            field_object.empty_display_size = 0.14
            field_object.show_in_front = True

            field = field_object.field
            field.type = "WIND"
            field.shape = "PLANE"
            field.apply_to_location = True
            field.apply_to_rotation = False
            field.falloff_type = "SPHERE"
            field.falloff_power = HEM_DOWN_FALLOFF_POWER
            field.use_min_distance = True
            field.distance_min = HEM_DOWN_MIN_DISTANCE_MM / 1000.0
            field.use_max_distance = True
            field.distance_max = HEM_DOWN_MAX_DISTANCE_MM / 1000.0

            animate_field_strength(
                field_object,
                [
                    (frames["start"], 0.0),
                    (frames["drag_start"], 0.0),
                    (frames["drag_ramp_start"], HEM_DOWN_EARLY_STRENGTH),
                    (frames["drag_ramp_end"], HEM_DOWN_STRENGTH),
                    (frames["drag_hold_end"], HEM_DOWN_STRENGTH),
                    (frames["drag_release_end"], HEM_DOWN_SUSTAIN_STRENGTH),
                    (frames["drag_sustain_end"], HEM_DOWN_SUSTAIN_STRENGTH),
                ],
            )
            field_object["cloth_hem_group"] = group_name
            field_object["cloth_hem_field_index"] = field_index + 1
            field_object["cloth_hem_direction_world"] = list(direction)
            field_objects.append(field_object)
        direction_notes.append(
            f"{group_name}=({direction.x:+.3f},{direction.y:+.3f},"
            f"{direction.z:+.3f})"
        )

    obj["car_cover_rear_drag_driver"] = False
    obj["cloth_rear_drag_group"] = ",".join(HEM_DRAG_GROUP_NAMES)
    obj["cloth_hem_drag_groups"] = ",".join(HEM_DRAG_GROUP_NAMES)
    obj["cloth_hem_down_objects"] = ",".join(item.name for item in field_objects)
    obj["cloth_hem_down_strength"] = HEM_DOWN_STRENGTH
    obj["cloth_hem_down_early_strength"] = HEM_DOWN_EARLY_STRENGTH
    obj["cloth_hem_down_sustain_strength"] = HEM_DOWN_SUSTAIN_STRENGTH
    obj["cloth_hem_slide_horizontal_factor"] = HEM_SLIDE_HORIZONTAL_FACTOR
    obj["cloth_roof_guide_vertex_count"] = 0

    ensure_force_stage_handler()
    car_cover_force_stage_handler(bpy.context.scene)
    bpy.context.view_layer.update()
    old_field_note = (
        f", cleared {old_field_count} old fields" if old_field_count else ""
    )
    group_counts = ", ".join(
        f"{group_name}={len(weights)}"
        for group_name, weights in source_weights_by_group.items()
    )
    return field_objects[0], (
        f"ready ({group_counts}, missing={', '.join(missing_groups) or 'none'}, "
        f"Wind fields={len(field_objects)}, each "
        f"0->{HEM_DOWN_EARLY_STRENGTH:g}->{HEM_DOWN_STRENGTH:g}->"
        f"{HEM_DOWN_SUSTAIN_STRENGTH:g}, "
        f"directions {'; '.join(direction_notes)}, "
        f"XYZ HEM Pin=OFF{old_field_note})"
    )


def _capture_cloth_world_trajectory_v24(
    obj,
    modifier,
    vertex_indices,
    end_frame,
):
    """Evaluate Cloth sequentially and sample indexed vertices through a frame."""

    scene = bpy.context.scene
    start_frame = scene.frame_start
    cloth_index = obj.modifiers.find(modifier.name)
    downstream = []
    for index, downstream_modifier in enumerate(obj.modifiers):
        if index > cloth_index:
            downstream.append(
                (downstream_modifier, downstream_modifier.show_viewport)
            )
            downstream_modifier.show_viewport = False

    try:
        trajectory = {}
        for current_frame in range(start_frame, int(end_frame) + 1):
            scene.frame_set(current_frame)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated = obj.evaluated_get(depsgraph)
            if len(evaluated.data.vertices) != len(obj.data.vertices):
                raise RuntimeError(
                    "Cannot map HEM vertices after Cloth: evaluated topology "
                    f"has {len(evaluated.data.vertices)} vertices, base mesh has "
                    f"{len(obj.data.vertices)}."
                )
            trajectory[current_frame] = {
                vertex_index: evaluated.matrix_world
                @ evaluated.data.vertices[vertex_index].co.copy()
                for vertex_index in vertex_indices
            }
        return trajectory
    finally:
        for downstream_modifier, was_visible in downstream:
            downstream_modifier.show_viewport = was_visible
        scene.frame_set(start_frame)


def _configure_hem_dynamic_drag_v24(obj, modifier):
    """Grab frame-18 HEM positions and pin-drag them to one world height."""

    cleared_fields = clear_legacy_rear_pull_fields(obj)
    cleared_fields += clear_hem_down_fields(obj)
    disable_rear_drag(obj, modifier)

    settings = modifier.settings
    if hasattr(settings, "use_dynamic_mesh"):
        settings.use_dynamic_mesh = False
    if not ENABLE_HEM_DRAG:
        return None, f"disabled; cleared {cleared_fields} old fields"
    if not hasattr(settings, "use_dynamic_mesh"):
        return None, "Blender Cloth Dynamic Mesh is unavailable"

    source_weights_by_group = {
        group_name: source_group_vertex_weights(obj, group_name)
        for group_name in HEM_DRAG_GROUP_NAMES
    }
    missing_groups = [
        group_name
        for group_name, weights in source_weights_by_group.items()
        if not weights
    ]
    if missing_groups:
        return None, (
            "requires both HEM groups; missing or empty "
            + " / ".join(missing_groups)
        )

    indices_by_group = {
        group_name: {vertex_index for vertex_index, _weight in weights}
        for group_name, weights in source_weights_by_group.items()
    }
    overlap = indices_by_group[FRONT_DRAG_GROUP_NAME].intersection(
        indices_by_group[REAR_DRAG_GROUP_NAME]
    )
    if overlap:
        raise RuntimeError(
            f"HEM_FRONT / HEM_REAR overlap on {len(overlap)} vertices; "
            "the drag groups must be disjoint."
        )

    frames = staged_frames()
    drag_start = float(frames["hem_drag_start"])
    drag_end = float(frames["hem_drag_end"])
    if drag_end <= drag_start:
        raise RuntimeError("HEM drag requires a positive frame range")

    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    key_blocks = obj.data.shape_keys.key_blocks
    basis = key_blocks[0]
    target = key_blocks.get(REAR_DRAG_SHAPE_KEY_NAME)
    if target is None:
        target = obj.shape_key_add(
            name=REAR_DRAG_SHAPE_KEY_NAME,
            from_mix=False,
        )

    # No previously generated trajectory may influence the natural pre-roll.
    generated_trajectory_keys = [
        shape_key
        for shape_key in key_blocks
        if shape_key.name == HEM_CAPTURE_SHAPE_KEY_NAME
        or shape_key.name.startswith(HEM_TRAJECTORY_SHAPE_KEY_PREFIX)
    ]
    for shape_key in generated_trajectory_keys + [target]:
        shape_key.driver_remove("value")
        shape_key.value = 0.0
        shape_key.slider_min = 0.0
        shape_key.slider_max = 1.0

    all_hem_indices = set().union(*indices_by_group.values())
    trajectory = _capture_cloth_world_trajectory_v24(
        obj,
        modifier,
        all_hem_indices,
        drag_start,
    )
    captured_points = trajectory[int(drag_start)]

    group_average_z = {}
    for group_name, weights in source_weights_by_group.items():
        total_weight = sum(weight for _vertex_index, weight in weights)
        group_average_z[group_name] = sum(
            captured_points[vertex_index].z * weight
            for vertex_index, weight in weights
        ) / total_weight

    common_target_z = (
        min(group_average_z.values()) - REAR_DRAG_DISTANCE_MM / 1000.0
    )
    group_down_mm = {
        group_name: (average_z - common_target_z) * 1000.0
        for group_name, average_z in group_average_z.items()
    }
    excessive = {
        group_name: distance_mm
        for group_name, distance_mm in group_down_mm.items()
        if distance_mm > MAX_SAFE_REAR_DRAG_DISTANCE_MM
    }
    if excessive:
        details = ", ".join(
            f"{name}={distance_mm:.1f} mm"
            for name, distance_mm in excessive.items()
        )
        raise RuntimeError(
            f"HEM equal-height drag exceeds the safe limit: {details}; "
            f"maximum is {MAX_SAFE_REAR_DRAG_DISTANCE_MM:g} mm."
        )

    inverse_world = obj.matrix_world.inverted_safe()
    trajectory_keys = []
    for trajectory_frame, frame_points in trajectory.items():
        shape_key_name = (
            HEM_CAPTURE_SHAPE_KEY_NAME
            if trajectory_frame == int(drag_start)
            else f"{HEM_TRAJECTORY_SHAPE_KEY_PREFIX}{trajectory_frame:03d}"
        )
        shape_key = key_blocks.get(shape_key_name)
        if shape_key is None:
            shape_key = obj.shape_key_add(
                name=shape_key_name,
                from_mix=False,
            )
        shape_key.driver_remove("value")
        shape_key.value = 0.0
        shape_key.slider_min = 0.0
        shape_key.slider_max = 1.0
        for vertex_index in range(len(obj.data.vertices)):
            shape_key.data[vertex_index].co = basis.data[vertex_index].co
        for vertex_index, world_point in frame_points.items():
            shape_key.data[vertex_index].co = inverse_world @ world_point

        driver = shape_key.driver_add("value").driver
        driver.type = "SCRIPTED"
        if trajectory_frame == int(drag_start):
            driver.expression = (
                f"max(0.0,min(1.0,frame-{drag_start - 1:g}))"
            )
        else:
            driver.expression = (
                f"max(0.0,1.0-abs(frame-{trajectory_frame:g}))"
            )
        trajectory_keys.append(shape_key)

    for vertex_index in range(len(obj.data.vertices)):
        target.data[vertex_index].co = basis.data[vertex_index].co

    # The trajectory keys reproduce the unforced HEM motion through frame 18.
    # This additive target then changes only Z while the fixed pin transfers the
    # grab into the Cloth solve.
    for group_name, weights in source_weights_by_group.items():
        delta_z = common_target_z - group_average_z[group_name]
        for vertex_index, _weight in weights:
            world_delta_target = obj.matrix_world @ basis.data[vertex_index].co
            world_delta_target.z += delta_z
            target.data[vertex_index].co = inverse_world @ world_delta_target

    target.driver_remove("value")
    target.value = 0.0
    target.slider_min = 0.0
    target.slider_max = 1.0
    target_driver = target.driver_add("value").driver
    target_driver.type = "SCRIPTED"
    target_driver.expression = (
        f"max(0.0,min(1.0,(frame-{drag_start:g})/"
        f"{drag_end - drag_start:g}))"
    )

    source_weights = [
        (vertex_index, weight * REAR_DRAG_VERTEX_WEIGHT)
        for group_name in HEM_DRAG_GROUP_NAMES
        for vertex_index, weight in source_weights_by_group[group_name]
    ]
    pin_group = replace_weight_group(
        obj,
        REAR_DRAG_PIN_GROUP_NAME,
        source_weights,
    )
    for modifier_name in (
        ROOF_PIN_RELEASE_MIX_MODIFIER_NAME,
        REAR_DRAG_MIX_MODIFIER_NAME,
    ):
        weight_modifier = obj.modifiers.get(modifier_name)
        if weight_modifier is not None:
            obj.modifiers.remove(weight_modifier)

    settings.driver_remove("pin_stiffness")
    settings.vertex_group_mass = pin_group.name
    settings.pin_stiffness = REAR_DRAG_PIN_STIFFNESS
    settings.use_dynamic_mesh = True

    obj["car_cover_hem_drag_schedule"] = True
    obj["car_cover_rear_drag_pin_group"] = pin_group.name
    obj["cloth_hem_drag_groups"] = ",".join(HEM_DRAG_GROUP_NAMES)
    obj["cloth_hem_capture_shape_key"] = HEM_CAPTURE_SHAPE_KEY_NAME
    obj["cloth_hem_trajectory_shape_keys"] = ",".join(
        shape_key.name for shape_key in trajectory_keys
    )
    obj["cloth_hem_drag_shape_key"] = target.name
    obj["cloth_hem_drag_capture_frame"] = drag_start
    obj["cloth_hem_drag_target_z_world"] = common_target_z
    obj["cloth_hem_drag_target_difference_mm"] = 0.0
    obj["cloth_hem_drag_tolerance_mm"] = HEM_EQUAL_HEIGHT_TOLERANCE_MM
    obj["cloth_hem_drag_start_frame"] = drag_start
    obj["cloth_hem_drag_end_frame"] = drag_end
    for group_name, average_z in group_average_z.items():
        obj[f"cloth_{group_name}_captured_average_z_world"] = average_z
        obj[f"cloth_{group_name}_dynamic_down_mm"] = group_down_mm[group_name]
    obj["cloth_roof_pin_status"] = (
        "used only for natural HEM trajectory pre-roll; final solve uses "
        f"fixed {REAR_DRAG_PIN_GROUP_NAME}"
    )

    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    bpy.context.view_layer.update()
    distances = ", ".join(
        f"{name}={distance_mm:.1f} mm"
        for name, distance_mm in group_down_mm.items()
    )
    cleared_note = (
        f", cleared {cleared_fields} old fields" if cleared_fields else ""
    )
    return target, (
        f"frame-{drag_start:g} HEM grab -> frame {drag_end:g}; {distances}; "
        f"common target Z={common_target_z:.4f} m; captured XY retained; "
        f"fixed HEM Pin follows {len(trajectory_keys)} sampled frames; "
        f"force fields OFF{cleared_note}"
    )


def remove_v24_hem_grab_artifacts(obj):
    """Remove expensive trajectory keys and cached-pin helpers from V24."""

    removed_shape_keys = 0
    shape_keys = getattr(obj.data, "shape_keys", None)
    if shape_keys is not None:
        stale_keys = [
            shape_key
            for shape_key in shape_keys.key_blocks
            if shape_key.name == HEM_CAPTURE_SHAPE_KEY_NAME
            or shape_key.name.startswith(HEM_TRAJECTORY_SHAPE_KEY_PREFIX)
        ]
        for shape_key in stale_keys:
            shape_key.driver_remove("value")
            obj.shape_key_remove(shape_key)
            removed_shape_keys += 1

    removed_modifiers = 0
    for modifier_name in (
        ROOF_PIN_RELEASE_MIX_MODIFIER_NAME,
        REAR_DRAG_MIX_MODIFIER_NAME,
    ):
        generated_modifier = obj.modifiers.get(modifier_name)
        if generated_modifier is not None:
            obj.modifiers.remove(generated_modifier)
            removed_modifiers += 1

    for group_name in (
        REAR_DRAG_PIN_GROUP_NAME,
        REAR_DRAG_WEIGHT_GROUP_NAME,
    ):
        group = obj.vertex_groups.get(group_name)
        if group is not None:
            obj.vertex_groups.remove(group)

    for property_name in (
        "cloth_hem_capture_shape_key",
        "cloth_hem_trajectory_shape_keys",
        "cloth_hem_drag_capture_frame",
        "cloth_hem_drag_target_z_world",
        "cloth_hem_drag_target_difference_mm",
        "cloth_hem_drag_tolerance_mm",
        "car_cover_rear_drag_pin_group",
    ):
        if property_name in obj:
            del obj[property_name]
    return removed_shape_keys, removed_modifiers


def hem_front_extra_mm(previous_mm, difference_mm):
    """Bounded correction with a dead band; release extra pull on overshoot."""
    tolerance = HEM_EQUAL_HEIGHT_TOLERANCE_MM
    error = max(0.0, difference_mm - tolerance) + min(
        0.0, difference_mm + tolerance
    )
    return max(0.0, min(MAX_HEM_FRONT_EXTRA_MM,
                        previous_mm + HEM_HEIGHT_FEEDBACK_GAIN * error))


def measure_settled_hem_difference(obj):
    """Read semantic groups on evaluated geometry, including downstream Weld.

    Use median world Z so a single caught corner does not drive the whole hem.
    Never map base vertex indices onto the welded/subdivided output.
    """
    scene = bpy.context.scene
    if not ENABLE_HEM_HEIGHT_FEEDBACK or not ENABLE_HEM_DRAG:
        return None
    cloth = next((m for m in obj.modifiers if m.type == "CLOTH"), None)
    if cloth is None or scene.frame_current < scene.frame_start + HEM_DRAG_SETTLE_END:
        print(f"  [CC HEM] {obj.name}: run again on the settled final frame "
              "to measure front/rear height; keeping previous correction")
        return None
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    heights = []
    for name in HEM_DRAG_GROUP_NAMES:
        points = vertex_group_world_points(evaluated, name)
        if not points:
            print(f"  [CC HEM] {obj.name}: cannot measure {name}; keeping correction")
            return None
        values = sorted(point.z for point in points)
        middle = len(values) // 2
        heights.append((values[middle] + values[(len(values) - 1) // 2]) * 0.5)
    difference = (heights[0] - heights[1]) * 1000.0
    obj["cloth_hem_measured_difference_mm"] = difference
    obj["cloth_hem_measurement_frame"] = scene.frame_current
    print(f"  [CC HEM] {obj.name}: front/rear median Z="
          f"{heights[0]:.4f}/{heights[1]:.4f} m, gap={difference:.1f} mm")
    return difference


def configure_hem_dynamic_drag(obj, modifier, measured_difference_mm=None):
    """Apply equal HEM tension, then a collision-safe front/rear level trim."""

    cleared_fields = clear_legacy_rear_pull_fields(obj)
    cleared_fields += clear_hem_down_fields(obj)
    disable_rear_drag(obj, modifier)
    removed_keys, removed_modifiers = remove_v24_hem_grab_artifacts(obj)

    settings = modifier.settings
    if hasattr(settings, "use_dynamic_mesh"):
        settings.use_dynamic_mesh = False
    if not ENABLE_HEM_DRAG:
        return None, f"disabled; cleared {cleared_fields} old fields"
    if not hasattr(settings, "use_dynamic_mesh"):
        return None, "Blender Cloth Dynamic Mesh is unavailable"
    tension_by_group = {
        FRONT_DRAG_GROUP_NAME: HEM_FRONT_TENSION_DISTANCE_MM,
        REAR_DRAG_GROUP_NAME: HEM_REAR_TENSION_DISTANCE_MM,
    }
    invalid_tension = [
        f"{group_name}={distance_mm:g}"
        for group_name, distance_mm in tension_by_group.items()
        if not 0.0 <= distance_mm <= MAX_SAFE_HEM_TENSION_DISTANCE_MM
    ]
    if invalid_tension:
        raise RuntimeError(
            "HEM tension must stay between 0 and "
            f"{MAX_SAFE_HEM_TENSION_DISTANCE_MM:g} mm; invalid "
            + ", ".join(invalid_tension)
        )
    if HEM_FRONT_TENSION_DISTANCE_MM <= HEM_REAR_TENSION_DISTANCE_MM:
        raise RuntimeError(
            "HEM leveling requires more front tension than rear tension"
        )
    expected_front = HEM_TENSION_DISTANCE_MM + HEM_LEVELING_BIAS_MM
    expected_rear = HEM_TENSION_DISTANCE_MM - HEM_LEVELING_BIAS_MM
    if (
        abs(HEM_FRONT_TENSION_DISTANCE_MM - expected_front) > 1.0e-6
        or abs(HEM_REAR_TENSION_DISTANCE_MM - expected_rear) > 1.0e-6
    ):
        raise RuntimeError(
            "Front/rear HEM totals must equal base tension +/- leveling bias"
        )

    source_weights_by_group = {
        group_name: source_group_vertex_weights(obj, group_name)
        for group_name in HEM_DRAG_GROUP_NAMES
    }
    missing_groups = [
        group_name
        for group_name, weights in source_weights_by_group.items()
        if not weights
    ]
    if missing_groups:
        return None, (
            "requires both HEM groups; missing or empty "
            + " / ".join(missing_groups)
        )
    group_indices = {
        group_name: {vertex_index for vertex_index, _weight in weights}
        for group_name, weights in source_weights_by_group.items()
    }
    overlap = group_indices[FRONT_DRAG_GROUP_NAME].intersection(
        group_indices[REAR_DRAG_GROUP_NAME]
    )
    if overlap:
        raise RuntimeError(
            f"HEM_FRONT / HEM_REAR overlap on {len(overlap)} vertices; "
            "leveling directions would be ambiguous"
        )

    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    key_blocks = obj.data.shape_keys.key_blocks
    basis = key_blocks[0]
    base_target = key_blocks.get(REAR_DRAG_SHAPE_KEY_NAME)
    if base_target is None:
        base_target = obj.shape_key_add(
            name=REAR_DRAG_SHAPE_KEY_NAME,
            from_mix=False,
        )
    level_target = key_blocks.get(HEM_LEVEL_SHAPE_KEY_NAME)
    if level_target is None:
        level_target = obj.shape_key_add(
            name=HEM_LEVEL_SHAPE_KEY_NAME,
            from_mix=False,
        )

    for shape_key in (base_target, level_target):
        shape_key.driver_remove("value")
        shape_key.value = 0.0
        shape_key.slider_min = 0.0
        shape_key.slider_max = 1.0
        for vertex_index in range(len(obj.data.vertices)):
            shape_key.data[vertex_index].co = basis.data[vertex_index].co

    inverse_world = obj.matrix_world.inverted_safe()
    for group_name, weights in source_weights_by_group.items():
        level_direction = (
            -1.0 if group_name == FRONT_DRAG_GROUP_NAME else 1.0
        )
        for vertex_index, weight in weights:
            basis_world = obj.matrix_world @ basis.data[vertex_index].co

            base_world = basis_world.copy()
            base_world.z -= (
                HEM_TENSION_DISTANCE_MM * weight / 1000.0
            )
            base_target.data[vertex_index].co = inverse_world @ base_world

            level_world = basis_world.copy()
            level_world.z += (
                level_direction * HEM_LEVELING_BIAS_MM * weight / 1000.0
            )
            level_target.data[vertex_index].co = inverse_world @ level_world

    frames = staged_frames()
    drag_start = float(frames["hem_drag_start"])
    drag_end = float(frames["hem_drag_end"])
    level_start = float(frames["hem_level_start"])
    level_end = float(frames["hem_level_end"])
    if drag_end <= drag_start:
        raise RuntimeError("HEM tension requires a positive frame range")
    if not drag_start < level_start < level_end:
        raise RuntimeError("HEM leveling requires a positive late frame range")
    if level_end > frames["hem_drag_settle_end"]:
        raise RuntimeError("HEM leveling must finish before the settle frame")
    progress = (
        f"max(0.0,min(1.0,(frame-{drag_start:g})/"
        f"{drag_end - drag_start:g}))"
    )
    driver = base_target.driver_add("value").driver
    driver.type = "SCRIPTED"
    driver.expression = (
        f"({progress})*({progress})*(3.0-2.0*({progress}))"
    )
    level_progress = (
        f"max(0.0,min(1.0,(frame-{level_start:g})/"
        f"{level_end - level_start:g}))"
    )
    driver = level_target.driver_add("value").driver
    driver.type = "SCRIPTED"
    driver.expression = (
        f"({level_progress})*({level_progress})*"
        f"(3.0-2.0*({level_progress}))"
    )

    # Freeze measured feedback into a deterministic driver schedule. No live
    # handler mutates the rest mesh while Cloth is evaluating or reading cache.
    extra_mm = float(obj.get("cloth_hem_front_extra_mm", 0.0))
    if not ENABLE_HEM_HEIGHT_FEEDBACK:
        extra_mm = 0.0
    elif measured_difference_mm is not None:
        extra_mm = hem_front_extra_mm(extra_mm, measured_difference_mm)
    extra_mm = max(0.0, min(MAX_HEM_FRONT_EXTRA_MM, extra_mm))
    correction = key_blocks.get(HEM_FEEDBACK_SHAPE_KEY_NAME)
    if correction is None:
        correction = obj.shape_key_add(name=HEM_FEEDBACK_SHAPE_KEY_NAME, from_mix=False)
    correction.driver_remove("value")
    correction.relative_key = basis
    correction.value = 0.0
    for vertex_index in range(len(obj.data.vertices)):
        correction.data[vertex_index].co = basis.data[vertex_index].co
    for vertex_index, weight in source_weights_by_group[FRONT_DRAG_GROUP_NAME]:
        point = obj.matrix_world @ basis.data[vertex_index].co
        point.z -= extra_mm * weight / 1000.0
        correction.data[vertex_index].co = inverse_world @ point
    correction_driver = correction.driver_add("value").driver
    correction_driver.type = "SCRIPTED"
    correction_driver.expression = driver.expression
    obj["cloth_hem_front_extra_mm"] = extra_mm
    print(f"  [CC HEM] {obj.name}: additional front rest-tension={extra_mm:.1f} mm "
          f"(limit {MAX_HEM_FRONT_EXTRA_MM:g} mm); replay from Scene Start")

    settings.use_dynamic_mesh = True
    obj["car_cover_hem_drag_schedule"] = True
    obj["cloth_hem_drag_groups"] = ",".join(HEM_DRAG_GROUP_NAMES)
    obj["cloth_hem_drag_shape_key"] = base_target.name
    obj["cloth_hem_level_shape_key"] = level_target.name
    obj["cloth_hem_tension_distance_mm"] = HEM_TENSION_DISTANCE_MM
    obj["cloth_hem_leveling_bias_mm"] = HEM_LEVELING_BIAS_MM
    obj["cloth_hem_front_tension_distance_mm"] = (
        HEM_FRONT_TENSION_DISTANCE_MM
    )
    obj["cloth_hem_rear_tension_distance_mm"] = (
        HEM_REAR_TENSION_DISTANCE_MM
    )
    obj["cloth_hem_leveling_differential_mm"] = (
        HEM_FRONT_TENSION_DISTANCE_MM - HEM_REAR_TENSION_DISTANCE_MM
    )
    obj["cloth_hem_drag_start_frame"] = drag_start
    obj["cloth_hem_drag_end_frame"] = drag_end
    obj["cloth_hem_level_start_frame"] = level_start
    obj["cloth_hem_level_end_frame"] = level_end

    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    bpy.context.view_layer.update()
    cleanup_notes = []
    if cleared_fields:
        cleanup_notes.append(f"cleared {cleared_fields} fields")
    if removed_keys:
        cleanup_notes.append(f"removed {removed_keys} V24 trajectory keys")
    if removed_modifiers:
        cleanup_notes.append(
            f"removed {removed_modifiers} V24 weight modifiers"
        )
    cleanup_note = (
        f"; {', '.join(cleanup_notes)}" if cleanup_notes else ""
    )
    group_counts = ", ".join(
        f"{group_name}={len(weights)}"
        for group_name, weights in source_weights_by_group.items()
    )
    return base_target, (
        f"base Z tension {drag_start:g}->{drag_end:g}, "
        f"down {HEM_TENSION_DISTANCE_MM:g} mm; level trim "
        f"{level_start:g}->{level_end:g}; final front/rear "
        f"{HEM_FRONT_TENSION_DISTANCE_MM:g}/"
        f"{HEM_REAR_TENSION_DISTANCE_MM:g} mm ({group_counts}); "
        f"HEM Pin OFF; collision/slide remain active; force fields OFF"
        f"{cleanup_note}"
    )


def apply_preset(obj, measured_difference_mm=None):
    """Apply the embedded preset to one mesh object."""

    proxy_reason = collision_proxy_reason(obj)
    if proxy_reason is not None:
        raise RuntimeError(
            f"Refusing to apply Cloth to collision proxy '{obj.name}': "
            f"{proxy_reason}"
        )

    # Validate connector topology before creating or changing physics. Raising
    # here leaves a bad mesh untouched and prevents a stronger sewing force
    # from amplifying a many-to-one "black hole" connection.
    report_sewing_preflight(obj)

    modifier = get_or_create_cloth_modifier(obj)
    settings = modifier.settings
    collision = modifier.collision_settings
    point_cache = getattr(modifier, "point_cache", None)
    was_baked = bool(getattr(point_cache, "is_baked", False))

    if point_cache is not None and not was_baked:
        point_cache.frame_start = bpy.context.scene.frame_start
        point_cache.frame_end = (
            bpy.context.scene.frame_start + SIMULATION_END_OFFSET
        )

    # General simulation
    settings.quality = QUALITY_STEPS
    settings.time_scale = TIME_SCALE
    settings.mass = MASS_PER_VERTEX
    settings.air_damping = AIR_DAMPING

    # Keep in-plane stiffness while reducing bending resistance and damping.
    # Mass is retained for comparison; this is not a calibrated fabric model.
    settings.tension_stiffness = TENSION_STIFFNESS
    settings.compression_stiffness = COMPRESSION_STIFFNESS
    settings.shear_stiffness = SHEAR_STIFFNESS
    settings.bending_stiffness = BENDING_STIFFNESS
    settings.bending_model = BENDING_MODEL

    settings.tension_damping = TENSION_DAMPING
    settings.compression_damping = COMPRESSION_DAMPING
    settings.shear_damping = SHEAR_DAMPING
    settings.bending_damping = BENDING_DAMPING

    # The cover has an open hem, so closed-volume Cloth Pressure can leak and
    # propel the mesh. V7 keeps pressure disabled and uses bounded temporary
    # radial fields for open-cover expansion instead.
    if hasattr(settings, "use_pressure"):
        settings.use_pressure = False

    # Sewing
    settings.use_sewing_springs = ENABLE_SEWING
    # sewing_force_max is a force cap, not a breaking threshold. Ramping the
    # cap prevents an initial snap while the Sewing Springs remain connected.
    settings.sewing_force_max = MAX_SEWING_FORCE
    sewing_status = configure_sewing_force_driver(obj, modifier)
    obj["cloth_sewing_status"] = sewing_status
    obj["cloth_bending_status"] = configure_bending_stiffness_driver(
        obj,
        modifier,
    )
    obj["cloth_gravity_status"] = configure_gravity_driver(modifier)

    # A small temporary center anchor keeps the TOP panel over the collider
    # while symmetric left/right sewing springs close. It is fully released
    # before the final settle so it cannot falsify the fitted cover shape.
    pin_group, pin_indices, pin_group_status = ensure_roof_pin_group(obj)
    has_pin_reference = bool(pin_indices)
    roof_pin_status = configure_roof_pin_driver(
        obj,
        modifier,
        pin_group,
        pin_indices,
    )
    obj["cloth_roof_pin_group_status"] = pin_group_status
    obj["cloth_roof_pin_status"] = roof_pin_status

    # Cloth-to-vehicle collision
    collision.driver_remove("use_collision")
    collision.use_collision = ENABLE_OBJECT_COLLISION
    collision.collision_quality = COLLISION_QUALITY
    collision.distance_min = OBJECT_COLLISION_DISTANCE_MM / 1000.0
    collision.friction = OBJECT_COLLISION_FRICTION
    collision_collection, colliders, collision_scope = resolve_collision_scope()
    collision.collection = collision_collection
    for collider in colliders:
        collider.collision.cloth_friction = COLLIDER_SURFACE_FRICTION
    obj["cloth_collision_collection"] = (
        collision.collection.name if collision.collection is not None else "SCENE"
    )
    obj["cloth_collision_scope"] = collision_scope
    obj["cloth_collision_objects"] = ", ".join(
        collider.name for collider in colliders
    )
    obj["cloth_collider_surface_friction"] = COLLIDER_SURFACE_FRICTION

    # Cloth-to-cloth collision
    collision.self_distance_min = SELF_COLLISION_DISTANCE_MM / 1000.0
    collision.self_friction = SELF_COLLISION_FRICTION
    obj["cloth_self_collision_status"] = configure_self_collision_driver(
        obj,
        modifier,
    )

    # V21 is deliberately isolated from every scene Force/Wind effector, not
    # only the generated objects. This prevents untagged or stale fields from
    # continuing to influence the cloth after cleanup.
    effector_weights = getattr(settings, "effector_weights", None)
    if effector_weights is not None:
        effector_weights.force = 1.0 if ENABLE_STAGED_EXPANSION else 0.0
        if hasattr(effector_weights, "wind"):
            effector_weights.wind = 1.0 if ENABLE_TOP_DOWN_GUIDE else 0.0

    # This changes only display normals, not simulation geometry or Fit data.
    if SHADE_SMOOTH:
        for polygon in obj.data.polygons:
            polygon.use_smooth = True

    # Display-only seam line derived from semantic seam vertex groups. Apply
    # it before the downstream Weld/Subsurf setup; it remains a mesh attribute
    # and never changes modifier topology or Cloth input.
    obj["cloth_seam_texture_status"] = configure_seam_texture(obj)

    weld_status = configure_post_cloth_seam_weld(obj, modifier)
    obj["cloth_post_seam_weld_status"] = weld_status

    if ENABLE_DISPLAY_SUBSURF:
        get_or_create_display_subsurf(obj)

    # Store enough metadata in the .blend file to identify the exact preset.
    obj["cloth_preset"] = PRESET_NAME
    obj["cloth_material_preset"] = MATERIAL_PRESET_NAME
    obj["cloth_preset_embedded"] = True
    obj["cloth_mesh_edge_target_mm"] = MESH_EDGE_TARGET_MM
    obj["cloth_mass"] = MASS_PER_VERTEX
    obj["cloth_tension"] = TENSION_STIFFNESS
    obj["cloth_compression"] = COMPRESSION_STIFFNESS
    obj["cloth_shear"] = SHEAR_STIFFNESS
    obj["cloth_bending"] = BENDING_STIFFNESS
    obj["cloth_sewing_force"] = MAX_SEWING_FORCE
    obj["cloth_shade_smooth"] = SHADE_SMOOTH
    obj["cloth_pin_vertex_weight"] = (
        PIN_VERTEX_WEIGHT if ENABLE_ROOF_PIN_DURING_SIMULATION else 0.0
    )

    top_down_object, top_down_status = configure_top_down_guide(obj)

    expansion_objects, expansion_status = configure_expansion_fields(
        obj,
        has_pin_reference,
    )

    rear_drag_target, rear_drag_status = configure_hem_dynamic_drag(
        obj, modifier, measured_difference_mm
    )

    configure_hem_level_feedback(obj, modifier)

    # Replace handlers left by V19 even when every generated field is disabled.
    ensure_force_stage_handler()
    car_cover_force_stage_handler(bpy.context.scene)

    return (
        was_baked,
        has_pin_reference,
        top_down_object,
        top_down_status,
        expansion_objects,
        expansion_status,
        rear_drag_target,
        rear_drag_status,
    )



# Late-stage soft pin spring targets. All semantic HEM vertices share a plane.
ENABLE_HEM_LEVEL_FEEDBACK = True
HEM_FEEDBACK_START = 44
HEM_FEEDBACK_RAMP = 20
HEM_FEEDBACK_TARGET_Z = None  # Metres; None captures the global HEM mean once.
HEM_FEEDBACK_LIMIT_MM = 350.0
HEM_LIVE_KEY = "CC_HEM_LIVE_LEVEL"
HEM_LEVEL_PIN_WEIGHT = 0.8



def hem_level_target_z(height, target, frame, start, end):
    """Smoothly move each sampled HEM height to the same world-Z plane."""
    t = max(0.0, min(1.0, (frame - start) / (end - start)))
    return height + (target - height) * t * t * (3 - 2 * t)


def configure_hem_level_feedback(obj, cloth):
    """Drive soft pin springs from a sampled free trajectory to a level hem.

    Target X/Y follows the free solve rather than the flat cutting pattern.
    Fixed key data and frame drivers keep the Cloth point cache deterministic.
    """
    keys = obj.data.shape_keys
    if keys:
        for old in list(keys.key_blocks):
            if old.name.startswith(HEM_LIVE_KEY):
                old.driver_remove("value")
                obj.shape_key_remove(old)
    if not ENABLE_HEM_LEVEL_FEEDBACK:
        return
    if cloth.point_cache.is_baked:
        raise RuntimeError("Free the Cloth bake before setting up HEM leveling")
    groups = {g.index for g in obj.vertex_groups
              if g.name == "HEM" or g.name.startswith("HEM_")}
    indices = {v.index for v in obj.data.vertices
               if any(g.group in groups and g.weight > 0 for g in v.groups)}
    if not indices:
        print(f"[CC HEM] {obj.name}: no HEM vertices; leveling skipped")
        return
    scene = bpy.context.scene
    start = scene.frame_start + HEM_FEEDBACK_START
    end = start + HEM_FEEDBACK_RAMP
    cloth.settings.use_dynamic_mesh = False
    trajectory = _capture_cloth_world_trajectory_v24(
        obj, cloth, indices, scene.frame_start + SIMULATION_END_OFFSET)
    points = trajectory[start]
    target = HEM_FEEDBACK_TARGET_Z
    if target is None:
        target = sum(p.z for p in points.values()) / len(points)
    maximum = max(abs(p.z - target) for p in points.values()) * 1000
    if maximum > HEM_FEEDBACK_LIMIT_MM:
        raise RuntimeError(f"HEM leveling requires {maximum:.1f} mm; "
                           f"limit is {HEM_FEEDBACK_LIMIT_MM:g} mm. Adjust target or drape first.")
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    basis = obj.data.shape_keys.key_blocks[0]
    inverse = obj.matrix_world.inverted()
    for frame, frame_points in trajectory.items():
        key = obj.shape_key_add(name=f"{HEM_LIVE_KEY}_{frame:04d}", from_mix=False)
        for vertex in obj.data.vertices:
            key.data[vertex.index].co = basis.data[vertex.index].co
        for index, world in frame_points.items():
            point = world.copy()
            point.z = hem_level_target_z(point.z, target, frame, start, end)
            key.data[index].co = inverse @ point
        driver = key.driver_add("value").driver
        driver.type = "SCRIPTED"
        if frame == scene.frame_start + SIMULATION_END_OFFSET:
            driver.expression = f"max(0.0,min(1.0,frame-{frame-1}))"
        else:
            driver.expression = f"max(0.0,1.0-abs(frame-{frame}))"
    roof_weights = source_group_vertex_weights(obj, PIN_GROUP_NAME)
    pin, drag = rebuild_rear_drag_pin_groups(obj, [(i, HEM_LEVEL_PIN_WEIGHT) for i in indices], roof_weights)
    release = get_or_create_roof_pin_release_modifier(obj, cloth)
    acquire = get_or_create_rear_drag_weight_modifier(obj, cloth)
    acquire.driver_remove("mask_constant")
    driver = acquire.driver_add("mask_constant").driver
    driver.type = "SCRIPTED"
    driver.expression = f"max(0.0,min(1.0,(frame-{start})/{HEM_FEEDBACK_RAMP}))"
    order_dynamic_pin_modifiers(obj, release, acquire, cloth)
    cloth.settings.driver_remove("pin_stiffness")
    cloth.settings.vertex_group_mass = pin.name
    cloth.settings.pin_stiffness = 1.0
    obj["cloth_hem_target_z_world"] = target
    obj["cloth_hem_sample_spread_mm"] = (max(p.z for p in points.values()) -
                                         min(p.z for p in points.values())) * 1000
    obj["cloth_hem_level_vertex_count"] = len(indices)
    obj["cloth_roof_pin_status"] = "early roof hold/release; late HEM soft pin springs"
    scene.frame_set(scene.frame_start)
    bpy.context.view_layer.update()
    print(f"[CC HEM] {obj.name}: {len(indices)} vertices, common target Z={target:.4f}, "
          f"soft pin spring ramp {start}-{end}; replay from Scene Start")


def main():
    if bpy.context.mode != "OBJECT":
        raise RuntimeError("请先切换到 Object Mode，再运行脚本。")

    objects, rejected = selected_cloth_meshes()
    for obj, reason in rejected:
        print(f"[CC CLOTH] skipped collider {obj.name}: {reason}")

    if not objects:
        rejected_names = ", ".join(obj.name for obj, _reason in rejected)
        detail = (
            f" 当前选中的 Mesh（{rejected_names}）是碰撞体。"
            if rejected_names
            else ""
        )
        raise RuntimeError(
            "请只选择实际车衣 Mesh，再运行布料脚本。"
            f"{detail} 碰撞体由 Collision 修改器识别，不再依赖集合名称；"
            "如果碰撞代理上已误加 Cloth，请先删除该 Cloth 修改器。"
        )

    # Capture every selected object before setup resets the frame/cache of any.
    hem_measurements = {obj.name: measure_settled_hem_difference(obj) for obj in objects}

    required_end = bpy.context.scene.frame_start + SIMULATION_END_OFFSET
    bpy.context.scene.frame_end = required_end

    baked_objects = []

    print("")
    print("=" * 64)
    print(f"APPLY EMBEDDED PRESET: {PRESET_NAME}")
    print("=" * 64)
    _collection, _colliders, scope = resolve_collision_scope()
    names = ", ".join(obj.name for obj in _colliders) or "none"
    print(f"Collision scope: {scope} ({names})")
    if ENABLE_OBJECT_COLLISION and not _colliders:
        print(
            "  [CC COLLISION WARNING] 当前场景没有带 Collision 修改器的 "
            "Mesh；车体碰撞不会生效。"
        )

    for obj in objects:
        (
            was_baked,
            has_pin,
            top_down_object,
            top_down_status,
            expansion_objects,
            expansion_status,
            rear_drag_target,
            rear_drag_status,
        ) = apply_preset(obj, hem_measurements[obj.name])
        if was_baked:
            baked_objects.append(obj.name)

        print(
            f"{obj.name}: material={MATERIAL_PRESET_NAME}, "
            f"quality={QUALITY_STEPS}, mass={MASS_PER_VERTEX}, "
            f"bend={BENDING_STIFFNESS}, "
            f"sewing={SEWING_FORCE_START}->{MAX_SEWING_FORCE}, "
            f"bend={obj['cloth_bending_status']}, "
            f"post_weld={obj['cloth_post_seam_weld_status']}, "
            f"self_collision={obj['cloth_self_collision_status']}, "
            f"pin={obj['cloth_roof_pin_status']}, "
            f"seam_texture={obj['cloth_seam_texture_status']}, "
            f"collision={obj['cloth_collision_scope']}, "
            f"top_down={top_down_status}, expansion={expansion_status}, "
            f"hem_down={rear_drag_status}"
        )

        if top_down_object is None and ENABLE_TOP_DOWN_GUIDE:
            print(f"  [TOP Down skipped] {top_down_status}.")

        if not expansion_objects and ENABLE_STAGED_EXPANSION:
            print(
                f"  [Expansion skipped] {expansion_status}. "
                f"需要非空的 {PIN_GROUP_NAME}。"
            )

        if rear_drag_target is None and ENABLE_HEM_DRAG:
            print(
                f"  [Hem Drag skipped] {rear_drag_status}. "
                f"需要两个互不重叠的非空语义组 "
                f"{' / '.join(HEM_DRAG_GROUP_NAMES)}。"
            )

    print("=" * 64)
    print(f"完成：已应用到 {len(objects)} 个 Mesh 对象。")

    frames = staged_frames()
    print("")
    print("STAGED SIMULATION GUIDES:")
    if ENABLE_SEWING:
        print(
            f"  Sewing max force: {SEWING_FORCE_START:g} -> "
            f"{MAX_SEWING_FORCE:g} by {frames['sewing_ramp_end']} -> "
            f"sustain {SEWING_FORCE_SUSTAIN:g} at "
            f"{frames['sewing_release_end']}"
        )
        print(
            f"  Gravity: {SEWING_GRAVITY_FACTOR:g} through "
            f"{frames['gravity_ramp_start']} -> 1 at "
            f"{frames['gravity_ramp_end']}"
        )
        print(
            f"  TOP center pin: hold through {frames['roof_pin_hold_end']} -> "
            f"fully released at {frames['roof_pin_release_end']}"
        )
        print(
            f"  Object collision: ON from {frames['start']}; "
            f"self-collision: ON from {frames['self_collision_start']}"
        )
        print(
            f"  Post-Cloth seam weld: ON from "
            f"{frames['start'] + SEAM_WELD_ENABLE_OFFSET}"
        )
    if ENABLE_TOP_DOWN_GUIDE:
        print(
            f"  TOP down Wind: {frames['start']} -> "
            f"{frames['top_down_ramp_end']} -> {frames['top_down_hold_end']} -> "
            f"OFF {frames['top_down_release_end']}"
        )
    if ENABLE_STAGED_EXPANSION:
        print(
            f"  Expand: {frames['expand_ramp_start']} -> "
            f"{frames['expand_ramp_end']} -> {frames['expand_hold_end']} -> "
            f"SUSTAIN {EXPANSION_SUSTAIN_STRENGTH:g} from "
            f"{frames['expand_sustain_start']} -> RELEASE "
            f"{frames['expand_release_start']} -> OFF "
            f"{frames['expand_release_end']}; centers "
            f"{EXPANSION_FORCE_ABOVE_TOP_MM:g} mm above cloth top"
        )
    else:
        print("  Expansion fields: OFF (old CC_EXPAND_* fields cleared)")
    if ENABLE_HEM_DRAG:
        print(
            f"  HEM base rest-tension: OFF through "
            f"{frames['hem_drag_start']} -> smooth {HEM_TENSION_DISTANCE_MM:g} mm "
            f"Z shift at {frames['hem_drag_end']}; level trim "
            f"{frames['hem_level_start']}->{frames['hem_level_end']} -> final "
            f"front/rear {HEM_FRONT_TENSION_DISTANCE_MM:g}/"
            f"{HEM_REAR_TENSION_DISTANCE_MM:g} mm -> hold through "
            f"{frames['hem_drag_settle_end']}; HEM Pin OFF; force fields OFF; "
            f"collision slide ON"
        )
    else:
        print(
            "  HEM generated fields: OFF; HEM follows the same world gravity "
            "as the rest of the cloth"
        )
    if (
        ENABLE_HEM_DRAG
        and bpy.context.scene.frame_end < frames["hem_drag_settle_end"]
    ):
        print(
            f"  [Warning] Scene End={bpy.context.scene.frame_end}，"
            f"请至少设为 {frames['hem_drag_settle_end']}。"
        )

    if baked_objects:
        print("")
        print("[IMPORTANT] 以下对象存在已烘焙的 Cloth Cache：")
        for object_name in baked_objects:
            print(f"  - {object_name}")
        print(
            "请先执行 Physics > Cache > Delete Bake/Free Bake，再重新运行 V27，"
            "然后回到第 1 帧模拟。"
        )

    print("")
    print("V28: frames 45-65 ramp soft HEM pin springs to one world-Z plane; hold through 75.")
    print("Clear Cloth cache and replay sequentially from Scene Start. Rerun after geometry changes.")
    print("HEM targets use sampled per-vertex Z; collision and finishing modifiers stay active.")



if __name__ == "__main__":
    main()
