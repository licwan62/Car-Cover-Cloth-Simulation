"""Generate a smooth, cloth-safe vehicle Collision Proxy in Blender.

Standalone usage:
1. Switch to Object Mode.
2. Select one or more vehicle mesh objects. The active object supplies the
   automatic proxy name.
3. Run this file in Blender's Text Editor.

The script does not import project modules or read JSON. Source objects are
never modified. It evaluates their visible modifiers, seals at most one
detected rear wing, merges the evaluated topology, optionally voxel-remeshes
it, decimates it, and enables Collision physics.
"""

import bmesh
import bpy


# ============================================================
# EMBEDDED PRESET: CarCover_FastCollisionShell_V5
# Assumptions:
# - Z is world up.
# - 1 Blender Unit = 1 metre.
# - Explicitly selected meshes are the intended vehicle sources.
# ============================================================

PRESET_NAME = "CarCover_FastCollisionShell_V5"
PROXY_COLLECTION_NAME = "CC_COLLISION_PROXY"
PROXY_NAME_SUFFIX = " Collision"

VOXEL_SIZE_MM = 20.0
ENABLE_VOXEL_REMESH = False
REMOVE_DISCONNECTED_COMPONENTS = False
TARGET_FACE_RANGE = (8000, 24000)
TARGET_FACE_COUNT = 18000
MAX_FINAL_FACE_COUNT = 24000
ENABLE_PLANAR_DISSOLVE = True
PLANAR_DISSOLVE_ANGLE_DEG = 3.0

SMOOTH_METHOD = "LAPLACIAN"
SMOOTH_ITERATIONS = 0
SMOOTH_FACTOR = 0.12
SMOOTH_VOLUME_PRESERVE = True
PRESERVE_SOURCE_BOUNDS = True
MAX_BOUNDS_ERROR_MM = 1.0

# Thin, high, detached overhangs such as rear wings are dangerous cloth
# colliders. A falling cover can enter the gap below the part, become pinched,
# and then be pulled through its sharp trailing edge. Detect those voxel-mesh
# islands and add a downward support volume before the final remesh. The
# support stays inside the island's XY footprint, so it seals the snagging gap
# without increasing the vehicle's measured length or width.
ENABLE_THIN_OVERHANG_SUPPORT = True
THIN_OVERHANG_MAX_THICKNESS_MM = 350.0
THIN_OVERHANG_MIN_HORIZONTAL_SPAN_MM = 250.0
THIN_OVERHANG_MIN_HEIGHT_RATIO = 0.45
THIN_OVERHANG_SUPPORT_DROP_MM = 350.0
THIN_OVERHANG_MAX_LENGTH_RATIO = 0.22
THIN_OVERHANG_MIN_WIDTH_RATIO = 0.25
THIN_OVERHANG_MIN_END_RATIO = 0.55
THIN_OVERHANG_MIN_ASPECT_RATIO = 2.0
THIN_OVERHANG_NAME_HINTS = (
    "spoiler",
    "rear_wing",
    "rear wing",
    "tailwing",
    "尾翼",
)

# A full vehicle shell keeps supporting cloth along doors, wheel arches, and
# bumpers. Tapering the lower shell inward preserves a closed collider while
# giving the cover room to fall vertically after it leaves the shoulder line.
ENABLE_LOWER_BODY_INSET = False
LOWER_BODY_INSET_START_HEIGHT_RATIO = 0.55
LOWER_BODY_INSET_FULL_HEIGHT_RATIO = 0.20
LOWER_BODY_INSET_MM = 150.0

COLLISION_THICKNESS_MM = 7.0
COLLISION_FRICTION = 10.0
COLLISION_USE_CULLING = True
COLLISION_USE_NORMAL = True

EXCLUDE_CLOTH_OBJECTS = True
HIDE_PROXY_FROM_RENDER = True
PROXY_DISPLAY_TYPE = "WIRE"
SHOW_PROXY_IN_FRONT = True

GENERATED_TAG = "car_cover_generated_collision_proxy"
WORK_TAG = "car_cover_collision_proxy_work"
COLLISION_MODIFIER_NAME = "CC Cloth Collision"
REMESH_MODIFIER_NAME = "CC Voxel Remesh"
SMOOTH_MODIFIER_NAME = "CC Proxy Smooth"
DECIMATE_MODIFIER_NAME = "CC Proxy Decimate"


def configure_from_mapping(config):
    """Override embedded values from a project configuration mapping."""

    global PRESET_NAME
    global PROXY_COLLECTION_NAME
    global PROXY_NAME_SUFFIX
    global VOXEL_SIZE_MM
    global ENABLE_VOXEL_REMESH
    global REMOVE_DISCONNECTED_COMPONENTS
    global TARGET_FACE_RANGE
    global TARGET_FACE_COUNT
    global MAX_FINAL_FACE_COUNT
    global ENABLE_PLANAR_DISSOLVE
    global PLANAR_DISSOLVE_ANGLE_DEG
    global SMOOTH_METHOD
    global SMOOTH_ITERATIONS
    global SMOOTH_FACTOR
    global SMOOTH_VOLUME_PRESERVE
    global PRESERVE_SOURCE_BOUNDS
    global MAX_BOUNDS_ERROR_MM
    global ENABLE_THIN_OVERHANG_SUPPORT
    global THIN_OVERHANG_MAX_THICKNESS_MM
    global THIN_OVERHANG_MIN_HORIZONTAL_SPAN_MM
    global THIN_OVERHANG_MIN_HEIGHT_RATIO
    global THIN_OVERHANG_SUPPORT_DROP_MM
    global THIN_OVERHANG_MAX_LENGTH_RATIO
    global THIN_OVERHANG_MIN_WIDTH_RATIO
    global THIN_OVERHANG_MIN_END_RATIO
    global THIN_OVERHANG_MIN_ASPECT_RATIO
    global ENABLE_LOWER_BODY_INSET
    global LOWER_BODY_INSET_START_HEIGHT_RATIO
    global LOWER_BODY_INSET_FULL_HEIGHT_RATIO
    global LOWER_BODY_INSET_MM
    global COLLISION_THICKNESS_MM
    global COLLISION_FRICTION
    global COLLISION_USE_CULLING
    global COLLISION_USE_NORMAL

    PRESET_NAME = str(config.get("preset", PRESET_NAME))
    PROXY_COLLECTION_NAME = str(
        config.get("collection_name", PROXY_COLLECTION_NAME)
    )
    PROXY_NAME_SUFFIX = str(config.get("name_suffix", PROXY_NAME_SUFFIX))
    VOXEL_SIZE_MM = float(config.get("voxel_size_mm", VOXEL_SIZE_MM))
    ENABLE_VOXEL_REMESH = bool(
        config.get("use_voxel_remesh", ENABLE_VOXEL_REMESH)
    )
    REMOVE_DISCONNECTED_COMPONENTS = bool(
        config.get(
            "remove_disconnected_components",
            REMOVE_DISCONNECTED_COMPONENTS,
        )
    )

    target_faces = config.get("target_faces", TARGET_FACE_RANGE)
    if len(target_faces) != 2:
        raise ValueError("collision_proxy.target_faces must contain two values")
    TARGET_FACE_RANGE = (int(target_faces[0]), int(target_faces[1]))
    TARGET_FACE_COUNT = int(
        config.get("target_face_count", TARGET_FACE_COUNT)
    )
    MAX_FINAL_FACE_COUNT = int(
        config.get("max_final_face_count", MAX_FINAL_FACE_COUNT)
    )
    ENABLE_PLANAR_DISSOLVE = bool(
        config.get("planar_dissolve", ENABLE_PLANAR_DISSOLVE)
    )
    PLANAR_DISSOLVE_ANGLE_DEG = float(
        config.get("planar_angle_deg", PLANAR_DISSOLVE_ANGLE_DEG)
    )
    SMOOTH_METHOD = str(config.get("smooth_method", SMOOTH_METHOD)).upper()
    SMOOTH_ITERATIONS = int(
        config.get("smooth_iterations", SMOOTH_ITERATIONS)
    )
    SMOOTH_FACTOR = float(config.get("smooth_factor", SMOOTH_FACTOR))
    SMOOTH_VOLUME_PRESERVE = bool(
        config.get("smooth_volume_preserve", SMOOTH_VOLUME_PRESERVE)
    )
    PRESERVE_SOURCE_BOUNDS = bool(
        config.get("preserve_source_bounds", PRESERVE_SOURCE_BOUNDS)
    )
    MAX_BOUNDS_ERROR_MM = float(
        config.get("max_bounds_error_mm", MAX_BOUNDS_ERROR_MM)
    )

    overhang = config.get("thin_overhang_support", {})
    ENABLE_THIN_OVERHANG_SUPPORT = bool(
        overhang.get("enabled", ENABLE_THIN_OVERHANG_SUPPORT)
    )
    THIN_OVERHANG_MAX_THICKNESS_MM = float(
        overhang.get(
            "max_thickness_mm",
            THIN_OVERHANG_MAX_THICKNESS_MM,
        )
    )
    THIN_OVERHANG_MIN_HORIZONTAL_SPAN_MM = float(
        overhang.get(
            "min_horizontal_span_mm",
            THIN_OVERHANG_MIN_HORIZONTAL_SPAN_MM,
        )
    )
    THIN_OVERHANG_MIN_HEIGHT_RATIO = float(
        overhang.get(
            "min_height_ratio",
            THIN_OVERHANG_MIN_HEIGHT_RATIO,
        )
    )
    THIN_OVERHANG_SUPPORT_DROP_MM = float(
        overhang.get(
            "support_drop_mm",
            THIN_OVERHANG_SUPPORT_DROP_MM,
        )
    )
    THIN_OVERHANG_MAX_LENGTH_RATIO = float(
        overhang.get(
            "max_length_ratio",
            THIN_OVERHANG_MAX_LENGTH_RATIO,
        )
    )
    THIN_OVERHANG_MIN_WIDTH_RATIO = float(
        overhang.get(
            "min_width_ratio",
            THIN_OVERHANG_MIN_WIDTH_RATIO,
        )
    )
    THIN_OVERHANG_MIN_END_RATIO = float(
        overhang.get(
            "min_end_ratio",
            THIN_OVERHANG_MIN_END_RATIO,
        )
    )
    THIN_OVERHANG_MIN_ASPECT_RATIO = float(
        overhang.get(
            "min_aspect_ratio",
            THIN_OVERHANG_MIN_ASPECT_RATIO,
        )
    )

    inset = config.get("lower_body_inset", {})
    ENABLE_LOWER_BODY_INSET = bool(
        inset.get("enabled", ENABLE_LOWER_BODY_INSET)
    )
    LOWER_BODY_INSET_START_HEIGHT_RATIO = float(
        inset.get(
            "start_height_ratio",
            LOWER_BODY_INSET_START_HEIGHT_RATIO,
        )
    )
    LOWER_BODY_INSET_FULL_HEIGHT_RATIO = float(
        inset.get(
            "full_height_ratio",
            LOWER_BODY_INSET_FULL_HEIGHT_RATIO,
        )
    )
    LOWER_BODY_INSET_MM = float(
        inset.get("distance_mm", LOWER_BODY_INSET_MM)
    )

    COLLISION_THICKNESS_MM = float(
        config.get("thickness_mm", COLLISION_THICKNESS_MM)
    )
    COLLISION_FRICTION = float(
        config.get("friction", COLLISION_FRICTION)
    )
    COLLISION_USE_CULLING = bool(
        config.get("use_culling", COLLISION_USE_CULLING)
    )
    COLLISION_USE_NORMAL = bool(
        config.get("use_normal", COLLISION_USE_NORMAL)
    )


def validate_parameters():
    """Reject settings that can create an invalid or misleading proxy."""

    if VOXEL_SIZE_MM <= 0.0:
        raise ValueError("VOXEL_SIZE_MM must be greater than zero")
    minimum_faces, maximum_faces = TARGET_FACE_RANGE
    if minimum_faces < 4 or maximum_faces < minimum_faces:
        raise ValueError("TARGET_FACE_RANGE must be an increasing positive range")
    if not minimum_faces <= TARGET_FACE_COUNT <= maximum_faces:
        raise ValueError("TARGET_FACE_COUNT must be inside TARGET_FACE_RANGE")
    if MAX_FINAL_FACE_COUNT < TARGET_FACE_COUNT:
        raise ValueError(
            "MAX_FINAL_FACE_COUNT must be no lower than TARGET_FACE_COUNT"
        )
    if not 0.0 <= PLANAR_DISSOLVE_ANGLE_DEG <= 45.0:
        raise ValueError("PLANAR_DISSOLVE_ANGLE_DEG must be between 0 and 45")
    if SMOOTH_ITERATIONS < 0:
        raise ValueError("SMOOTH_ITERATIONS cannot be negative")
    if SMOOTH_METHOD not in {"LAPLACIAN", "SIMPLE"}:
        raise ValueError("SMOOTH_METHOD must be LAPLACIAN or SIMPLE")
    if not 0.0 <= SMOOTH_FACTOR <= 1.0:
        raise ValueError("SMOOTH_FACTOR must be between zero and one")
    if not (
        0.0
        <= LOWER_BODY_INSET_FULL_HEIGHT_RATIO
        < LOWER_BODY_INSET_START_HEIGHT_RATIO
        <= 1.0
    ):
        raise ValueError(
            "lower-body height ratios must satisfy "
            "0 <= full < start <= 1"
        )
    if LOWER_BODY_INSET_MM < 0.0:
        raise ValueError("LOWER_BODY_INSET_MM cannot be negative")
    if MAX_BOUNDS_ERROR_MM < 0.0:
        raise ValueError("MAX_BOUNDS_ERROR_MM cannot be negative")
    if THIN_OVERHANG_MAX_THICKNESS_MM <= 0.0:
        raise ValueError("THIN_OVERHANG_MAX_THICKNESS_MM must be positive")
    if THIN_OVERHANG_MIN_HORIZONTAL_SPAN_MM <= 0.0:
        raise ValueError(
            "THIN_OVERHANG_MIN_HORIZONTAL_SPAN_MM must be positive"
        )
    if not 0.0 <= THIN_OVERHANG_MIN_HEIGHT_RATIO <= 1.0:
        raise ValueError(
            "THIN_OVERHANG_MIN_HEIGHT_RATIO must be between zero and one"
        )
    if THIN_OVERHANG_SUPPORT_DROP_MM <= 0.0:
        raise ValueError("THIN_OVERHANG_SUPPORT_DROP_MM must be positive")
    for name, value in (
        ("THIN_OVERHANG_MAX_LENGTH_RATIO", THIN_OVERHANG_MAX_LENGTH_RATIO),
        ("THIN_OVERHANG_MIN_WIDTH_RATIO", THIN_OVERHANG_MIN_WIDTH_RATIO),
        ("THIN_OVERHANG_MIN_END_RATIO", THIN_OVERHANG_MIN_END_RATIO),
    ):
        if not 0.0 < value <= 1.0:
            raise ValueError(f"{name} must be in the interval (0, 1]")
    if THIN_OVERHANG_MIN_ASPECT_RATIO <= 1.0:
        raise ValueError("THIN_OVERHANG_MIN_ASPECT_RATIO must exceed 1")
    if COLLISION_THICKNESS_MM <= 0.0:
        raise ValueError("COLLISION_THICKNESS_MM must be greater than zero")
    if not 0.0 <= COLLISION_FRICTION <= 80.0:
        raise ValueError("COLLISION_FRICTION must be between zero and 80")


def object_exists(obj):
    """Return whether an object reference is still present in bpy.data."""

    return obj is not None and bpy.data.objects.get(obj.name) is obj


def remove_object_and_unused_mesh(obj):
    """Remove one generated object and its mesh when it has no other users."""

    if not object_exists(obj):
        return
    mesh = obj.data if obj.type == "MESH" else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def cleanup_stale_work_objects():
    """Remove only unfinished temporary objects created by this script."""

    stale = [obj for obj in bpy.data.objects if obj.get(WORK_TAG, False)]
    for obj in stale:
        remove_object_and_unused_mesh(obj)
    return len(stale)


def ensure_proxy_collection(scene):
    """Return the proxy collection and ensure it is linked to this scene."""

    collection = bpy.data.collections.get(PROXY_COLLECTION_NAME)
    if collection is None:
        collection = bpy.data.collections.new(PROXY_COLLECTION_NAME)

    scene_collections = {scene.collection}
    scene_collections.update(scene.collection.children_recursive)
    if collection not in scene_collections:
        scene.collection.children.link(collection)
    return collection


def has_cloth_modifier(obj):
    return any(modifier.type == "CLOTH" for modifier in obj.modifiers)


def selected_vehicle_sources():
    """Collect selected vehicle meshes while excluding generated/cloth meshes."""

    sources = []
    skipped = []
    for obj in bpy.context.selected_objects:
        reason = None
        if obj.type != "MESH":
            reason = "not a mesh"
        elif obj.get(GENERATED_TAG, False):
            reason = "already a generated proxy"
        elif obj.get(WORK_TAG, False):
            reason = "temporary proxy object"
        elif EXCLUDE_CLOTH_OBJECTS and has_cloth_modifier(obj):
            reason = "has a Cloth modifier"
        elif len(obj.data.vertices) == 0:
            reason = "empty mesh"

        if reason is None:
            sources.append(obj)
        else:
            skipped.append((obj.name, reason))
    return sources, skipped


def automatic_proxy_name(sources, active_object):
    """Build a deterministic name from the active eligible source."""

    basis = active_object if active_object in sources else sources[0]
    base_name = basis.name
    if base_name.endswith(PROXY_NAME_SUFFIX):
        base_name = base_name[: -len(PROXY_NAME_SUFFIX)]
    return f"{base_name}{PROXY_NAME_SUFFIX}"


def evaluated_world_mesh(source, depsgraph):
    """Create a real mesh containing the evaluated source in world space."""

    evaluated = source.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(
        evaluated,
        preserve_all_data_layers=False,
        depsgraph=depsgraph,
    )
    world_matrix = source.matrix_world.copy()
    for vertex in mesh.vertices:
        vertex.co = world_matrix @ vertex.co
    mesh.update()
    return mesh


def create_work_objects(sources, collection):
    """Create modifier-evaluated copies without touching the source objects."""

    depsgraph = bpy.context.evaluated_depsgraph_get()
    work_objects = []
    for index, source in enumerate(sources, start=1):
        mesh = evaluated_world_mesh(source, depsgraph)
        if len(mesh.vertices) == 0:
            bpy.data.meshes.remove(mesh)
            continue
        work = bpy.data.objects.new(f"CC_PROXY_WORK_{index:03d}", mesh)
        work[WORK_TAG] = True
        work["collision_proxy_source"] = source.name
        collection.objects.link(work)
        work_objects.append(work)
    if not work_objects:
        raise RuntimeError("Selected sources produced no evaluated mesh geometry")
    return work_objects


def select_only(objects, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        if object_exists(obj):
            obj.select_set(True)
    if active is not None and object_exists(active):
        bpy.context.view_layer.objects.active = active


def join_work_objects(work_objects):
    """Join evaluated world-space copies into one mesh object."""

    active = work_objects[0]
    select_only(work_objects, active)
    if len(work_objects) > 1:
        result = bpy.ops.object.join()
        if "FINISHED" not in result:
            raise RuntimeError("Blender failed to join evaluated source meshes")
    active.name = "CC_PROXY_WORK_JOINED"
    active.data.name = "CC_PROXY_WORK_JOINED_MESH"
    active[WORK_TAG] = True
    return active


def apply_modifier(obj, modifier):
    """Apply one modifier with an explicit active-object context."""

    select_only([obj], obj)
    result = bpy.ops.object.modifier_apply(modifier=modifier.name)
    if "FINISHED" not in result:
        raise RuntimeError(f"Failed to apply modifier: {modifier.name}")


def apply_voxel_remesh(proxy):
    modifier = proxy.modifiers.new(REMESH_MODIFIER_NAME, type="REMESH")
    modifier.mode = "VOXEL"
    modifier.voxel_size = VOXEL_SIZE_MM / 1000.0
    modifier.use_remove_disconnected = REMOVE_DISCONNECTED_COMPONENTS
    if REMOVE_DISCONNECTED_COMPONENTS:
        modifier.threshold = 1.0
    modifier.use_smooth_shade = True
    apply_modifier(proxy, modifier)
    if len(proxy.data.polygons) == 0:
        raise RuntimeError(
            "Voxel Remesh produced no faces; confirm 1 BU = 1 m and reduce "
            "VOXEL_SIZE_MM for very small source geometry"
        )


def mesh_bounds(mesh):
    coordinates = [vertex.co for vertex in mesh.vertices]
    minimum = coordinates[0].copy()
    maximum = coordinates[0].copy()
    for coordinate in coordinates[1:]:
        minimum.x = min(minimum.x, coordinate.x)
        minimum.y = min(minimum.y, coordinate.y)
        minimum.z = min(minimum.z, coordinate.z)
        maximum.x = max(maximum.x, coordinate.x)
        maximum.y = max(maximum.y, coordinate.y)
        maximum.z = max(maximum.z, coordinate.z)
    return minimum, maximum


def object_meshes_bounds(objects):
    """Return combined bounds for identity-transform world-space work meshes."""

    bounds = [mesh_bounds(obj.data) for obj in objects]
    minimum = bounds[0][0].copy()
    maximum = bounds[0][1].copy()
    for object_minimum, object_maximum in bounds[1:]:
        for axis in range(3):
            minimum[axis] = min(minimum[axis], object_minimum[axis])
            maximum[axis] = max(maximum[axis], object_maximum[axis])
    return minimum, maximum


def connected_vertex_components(mesh):
    """Return vertex-index lists for every connected mesh island."""

    parent = list(range(len(mesh.vertices)))

    def find(vertex_index):
        while parent[vertex_index] != vertex_index:
            parent[vertex_index] = parent[parent[vertex_index]]
            vertex_index = parent[vertex_index]
        return vertex_index

    for edge in mesh.edges:
        index_a, index_b = edge.vertices
        root_a = find(index_a)
        root_b = find(index_b)
        if root_a != root_b:
            parent[root_b] = root_a

    components_by_root = {}
    for vertex_index in range(len(mesh.vertices)):
        root = find(vertex_index)
        components_by_root.setdefault(root, []).append(vertex_index)
    return list(components_by_root.values())


def component_bounds(mesh, vertex_indices):
    coordinates = [mesh.vertices[index].co for index in vertex_indices]
    minimum = coordinates[0].copy()
    maximum = coordinates[0].copy()
    for coordinate in coordinates[1:]:
        for axis in range(3):
            minimum[axis] = min(minimum[axis], coordinate[axis])
            maximum[axis] = max(maximum[axis], coordinate[axis])
    return minimum, maximum


def append_axis_aligned_box(bm, minimum, maximum):
    """Append a closed box to a BMesh; normals are recalculated later."""

    coordinates = (
        (minimum.x, minimum.y, minimum.z),
        (maximum.x, minimum.y, minimum.z),
        (maximum.x, maximum.y, minimum.z),
        (minimum.x, maximum.y, minimum.z),
        (minimum.x, minimum.y, maximum.z),
        (maximum.x, minimum.y, maximum.z),
        (maximum.x, maximum.y, maximum.z),
        (minimum.x, maximum.y, maximum.z),
    )
    vertices = [bm.verts.new(coordinate) for coordinate in coordinates]
    for indices in (
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ):
        bm.faces.new(tuple(vertices[index] for index in indices))


def detect_thin_overhang_support(work_objects, overall_bounds):
    """Describe at most one likely rear-wing support without editing meshes."""

    if not ENABLE_THIN_OVERHANG_SUPPORT:
        return []

    overall_minimum, overall_maximum = overall_bounds
    overall_height = overall_maximum.z - overall_minimum.z
    if overall_height <= 1.0e-9:
        raise RuntimeError("Proxy has zero world-Z height")

    horizontal_spans = (
        overall_maximum.x - overall_minimum.x,
        overall_maximum.y - overall_minimum.y,
    )
    length_axis = 0 if horizontal_spans[0] >= horizontal_spans[1] else 1
    width_axis = 1 - length_axis
    vehicle_length = horizontal_spans[length_axis]
    vehicle_width = horizontal_spans[width_axis]
    vehicle_center_length = (
        overall_minimum[length_axis] + overall_maximum[length_axis]
    ) * 0.5
    if vehicle_length <= 1.0e-9 or vehicle_width <= 1.0e-9:
        raise RuntimeError("Proxy has a zero-size horizontal bounds axis")

    maximum_thickness = THIN_OVERHANG_MAX_THICKNESS_MM / 1000.0
    minimum_span = THIN_OVERHANG_MIN_HORIZONTAL_SPAN_MM / 1000.0
    minimum_z = (
        overall_minimum.z
        + overall_height * THIN_OVERHANG_MIN_HEIGHT_RATIO
    )
    support_drop = THIN_OVERHANG_SUPPORT_DROP_MM / 1000.0
    minimum_footprint = VOXEL_SIZE_MM / 2000.0
    candidates = []

    for work_object in work_objects:
        mesh = work_object.data
        source_name = str(work_object.get("collision_proxy_source", ""))
        normalized_name = source_name.casefold()
        name_hint = any(
            hint.casefold() in normalized_name
            for hint in THIN_OVERHANG_NAME_HINTS
        )

        for component in connected_vertex_components(mesh):
            if len(component) < 4:
                continue
            component_minimum, component_maximum = component_bounds(
                mesh,
                component,
            )
            spans = (
                component_maximum.x - component_minimum.x,
                component_maximum.y - component_minimum.y,
            )
            length_span = spans[length_axis]
            width_span = spans[width_axis]
            span_z = component_maximum.z - component_minimum.z
            if span_z > maximum_thickness:
                continue
            if max(spans) < minimum_span or min(spans) < minimum_footprint:
                continue
            if component_minimum.z < minimum_z:
                continue

            length_ratio = length_span / vehicle_length
            width_ratio = width_span / vehicle_width
            aspect_ratio = width_span / max(length_span, 1.0e-9)
            component_center_length = (
                component_minimum[length_axis]
                + component_maximum[length_axis]
            ) * 0.5
            end_ratio = abs(
                component_center_length - vehicle_center_length
            ) / (vehicle_length * 0.5)
            height_ratio = (
                component_maximum.z - overall_minimum.z
            ) / overall_height

            if length_ratio > THIN_OVERHANG_MAX_LENGTH_RATIO:
                continue
            if width_ratio < THIN_OVERHANG_MIN_WIDTH_RATIO:
                continue
            if end_ratio < THIN_OVERHANG_MIN_END_RATIO:
                continue
            if aspect_ratio < THIN_OVERHANG_MIN_ASPECT_RATIO:
                continue

            score = (
                (10.0 if name_hint else 0.0)
                + end_ratio * 3.0
                + width_ratio * 2.0
                + height_ratio
                - length_ratio
                - span_z / maximum_thickness * 0.25
            )
            candidates.append(
                {
                    "work_object": work_object,
                    "source_name": source_name,
                    "minimum": component_minimum,
                    "maximum": component_maximum,
                    "island_vertices": len(component),
                    "island_thickness_mm": span_z * 1000.0,
                    "horizontal_span_mm": max(spans) * 1000.0,
                    "length_ratio": length_ratio,
                    "width_ratio": width_ratio,
                    "end_ratio": end_ratio,
                    "name_hint": name_hint,
                    "score": score,
                }
            )

    if not candidates:
        return []

    selected = max(candidates, key=lambda candidate: candidate["score"])
    support_minimum = selected["minimum"].copy()
    support_minimum.z = max(
        overall_minimum.z,
        selected["minimum"].z - support_drop,
    )
    support_maximum = selected["maximum"].copy()
    if support_maximum.z - support_minimum.z < VOXEL_SIZE_MM / 1000.0:
        return []

    selected["minimum"] = support_minimum
    selected["maximum"] = support_maximum
    del selected["work_object"]
    return [selected]


def append_overhang_support(proxy, supports):
    """Append detected support geometry after topology decimation."""

    if not supports:
        return

    mesh = proxy.data
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        for support in supports:
            append_axis_aligned_box(
                bm,
                support["minimum"],
                support["maximum"],
            )
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()


def smoothstep(value):
    value = min(max(value, 0.0), 1.0)
    return value * value * (3.0 - 2.0 * value)


def inset_lower_body(proxy):
    """Taper the lower shell toward its XY center for free cloth drape."""

    if not ENABLE_LOWER_BODY_INSET or LOWER_BODY_INSET_MM <= 0.0:
        return 0

    minimum, maximum = mesh_bounds(proxy.data)
    height = maximum.z - minimum.z
    if height <= 1.0e-9:
        raise RuntimeError("Proxy has zero world-Z height")

    center_x = (minimum.x + maximum.x) * 0.5
    center_y = (minimum.y + maximum.y) * 0.5
    start_z = minimum.z + height * LOWER_BODY_INSET_START_HEIGHT_RATIO
    full_z = minimum.z + height * LOWER_BODY_INSET_FULL_HEIGHT_RATIO
    transition_height = max(start_z - full_z, 1.0e-9)
    inset_distance = LOWER_BODY_INSET_MM / 1000.0
    changed = 0

    for vertex in proxy.data.vertices:
        if vertex.co.z >= start_z:
            continue
        factor = smoothstep((start_z - vertex.co.z) / transition_height)
        delta_x = vertex.co.x - center_x
        delta_y = vertex.co.y - center_y
        radius = (delta_x * delta_x + delta_y * delta_y) ** 0.5
        if radius <= 1.0e-9:
            continue
        target_radius = max(radius - inset_distance * factor, radius * 0.10)
        scale = target_radius / radius
        vertex.co.x = center_x + delta_x * scale
        vertex.co.y = center_y + delta_y * scale
        changed += 1

    proxy.data.update()
    return changed


def apply_smoothing(proxy):
    if SMOOTH_ITERATIONS <= 0 or SMOOTH_FACTOR <= 0.0:
        return
    if SMOOTH_METHOD == "LAPLACIAN":
        modifier = proxy.modifiers.new(
            SMOOTH_MODIFIER_NAME,
            type="LAPLACIANSMOOTH",
        )
        modifier.lambda_factor = SMOOTH_FACTOR
        modifier.lambda_border = SMOOTH_FACTOR
        modifier.iterations = SMOOTH_ITERATIONS
        modifier.use_normalized = True
        modifier.use_volume_preserve = SMOOTH_VOLUME_PRESERVE
    else:
        modifier = proxy.modifiers.new(SMOOTH_MODIFIER_NAME, type="SMOOTH")
        modifier.factor = SMOOTH_FACTOR
        modifier.iterations = SMOOTH_ITERATIONS
        modifier.use_x = True
        modifier.use_y = True
        modifier.use_z = True
    apply_modifier(proxy, modifier)


def mesh_triangle_count(mesh):
    """Return evaluated triangle count, including triangulated n-gons."""

    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def apply_collapse_decimation(proxy, target_triangles, modifier_name):
    """Collapse toward a triangle budget and return the resulting count."""

    triangle_count = mesh_triangle_count(proxy.data)
    if triangle_count <= target_triangles:
        return triangle_count

    modifier = proxy.modifiers.new(modifier_name, type="DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.ratio = max(
        min(target_triangles / triangle_count, 1.0),
        0.001,
    )
    modifier.use_collapse_triangulate = False
    apply_modifier(proxy, modifier)
    return mesh_triangle_count(proxy.data)


def apply_planar_dissolve(proxy):
    """Dissolve nearly coplanar edges after collapse without changing bounds."""

    if not ENABLE_PLANAR_DISSOLVE or PLANAR_DISSOLVE_ANGLE_DEG <= 0.0:
        return mesh_triangle_count(proxy.data)

    modifier = proxy.modifiers.new(
        f"{DECIMATE_MODIFIER_NAME} Planar",
        type="DECIMATE",
    )
    modifier.decimate_type = "DISSOLVE"
    modifier.angle_limit = PLANAR_DISSOLVE_ANGLE_DEG * 0.017453292519943295
    modifier.use_dissolve_boundaries = False
    apply_modifier(proxy, modifier)
    return mesh_triangle_count(proxy.data)


def apply_decimation(proxy, reserved_triangles=0):
    """Enforce the collision triangle budget in one or two collapse passes."""

    available_budget = MAX_FINAL_FACE_COUNT - reserved_triangles
    if available_budget < TARGET_FACE_COUNT:
        raise RuntimeError(
            "Reserved collision geometry exceeds the configured triangle "
            "budget"
        )
    source_triangles = mesh_triangle_count(proxy.data)
    collapsed_triangles = source_triangles
    if source_triangles > available_budget:
        collapsed_triangles = apply_collapse_decimation(
            proxy,
            TARGET_FACE_COUNT,
            DECIMATE_MODIFIER_NAME,
        )

    planar_triangles = apply_planar_dissolve(proxy)
    final_triangles = planar_triangles
    if final_triangles > available_budget:
        final_triangles = apply_collapse_decimation(
            proxy,
            TARGET_FACE_COUNT,
            f"{DECIMATE_MODIFIER_NAME} Budget",
        )

    if final_triangles > available_budget:
        raise RuntimeError(
            f"Collision proxy remains at {final_triangles} triangles after "
            f"decimation; available budget is {available_budget}."
        )
    return (
        source_triangles,
        collapsed_triangles,
        planar_triangles,
        final_triangles,
    )


def bounds_dimensions(bounds):
    minimum, maximum = bounds
    return tuple(maximum[index] - minimum[index] for index in range(3))


def preserve_reference_bounds(proxy, reference_bounds):
    """Restore source X/Y/Z bounds after remesh/smoothing/decimation.

    This is an axis-aligned affine correction, not a claim that every local
    feature is exact. Its purpose is to prevent systematic loss of vehicle
    length, width, height, wheel-track envelope, hood height, or spoiler tip.
    """

    current_bounds = mesh_bounds(proxy.data)
    reference_dimensions = bounds_dimensions(reference_bounds)
    current_dimensions = bounds_dimensions(current_bounds)
    before_error_mm = max(
        abs(current_dimensions[index] - reference_dimensions[index]) * 1000.0
        for index in range(3)
    )
    scales = [1.0, 1.0, 1.0]

    if PRESERVE_SOURCE_BOUNDS:
        reference_minimum, reference_maximum = reference_bounds
        current_minimum, current_maximum = current_bounds
        for axis in range(3):
            current_extent = current_dimensions[axis]
            reference_extent = reference_dimensions[axis]
            if current_extent <= 1.0e-12:
                raise RuntimeError("Proxy has a zero-size bounds axis")
            scales[axis] = reference_extent / current_extent
            current_center = (
                current_minimum[axis] + current_maximum[axis]
            ) * 0.5
            reference_center = (
                reference_minimum[axis] + reference_maximum[axis]
            ) * 0.5
            for vertex in proxy.data.vertices:
                vertex.co[axis] = reference_center + (
                    vertex.co[axis] - current_center
                ) * scales[axis]
        proxy.data.update()

    corrected_dimensions = bounds_dimensions(mesh_bounds(proxy.data))
    after_error_mm = max(
        abs(corrected_dimensions[index] - reference_dimensions[index]) * 1000.0
        for index in range(3)
    )
    if after_error_mm > MAX_BOUNDS_ERROR_MM:
        raise RuntimeError(
            f"Collision Proxy bounds error {after_error_mm:.3f} mm exceeds "
            f"MAX_BOUNDS_ERROR_MM={MAX_BOUNDS_ERROR_MM:g}"
        )
    return tuple(scales), before_error_mm, after_error_mm


def recalculate_normals(proxy):
    mesh = proxy.data
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.validate(clean_customdata=False)
    mesh.update()


def configure_collision(proxy):
    modifier = next(
        (item for item in proxy.modifiers if item.type == "COLLISION"),
        None,
    )
    if modifier is None:
        modifier = proxy.modifiers.new(COLLISION_MODIFIER_NAME, type="COLLISION")
    modifier.name = COLLISION_MODIFIER_NAME

    settings = proxy.collision
    settings.use = True
    settings.thickness_outer = COLLISION_THICKNESS_MM / 1000.0
    settings.cloth_friction = COLLISION_FRICTION
    if hasattr(settings, "use_culling"):
        settings.use_culling = COLLISION_USE_CULLING
    if hasattr(settings, "use_normal"):
        settings.use_normal = COLLISION_USE_NORMAL


def finalize_proxy(
    proxy,
    sources,
    target_name,
    collection,
    changed_vertices,
    overhang_supports,
    fidelity_report,
):
    """Replace only a same-name proxy previously generated by this script."""

    old_proxy = bpy.data.objects.get(target_name)
    if old_proxy is not None and old_proxy is not proxy:
        if old_proxy.get(GENERATED_TAG, False):
            remove_object_and_unused_mesh(old_proxy)
        else:
            print(
                f"[CC PROXY WARNING] '{target_name}' exists and is not "
                "script-generated; Blender will assign a unique suffix."
            )

    proxy.name = target_name
    proxy.data.name = f"{proxy.name} Mesh"
    proxy[GENERATED_TAG] = True
    if WORK_TAG in proxy:
        del proxy[WORK_TAG]
    proxy["collision_proxy_preset"] = PRESET_NAME
    proxy["collision_proxy_sources"] = ", ".join(obj.name for obj in sources)
    proxy["collision_proxy_voxel_size_mm"] = VOXEL_SIZE_MM
    proxy["collision_proxy_use_voxel_remesh"] = ENABLE_VOXEL_REMESH
    proxy["collision_proxy_target_faces"] = TARGET_FACE_COUNT
    proxy["collision_proxy_target_triangles"] = TARGET_FACE_COUNT
    proxy["collision_proxy_max_triangles"] = MAX_FINAL_FACE_COUNT
    proxy["collision_proxy_remove_disconnected"] = (
        REMOVE_DISCONNECTED_COMPONENTS
    )
    proxy["collision_proxy_smooth_method"] = SMOOTH_METHOD
    proxy["collision_proxy_preserve_source_bounds"] = PRESERVE_SOURCE_BOUNDS
    proxy["collision_proxy_thin_overhang_support_enabled"] = (
        ENABLE_THIN_OVERHANG_SUPPORT
    )
    proxy["collision_proxy_thin_overhang_support_count"] = len(
        overhang_supports
    )
    selected_overhang = overhang_supports[0] if overhang_supports else None
    proxy["collision_proxy_thin_overhang_source"] = (
        selected_overhang["source_name"] if selected_overhang else ""
    )
    proxy["collision_proxy_thin_overhang_score"] = (
        selected_overhang["score"] if selected_overhang else 0.0
    )
    proxy["collision_proxy_thickness_mm"] = COLLISION_THICKNESS_MM
    proxy["collision_proxy_friction"] = COLLISION_FRICTION
    proxy["collision_proxy_lower_inset_enabled"] = ENABLE_LOWER_BODY_INSET
    proxy["collision_proxy_lower_inset_mm"] = (
        LOWER_BODY_INSET_MM if ENABLE_LOWER_BODY_INSET else 0.0
    )
    proxy["collision_proxy_lower_inset_vertex_count"] = changed_vertices
    scales, before_error_mm, after_error_mm = fidelity_report
    proxy["collision_proxy_bounds_scale_xyz"] = list(scales)
    proxy["collision_proxy_bounds_error_before_mm"] = before_error_mm
    proxy["collision_proxy_bounds_error_after_mm"] = after_error_mm

    if collection not in proxy.users_collection:
        collection.objects.link(proxy)
    for user_collection in list(proxy.users_collection):
        if user_collection != collection:
            user_collection.objects.unlink(proxy)

    proxy.hide_render = HIDE_PROXY_FROM_RENDER
    proxy.display_type = PROXY_DISPLAY_TYPE
    proxy.show_in_front = SHOW_PROXY_IN_FRONT
    for polygon in proxy.data.polygons:
        polygon.use_smooth = True


def main():
    if bpy.context.mode != "OBJECT":
        raise RuntimeError("Switch to Object Mode before generating the proxy")

    validate_parameters()
    stale_count = cleanup_stale_work_objects()
    original_selection = list(bpy.context.selected_objects)
    original_active = bpy.context.view_layer.objects.active
    sources, skipped = selected_vehicle_sources()
    if not sources:
        raise RuntimeError(
            "Select at least one non-Cloth vehicle Mesh object in Object Mode"
        )

    for name, reason in skipped:
        print(f"[CC PROXY] skipped {name}: {reason}")

    target_name = automatic_proxy_name(sources, original_active)
    collection = ensure_proxy_collection(bpy.context.scene)
    proxy = None

    print("")
    print("=" * 64)
    print(f"GENERATE COLLISION PROXY: {PRESET_NAME}")
    print("=" * 64)
    print(f"Sources ({len(sources)}): {', '.join(obj.name for obj in sources)}")
    if stale_count:
        print(f"Removed {stale_count} stale temporary proxy object(s)")

    try:
        work_objects = create_work_objects(sources, collection)
        source_triangles = sum(
            mesh_triangle_count(obj.data) for obj in work_objects
        )
        source_bounds = object_meshes_bounds(work_objects)
        overhang_supports = detect_thin_overhang_support(
            work_objects,
            source_bounds,
        )
        proxy = join_work_objects(work_objects)
        joined_triangles = mesh_triangle_count(proxy.data)
        remesh_triangles = None
        if ENABLE_VOXEL_REMESH:
            append_overhang_support(proxy, overhang_supports)
            apply_voxel_remesh(proxy)
            remesh_triangles = mesh_triangle_count(proxy.data)
        changed_vertices = inset_lower_body(proxy)
        apply_smoothing(proxy)
        reserved_triangles = (
            12 * len(overhang_supports)
            if not ENABLE_VOXEL_REMESH
            else 0
        )
        decimation_report = apply_decimation(proxy, reserved_triangles)
        (
            pre_decimate_triangles,
            collapsed_triangles,
            planar_triangles,
            final_triangles,
        ) = decimation_report
        fidelity_report = preserve_reference_bounds(proxy, source_bounds)
        if not ENABLE_VOXEL_REMESH:
            append_overhang_support(proxy, overhang_supports)
            final_triangles = mesh_triangle_count(proxy.data)
        if final_triangles > MAX_FINAL_FACE_COUNT:
            raise RuntimeError(
                f"Final collision proxy has {final_triangles} triangles; "
                f"budget is {MAX_FINAL_FACE_COUNT}."
            )
        proxy["collision_proxy_source_triangles"] = source_triangles
        proxy["collision_proxy_final_triangles"] = final_triangles
        proxy["collision_proxy_reduction_ratio"] = (
            final_triangles / max(source_triangles, 1)
        )
        recalculate_normals(proxy)
        configure_collision(proxy)
        finalize_proxy(
            proxy,
            sources,
            target_name,
            collection,
            changed_vertices,
            overhang_supports,
            fidelity_report,
        )

        minimum, maximum = mesh_bounds(proxy.data)
        dimensions_mm = tuple(
            (maximum[index] - minimum[index]) * 1000.0
            for index in range(3)
        )
        select_only([proxy], proxy)

        remesh_note = (
            str(remesh_triangles)
            if remesh_triangles is not None
            else "OFF"
        )
        print(
            f"Triangles: source={source_triangles}, "
            f"joined={joined_triangles}, "
            f"voxel-remesh={remesh_note}, "
            f"pre-decimate={pre_decimate_triangles}, "
            f"collapse={collapsed_triangles}, "
            f"planar={planar_triangles}, final={final_triangles}"
        )
        print(
            "Collision performance budget: "
            f"target={TARGET_FACE_COUNT}, max={MAX_FINAL_FACE_COUNT}, "
            f"kept={final_triangles / max(source_triangles, 1):.1%}"
        )
        print(
            "Bounds: "
            f"X={dimensions_mm[0]:.1f} mm, "
            f"Y={dimensions_mm[1]:.1f} mm, "
            f"Z={dimensions_mm[2]:.1f} mm"
        )
        print(
            f"Lower-body inset: enabled={ENABLE_LOWER_BODY_INSET}, "
            f"distance={LOWER_BODY_INSET_MM:g} mm, "
            f"changed_vertices={changed_vertices}"
        )
        print(
            "Thin-overhang support: "
            f"enabled={ENABLE_THIN_OVERHANG_SUPPORT}, "
            f"islands={len(overhang_supports)}, "
            f"max_thickness={THIN_OVERHANG_MAX_THICKNESS_MM:g} mm, "
            f"drop={THIN_OVERHANG_SUPPORT_DROP_MM:g} mm"
        )
        for index, support in enumerate(overhang_supports, start=1):
            print(
                f"  support {index}: "
                f"source={support['source_name']}, "
                f"thickness={support['island_thickness_mm']:.1f} mm, "
                f"span={support['horizontal_span_mm']:.1f} mm, "
                f"end={support['end_ratio']:.2f}, "
                f"score={support['score']:.2f}, "
                f"vertices={support['island_vertices']}"
            )
        if ENABLE_LOWER_BODY_INSET:
            print(
                "[CC PROXY FIDELITY WARNING] Lower-body inset changes the "
                "vehicle reference envelope. Use it only for a separate "
                "drape-support proxy, never for dimensional Fit metrics."
            )
        scales, before_error_mm, after_error_mm = fidelity_report
        print(
            "Bounds fidelity: "
            f"pre-correction max error={before_error_mm:.3f} mm, "
            f"post-correction max error={after_error_mm:.6f} mm, "
            f"scale=({scales[0]:.6f}, {scales[1]:.6f}, {scales[2]:.6f})"
        )
        print(
            f"Collision: thickness={COLLISION_THICKNESS_MM:g} mm, "
            f"friction={COLLISION_FRICTION:g}, "
            f"collection={collection.name}"
        )
        print(f"Created: {proxy.name}")
        print(
            "Next: this proxy is selected for inspection. Before running "
            "setup_cloth_standalone.py, select only the actual car-cover "
            "mesh; never apply Cloth to this proxy."
        )
        print("=" * 64)
        return proxy
    except Exception:
        cleanup_stale_work_objects()
        select_only(
            [obj for obj in original_selection if object_exists(obj)],
            original_active if object_exists(original_active) else None,
        )
        raise


if __name__ == "__main__":
    main()
