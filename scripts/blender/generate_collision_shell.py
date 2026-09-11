"""Build a two-stage, watertight vehicle shell for cloth collision tests.

Standalone Blender usage:
1. Switch to Object Mode.
2. Select the visible vehicle mesh objects; keep cloth and old proxies unselected.
3. Run this file in Blender's Text Editor.

The selected, modifier-evaluated geometry is never edited. Stage one voxelizes
all parts into one inspected Outer Shell and probes its top silhouette. If a
zero-thickness hood or roof was lost, the stage is rebuilt from a temporary,
deep inward-solidified copy. Stage two extracts a coarser collision surface from
that shell, smooths and decimates it, repairs the low-poly surface, restores
source bounds, runs lightweight geometry/silhouette checks, and enables
Collision physics only on the final proxy. Original source objects are never
made colliders.
"""

import bmesh
import bpy
import math
from mathutils import Vector
from mathutils.bvhtree import BVHTree


# ============================================================
# EMBEDDED TEST PRESET: CarCover_TwoStageOuterShell_TEST_V2
# Z is world up; 1 Blender Unit = 1 metre.
# ============================================================

PRESET_NAME = "CarCover_TwoStageOuterShell_TEST_V2"
OUTER_SHELL_SUFFIX = " Outer Shell TEST"
COLLISION_SUFFIX = " Shell Collision TEST"

# Fine enough to retain hood/roof/trunk silhouette while merging panel gaps,
# glass, wheels and interior pieces into one exterior volume.
OUTER_SHELL_VOXEL_MM = 35.0
OUTER_SHELL_SMOOTH_ITERATIONS = 2
OUTER_SHELL_SMOOTH_FACTOR = 0.08

# Fast mode keeps silhouette checks advisory. Automatic deep Solidify repair
# can multiply voxel output into millions of faces on detailed vehicles, so it
# is disabled by default; enable it only for a final-quality rebuild.
ENABLE_THIN_SURFACE_REPAIR = False
ENFORCE_TOP_SURFACE_ACCURACY = False
THIN_SURFACE_PROTECTION_MM = 250.0
# 128 rays retain broad roof/hood/trunk coverage with low BVH query overhead.
TOP_SURFACE_SAMPLES_X = 8
TOP_SURFACE_SAMPLES_Y = 16
TOP_SURFACE_X_INSET_FACTOR = 0.08
TOP_SURFACE_Y_INSET_FACTOR = 0.03
TOP_SURFACE_MIN_HEIGHT_FACTOR = 0.38
TOP_SURFACE_DROP_TOLERANCE_MM = 70.0
MAX_TOP_SURFACE_DAMAGE_FRACTION = 0.02
MIN_TOP_SURFACE_SAMPLE_COUNT = 32

# A second extraction removes residual grooves and produces the actual solver
# surface. The cloth mesh target is 50 mm, so a 50 mm collision voxel is a
# useful compromise between silhouette fidelity and contact performance.
COLLISION_VOXEL_MM = 50.0
COLLISION_SMOOTH_ITERATIONS = 4
COLLISION_SMOOTH_FACTOR = 0.12
TARGET_TRIANGLES = 6000
MAX_TRIANGLES = 8000
POST_DECIMATE_SMOOTH_ITERATIONS = 2
POST_DECIMATE_SMOOTH_FACTOR = 0.08

# Voxel Remesh places its reconstructed surface around occupied voxel cells,
# which can leave broad panels locally outside the source even after the AABB
# is restored. Pull the remeshed surface inward before the final bounds restore;
# the restore keeps the overall vehicle dimensions while retaining the local
# anti-bulge correction.
VOXEL_INWARD_COMPENSATION_FACTOR = 0.45

PRESERVE_SOURCE_BOUNDS = True
MAX_BOUNDS_ERROR_MM = 1.0
KEEP_OUTER_SHELL = True

# Cloth already keeps OBJECT_COLLISION_DISTANCE_MM away from the collider.
# Keep the collider-side margin small so the proxy does not visibly inflate
# the fitted cover beyond the source vehicle dimensions.
COLLISION_THICKNESS_MM = 1.0
COLLISION_FRICTION = 3.0
COLLISION_USE_CULLING = False
COLLISION_USE_NORMAL = True

# High-detail vehicles can contain millions of evaluated triangles. Voxel
# remesh does not need that density. Only temporary work copies are simplified.
PRE_VOXEL_MAX_TRIANGLES = 180000
PRE_VOXEL_MIN_TRIANGLES_PER_OBJECT = 500
# The stage-one voxel mesh is only an intermediate silhouette. Reducing it
# before smoothing/component inspection also makes the stage-two copy cheaper.
OUTER_SHELL_POST_VOXEL_MAX_TRIANGLES = 30000

# Guard against wrong units or distant geometry before Blender allocates a
# huge dense voxel grid. Normal passenger vehicles are usually near 1M cells.
MAX_ESTIMATED_VOXEL_CELLS = 8000000

HIDE_FROM_RENDER = True
SHOW_IN_FRONT = True
EXCLUDE_CLOTH_OBJECTS = True

GENERATED_TAG = "car_cover_generated_collision_shell_test"
OUTER_SHELL_TAG = "car_cover_generated_outer_shell_test"
COLLISION_PROXY_TAG = "car_cover_generated_collision_proxy"
WORK_TAG = "car_cover_collision_shell_test_work"


def validate_parameters():
    """Reject values that cannot produce a useful collision shell."""

    if OUTER_SHELL_VOXEL_MM <= 0.0 or COLLISION_VOXEL_MM <= 0.0:
        raise ValueError("Voxel sizes must be positive")
    if COLLISION_VOXEL_MM < OUTER_SHELL_VOXEL_MM:
        raise ValueError(
            "COLLISION_VOXEL_MM must be no smaller than "
            "OUTER_SHELL_VOXEL_MM"
        )
    if TARGET_TRIANGLES < 100 or MAX_TRIANGLES < TARGET_TRIANGLES:
        raise ValueError("Triangle limits are invalid")
    if PRE_VOXEL_MAX_TRIANGLES < MAX_TRIANGLES:
        raise ValueError("PRE_VOXEL_MAX_TRIANGLES must exceed MAX_TRIANGLES")
    if PRE_VOXEL_MIN_TRIANGLES_PER_OBJECT < 100:
        raise ValueError("PRE_VOXEL_MIN_TRIANGLES_PER_OBJECT is too small")
    if OUTER_SHELL_POST_VOXEL_MAX_TRIANGLES < MAX_TRIANGLES:
        raise ValueError(
            "OUTER_SHELL_POST_VOXEL_MAX_TRIANGLES must exceed MAX_TRIANGLES"
        )
    if MAX_ESTIMATED_VOXEL_CELLS < 1000:
        raise ValueError("MAX_ESTIMATED_VOXEL_CELLS is too small")
    if not 0.0 <= VOXEL_INWARD_COMPENSATION_FACTOR <= 0.5:
        raise ValueError(
            "VOXEL_INWARD_COMPENSATION_FACTOR must be in [0, 0.5]"
        )
    for name, iterations, factor in (
        (
            "outer shell",
            OUTER_SHELL_SMOOTH_ITERATIONS,
            OUTER_SHELL_SMOOTH_FACTOR,
        ),
        (
            "collision",
            COLLISION_SMOOTH_ITERATIONS,
            COLLISION_SMOOTH_FACTOR,
        ),
        (
            "post-decimate collision",
            POST_DECIMATE_SMOOTH_ITERATIONS,
            POST_DECIMATE_SMOOTH_FACTOR,
        ),
    ):
        if iterations < 0 or not 0.0 <= factor <= 1.0:
            raise ValueError(f"Invalid {name} smoothing settings")
    if MAX_BOUNDS_ERROR_MM < 0.0:
        raise ValueError("MAX_BOUNDS_ERROR_MM cannot be negative")
    if COLLISION_THICKNESS_MM <= 0.0:
        raise ValueError("COLLISION_THICKNESS_MM must be positive")
    if not 0.0 <= COLLISION_FRICTION <= 80.0:
        raise ValueError("COLLISION_FRICTION must be between 0 and 80")
    if THIN_SURFACE_PROTECTION_MM <= 0.0:
        raise ValueError("THIN_SURFACE_PROTECTION_MM must be positive")
    if TOP_SURFACE_SAMPLES_X < 2 or TOP_SURFACE_SAMPLES_Y < 2:
        raise ValueError("Top-surface probe needs at least 2 samples per axis")
    if not 0.0 <= TOP_SURFACE_X_INSET_FACTOR < 0.5:
        raise ValueError("TOP_SURFACE_X_INSET_FACTOR must be in [0, 0.5)")
    if not 0.0 <= TOP_SURFACE_Y_INSET_FACTOR < 0.5:
        raise ValueError("TOP_SURFACE_Y_INSET_FACTOR must be in [0, 0.5)")
    if not 0.0 <= TOP_SURFACE_MIN_HEIGHT_FACTOR <= 1.0:
        raise ValueError("TOP_SURFACE_MIN_HEIGHT_FACTOR must be in [0, 1]")
    if TOP_SURFACE_DROP_TOLERANCE_MM <= 0.0:
        raise ValueError("TOP_SURFACE_DROP_TOLERANCE_MM must be positive")
    if not 0.0 <= MAX_TOP_SURFACE_DAMAGE_FRACTION <= 1.0:
        raise ValueError(
            "MAX_TOP_SURFACE_DAMAGE_FRACTION must be in [0, 1]"
        )
    if MIN_TOP_SURFACE_SAMPLE_COUNT < 1:
        raise ValueError("MIN_TOP_SURFACE_SAMPLE_COUNT must be positive")


def object_exists(obj):
    if obj is None:
        return False
    try:
        return bpy.data.objects.get(obj.name) is obj
    except ReferenceError:
        return False


def remove_object_and_mesh(obj):
    """Remove one script-owned object and its now-unused mesh."""

    if not object_exists(obj):
        return
    mesh = obj.data if obj.type == "MESH" else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def cleanup_stale_work_objects():
    stale = [obj for obj in bpy.data.objects if obj.get(WORK_TAG, False)]
    for obj in stale:
        remove_object_and_mesh(obj)
    return len(stale)


def ensure_collection(scene, collection_name):
    """Return the scene collection named after the target source object."""

    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        collection = bpy.data.collections.new(collection_name)
    scene_collections = {scene.collection}
    scene_collections.update(scene.collection.children_recursive)
    if collection not in scene_collections:
        scene.collection.children.link(collection)
    return collection


def has_cloth_modifier(obj):
    return any(modifier.type == "CLOTH" for modifier in obj.modifiers)


def selected_vehicle_sources():
    """Return selected source meshes while excluding cloth and generated data."""

    sources = []
    skipped = []
    for obj in bpy.context.selected_objects:
        reason = None
        if obj.type != "MESH":
            reason = "not a mesh"
        elif obj.get(GENERATED_TAG, False):
            reason = "already generated by this test"
        elif obj.get(OUTER_SHELL_TAG, False):
            reason = "already an Outer Shell"
        elif obj.get(COLLISION_PROXY_TAG, False):
            reason = "already a generated collision proxy"
        elif obj.get(WORK_TAG, False):
            reason = "temporary test object"
        elif EXCLUDE_CLOTH_OBJECTS and has_cloth_modifier(obj):
            reason = "has a Cloth modifier"
        elif len(obj.data.vertices) == 0:
            reason = "empty mesh"

        if reason is None:
            sources.append(obj)
        else:
            skipped.append((obj.name, reason))
    return sources, skipped


def source_base_name(sources, active_object):
    basis = active_object if active_object in sources else sources[0]
    name = basis.name
    for suffix in (OUTER_SHELL_SUFFIX, COLLISION_SUFFIX):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def select_only(objects, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        if object_exists(obj):
            obj.select_set(True)
    if active is not None and object_exists(active):
        bpy.context.view_layer.objects.active = active


def evaluated_world_mesh(source, depsgraph):
    """Copy one evaluated source into a real identity/world-space mesh."""

    evaluated = source.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(
        evaluated,
        preserve_all_data_layers=False,
        depsgraph=depsgraph,
    )
    matrix = evaluated.matrix_world.copy()
    for vertex in mesh.vertices:
        vertex.co = matrix @ vertex.co
    mesh.update()
    return mesh


def create_evaluated_work_objects(sources, collection):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    work_objects = []
    for index, source in enumerate(sources, start=1):
        mesh = evaluated_world_mesh(source, depsgraph)
        if not mesh.vertices:
            bpy.data.meshes.remove(mesh)
            continue
        work = bpy.data.objects.new(f"CC_SHELL_WORK_{index:03d}", mesh)
        work[WORK_TAG] = True
        work["collision_shell_source"] = source.name
        collection.objects.link(work)
        work_objects.append(work)
    if not work_objects:
        raise RuntimeError("Selected objects produced no evaluated geometry")
    return work_objects


def join_work_objects(work_objects):
    active = work_objects[0]
    select_only(work_objects, active)
    if len(work_objects) > 1:
        result = bpy.ops.object.join()
        if "FINISHED" not in result:
            raise RuntimeError("Failed to join evaluated vehicle sources")
    active.name = "CC_SHELL_WORK_JOINED"
    active.data.name = "CC_SHELL_WORK_JOINED_MESH"
    active[WORK_TAG] = True
    return active


def mesh_bounds(mesh):
    if not mesh.vertices:
        raise RuntimeError("Cannot measure empty mesh bounds")
    minimum = mesh.vertices[0].co.copy()
    maximum = minimum.copy()
    for vertex in mesh.vertices[1:]:
        coordinate = vertex.co
        for axis in range(3):
            minimum[axis] = min(minimum[axis], coordinate[axis])
            maximum[axis] = max(maximum[axis], coordinate[axis])
    return minimum, maximum


def bounds_dimensions(bounds):
    minimum, maximum = bounds
    return tuple(maximum[axis] - minimum[axis] for axis in range(3))


def combined_bounds(objects):
    bounds = [mesh_bounds(obj.data) for obj in objects]
    minimum = bounds[0][0].copy()
    maximum = bounds[0][1].copy()
    for object_minimum, object_maximum in bounds[1:]:
        for axis in range(3):
            minimum[axis] = min(minimum[axis], object_minimum[axis])
            maximum[axis] = max(maximum[axis], object_maximum[axis])
    return minimum, maximum


def mesh_triangle_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def estimated_voxel_cells(bounds, voxel_mm):
    """Conservative dense-grid cell count for an AABB and voxel size."""

    voxel = voxel_mm / 1000.0
    dimensions = bounds_dimensions(bounds)
    return math.prod(max(1, math.ceil(dimension / voxel) + 3)
                     for dimension in dimensions)


def validate_voxel_budget(bounds):
    dimensions = bounds_dimensions(bounds)
    cells = estimated_voxel_cells(bounds, OUTER_SHELL_VOXEL_MM)
    dimensions_text = " x ".join(f"{value:.3f}" for value in dimensions)
    print(
        f"[CC SHELL] Bounds: {dimensions_text} m; estimated stage-1 grid: "
        f"{cells:,} cells",
        flush=True,
    )
    if cells > MAX_ESTIMATED_VOXEL_CELLS:
        raise RuntimeError(
            f"Estimated voxel grid has {cells:,} cells, above the safe limit "
            f"of {MAX_ESTIMATED_VOXEL_CELLS:,}. Source bounds are "
            f"{dimensions_text} m. Check model units/distant geometry or "
            "increase OUTER_SHELL_VOXEL_MM."
        )


def predecimate_work_objects(work_objects):
    """Reduce evaluated temporary meshes before expensive join/BVH/remesh."""

    counts = [mesh_triangle_count(obj.data) for obj in work_objects]
    total = sum(counts)
    if total <= PRE_VOXEL_MAX_TRIANGLES:
        print(
            f"[CC SHELL] Pre-voxel input: {total:,} triangles; "
            "pre-decimation not needed",
            flush=True,
        )
        return total, total

    ratio = PRE_VOXEL_MAX_TRIANGLES / total
    print(
        f"[CC SHELL] Pre-decimating {total:,} evaluated triangles toward "
        f"{PRE_VOXEL_MAX_TRIANGLES:,} before join/remesh...",
        flush=True,
    )
    for obj, count in zip(work_objects, counts):
        if count <= PRE_VOXEL_MIN_TRIANGLES_PER_OBJECT:
            continue
        target = max(PRE_VOXEL_MIN_TRIANGLES_PER_OBJECT, int(count * ratio))
        if target >= count:
            continue
        modifier = obj.modifiers.new("CC Pre-Voxel Decimate", type="DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = max(0.001, min(1.0, target / count))
        modifier.use_collapse_triangulate = False
        apply_modifier(obj, modifier)
    reduced = sum(mesh_triangle_count(obj.data) for obj in work_objects)
    print(
        f"[CC SHELL] Pre-decimation complete: {total:,} -> "
        f"{reduced:,} triangles",
        flush=True,
    )
    return total, reduced


def apply_modifier(obj, modifier):
    select_only([obj], obj)
    result = bpy.ops.object.modifier_apply(modifier=modifier.name)
    if "FINISHED" not in result:
        raise RuntimeError(f"Failed to apply modifier '{modifier.name}'")


def mesh_bvh(mesh):
    """Build a local-space BVH without changing the mesh."""

    vertices = [vertex.co.copy() for vertex in mesh.vertices]
    polygons = [tuple(polygon.vertices) for polygon in mesh.polygons]
    return BVHTree.FromPolygons(vertices, polygons)


def capture_top_surface_samples(obj, reference_bounds):
    """Sample the raw evaluated vehicle's upper silhouette on an XY grid."""

    minimum, maximum = reference_bounds
    dimensions = bounds_dimensions(reference_bounds)
    ray_start_z = maximum.z + max(dimensions) * 0.1
    minimum_contact_z = (
        minimum.z + dimensions[2] * TOP_SURFACE_MIN_HEIGHT_FACTOR
    )
    tree = mesh_bvh(obj.data)
    samples = []
    x_span = 1.0 - 2.0 * TOP_SURFACE_X_INSET_FACTOR
    y_span = 1.0 - 2.0 * TOP_SURFACE_Y_INSET_FACTOR
    direction = Vector((0.0, 0.0, -1.0))
    for x_index in range(TOP_SURFACE_SAMPLES_X):
        x_factor = TOP_SURFACE_X_INSET_FACTOR + x_span * (
            x_index / (TOP_SURFACE_SAMPLES_X - 1)
        )
        x = minimum.x + dimensions[0] * x_factor
        for y_index in range(TOP_SURFACE_SAMPLES_Y):
            y_factor = TOP_SURFACE_Y_INSET_FACTOR + y_span * (
                y_index / (TOP_SURFACE_SAMPLES_Y - 1)
            )
            y = minimum.y + dimensions[1] * y_factor
            hit, _normal, _face_index, _distance = tree.ray_cast(
                Vector((x, y, ray_start_z)),
                direction,
            )
            if hit is not None and hit.z >= minimum_contact_z:
                samples.append((x, y, hit.z))
    return samples, ray_start_z


def measure_top_surface_damage(obj, samples, ray_start_z):
    """Report where a generated shell fell materially below the source."""

    tree = mesh_bvh(obj.data)
    direction = Vector((0.0, 0.0, -1.0))
    missing_samples = 0
    dropped_samples = 0
    maximum_drop_mm = 0.0
    for x, y, source_z in samples:
        hit, _normal, _face_index, _distance = tree.ray_cast(
            Vector((x, y, ray_start_z)),
            direction,
        )
        if hit is None:
            missing_samples += 1
            continue
        drop_mm = max(0.0, (source_z - hit.z) * 1000.0)
        maximum_drop_mm = max(maximum_drop_mm, drop_mm)
        if drop_mm > TOP_SURFACE_DROP_TOLERANCE_MM:
            dropped_samples += 1

    damaged_samples = missing_samples + dropped_samples
    sample_count = len(samples)
    damage_fraction = (
        damaged_samples / sample_count if sample_count else 0.0
    )
    return {
        "sample_count": sample_count,
        "missing_samples": missing_samples,
        "dropped_samples": dropped_samples,
        "damaged_samples": damaged_samples,
        "damage_fraction": damage_fraction,
        "maximum_drop_mm": maximum_drop_mm,
    }


def top_surface_is_damaged(report):
    return (
        report["sample_count"] >= MIN_TOP_SURFACE_SAMPLE_COUNT
        and report["damage_fraction"] > MAX_TOP_SURFACE_DAMAGE_FRACTION
    )


def apply_thin_surface_protection(obj):
    """Extrude surfaces inward so detached exterior panels survive remeshing."""

    modifier = obj.modifiers.new(
        "CC Thin Surface Protection",
        type="SOLIDIFY",
    )
    modifier.thickness = THIN_SURFACE_PROTECTION_MM / 1000.0
    # For consistently outward-facing vehicle panels, -1 keeps the original
    # exterior exactly in place and puts all temporary thickness inside the car.
    # This lets a thin hood join the engine/body volume without bulging upward.
    modifier.offset = -1.0
    modifier.use_even_offset = True
    modifier.use_quality_normals = True
    apply_modifier(obj, modifier)


def apply_voxel_remesh(obj, voxel_mm, modifier_name):
    """Union visible parts and retain only the principal watertight volume."""

    before = mesh_triangle_count(obj.data)
    print(
        f"[CC SHELL] Applying {modifier_name}: {before:,} triangles, "
        f"voxel={voxel_mm:g} mm...",
        flush=True,
    )
    modifier = obj.modifiers.new(modifier_name, type="REMESH")
    modifier.mode = "VOXEL"
    modifier.voxel_size = voxel_mm / 1000.0
    modifier.use_remove_disconnected = True
    modifier.threshold = 1.0
    modifier.use_smooth_shade = True
    apply_modifier(obj, modifier)
    if not obj.data.polygons:
        raise RuntimeError(
            f"{modifier_name} produced no faces; check that 1 BU = 1 m or "
            "reduce the voxel size"
        )
    print(
        f"[CC SHELL] {modifier_name} complete: "
        f"{mesh_triangle_count(obj.data):,} triangles",
        flush=True,
    )


def apply_laplacian_smooth(obj, iterations, factor, modifier_name):
    if iterations <= 0 or factor <= 0.0:
        return
    print(
        f"[CC SHELL] Applying {modifier_name}: iterations={iterations}, "
        f"factor={factor:g}...",
        flush=True,
    )
    modifier = obj.modifiers.new(modifier_name, type="LAPLACIANSMOOTH")
    modifier.lambda_factor = factor
    modifier.lambda_border = factor
    modifier.iterations = iterations
    modifier.use_normalized = True
    modifier.use_volume_preserve = True
    apply_modifier(obj, modifier)
    print(f"[CC SHELL] {modifier_name} complete", flush=True)


def decimate_to_target(obj, target, modifier_name):
    """Collapse a temporary mesh to an upper triangle target."""

    before = mesh_triangle_count(obj.data)
    if before <= target:
        return before, before
    print(
        f"[CC SHELL] Applying {modifier_name}: {before:,} -> "
        f"about {target:,} triangles...",
        flush=True,
    )
    modifier = obj.modifiers.new(modifier_name, type="DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.ratio = max(0.001, min(1.0, target / before))
    modifier.use_collapse_triangulate = False
    apply_modifier(obj, modifier)
    after = mesh_triangle_count(obj.data)
    print(
        f"[CC SHELL] {modifier_name} complete: {before:,} -> "
        f"{after:,} triangles",
        flush=True,
    )
    return before, after


def apply_decimation(obj):
    before = mesh_triangle_count(obj.data)
    if before <= TARGET_TRIANGLES:
        return before, before
    modifier = obj.modifiers.new("CC Shell Collision Decimate", type="DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.ratio = max(0.001, min(1.0, TARGET_TRIANGLES / before))
    modifier.use_collapse_triangulate = False
    apply_modifier(obj, modifier)
    after = mesh_triangle_count(obj.data)
    if after > MAX_TRIANGLES:
        raise RuntimeError(
            f"Collision shell has {after} triangles; maximum is "
            f"{MAX_TRIANGLES}"
        )
    return before, after


def compensate_voxel_surface_expansion(obj, voxel_mm):
    """Inset a remeshed surface to counter voxel-cell outward expansion."""

    distance = (
        voxel_mm * VOXEL_INWARD_COMPENSATION_FACTOR / 1000.0
    )
    if distance <= 0.0:
        return 0.0

    recalculate_normals(obj)
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.normal_update()
        for vertex in bm.verts:
            if vertex.normal.length_squared > 1.0e-12:
                vertex.co -= vertex.normal.normalized() * distance
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()
    return distance * 1000.0


def restore_reference_bounds(obj, reference_bounds):
    """Restore exact source AABB after remesh and volume-preserving smoothing."""

    current_bounds = mesh_bounds(obj.data)
    current_dimensions = bounds_dimensions(current_bounds)
    reference_dimensions = bounds_dimensions(reference_bounds)
    before_error_mm = max(
        abs(current_dimensions[axis] - reference_dimensions[axis]) * 1000.0
        for axis in range(3)
    )
    scales = [1.0, 1.0, 1.0]
    if PRESERVE_SOURCE_BOUNDS:
        current_minimum, current_maximum = current_bounds
        reference_minimum, reference_maximum = reference_bounds
        for axis in range(3):
            if current_dimensions[axis] <= 1.0e-12:
                raise RuntimeError("Generated shell has a zero-size axis")
            scales[axis] = reference_dimensions[axis] / current_dimensions[axis]
            current_center = (
                current_minimum[axis] + current_maximum[axis]
            ) * 0.5
            reference_center = (
                reference_minimum[axis] + reference_maximum[axis]
            ) * 0.5
            for vertex in obj.data.vertices:
                vertex.co[axis] = reference_center + (
                    vertex.co[axis] - current_center
                ) * scales[axis]
        obj.data.update()

    corrected_dimensions = bounds_dimensions(mesh_bounds(obj.data))
    after_error_mm = max(
        abs(corrected_dimensions[axis] - reference_dimensions[axis]) * 1000.0
        for axis in range(3)
    )
    if after_error_mm > MAX_BOUNDS_ERROR_MM:
        raise RuntimeError(
            f"Bounds error {after_error_mm:.3f} mm exceeds "
            f"MAX_BOUNDS_ERROR_MM={MAX_BOUNDS_ERROR_MM:g}"
        )
    return tuple(scales), before_error_mm, after_error_mm


def recalculate_normals(obj):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.validate(clean_customdata=False)
    obj.data.update()


def clean_low_poly_surface(obj):
    """Weld numerical duplicates and remove zero-area debris after decimation."""

    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        if bm.verts:
            bmesh.ops.remove_doubles(
                bm,
                verts=list(bm.verts),
                dist=1.0e-6,
            )
        if bm.edges:
            bmesh.ops.dissolve_degenerate(
                bm,
                edges=list(bm.edges),
                dist=1.0e-7,
            )
        bm.normal_update()
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.validate(clean_customdata=False)
    obj.data.update()


def keep_largest_surface_component(obj):
    """Discard detached detail islands while retaining the main vehicle shell."""

    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        remaining = set(bm.faces)
        components = []
        while remaining:
            seed = remaining.pop()
            component = {seed}
            stack = [seed]
            while stack:
                face = stack.pop()
                for edge in face.edges:
                    for neighbor in edge.link_faces:
                        if neighbor in remaining:
                            remaining.remove(neighbor)
                            component.add(neighbor)
                            stack.append(neighbor)
            components.append(component)

        if len(components) <= 1:
            return 0, 0
        largest = max(components, key=len)
        keep_vertices = {
            vertex for face in largest for vertex in face.verts
        }
        delete_vertices = [
            vertex for vertex in bm.verts if vertex not in keep_vertices
        ]
        removed_faces = len(bm.faces) - len(largest)
        bmesh.ops.delete(bm, geom=delete_vertices, context="VERTS")
        bm.to_mesh(obj.data)
        obj.data.update()
        return len(components) - 1, removed_faces
    finally:
        bm.free()


def build_stage_one_shell(obj, reference_bounds, protect_thin_surfaces):
    """Create, normalize, and validate one stage-one outer shell."""

    if protect_thin_surfaces:
        apply_thin_surface_protection(obj)
    apply_voxel_remesh(
        obj,
        OUTER_SHELL_VOXEL_MM,
        "CC Stage 1 Outer Shell Voxel Union",
    )
    decimate_to_target(
        obj,
        OUTER_SHELL_POST_VOXEL_MAX_TRIANGLES,
        "CC Stage 1 Post-Voxel Decimate",
    )
    apply_laplacian_smooth(
        obj,
        OUTER_SHELL_SMOOTH_ITERATIONS,
        OUTER_SHELL_SMOOTH_FACTOR,
        "CC Stage 1 Outer Shell Smooth",
    )
    print("[CC SHELL] Removing detached stage-1 islands...", flush=True)
    removed_islands, removed_island_faces = keep_largest_surface_component(obj)
    print(
        f"[CC SHELL] Island cleanup complete: removed "
        f"{removed_islands} component(s), {removed_island_faces:,} faces",
        flush=True,
    )
    print("[CC SHELL] Compensating voxel surface expansion...", flush=True)
    compensate_voxel_surface_expansion(obj, OUTER_SHELL_VOXEL_MM)
    print("[CC SHELL] Restoring source bounds...", flush=True)
    bounds_report = restore_reference_bounds(obj, reference_bounds)
    print("[CC SHELL] Recalculating stage-1 normals...", flush=True)
    recalculate_normals(obj)
    print("[CC SHELL] Running lightweight stage-1 checks...", flush=True)
    mesh_report = inspect_lightweight_mesh(obj, "Outer Shell")
    print(
        "[CC SHELL] Stage 1 lightweight checks complete",
        flush=True,
    )
    return (
        removed_islands,
        removed_island_faces,
        bounds_report,
        mesh_report,
    )


def inspect_lightweight_mesh(obj, stage_name, max_triangles=None):
    """Check essential mesh integrity without a full topology/volume audit."""

    mesh = obj.data
    triangles = mesh_triangle_count(mesh)
    problems = []
    if not mesh.vertices or not mesh.polygons or triangles <= 0:
        problems.append("mesh is empty")
    if max_triangles is not None and triangles > max_triangles:
        problems.append(f"triangles={triangles} exceeds {max_triangles}")
    if any(
        not all(math.isfinite(value) for value in vertex.co)
        for vertex in mesh.vertices
    ):
        problems.append("vertex coordinates contain NaN/Inf")
    if problems:
        raise RuntimeError(
            f"{stage_name} failed lightweight integrity checks: "
            + ", ".join(problems)
        )

    return {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.polygons),
        "triangles": triangles,
        # A largest-component cleanup immediately precedes each call.
        "surface_components": 1 if mesh.polygons else 0,
        "largest_component_faces": len(mesh.polygons),
        # These fields are intentionally not computed in lightweight mode.
        "boundary_edges": -1,
        "non_manifold_edges": -1,
        "loose_edges": -1,
        "loose_vertices": -1,
        "degenerate_faces": -1,
        "signed_volume": 0.0,
        "valid": True,
        "problems": [],
        "validation_mode": "lightweight",
    }


def replace_previous_generated(name, incoming):
    old_object = bpy.data.objects.get(name)
    if old_object is None or old_object is incoming:
        return
    if old_object.get(GENERATED_TAG, False) or old_object.get(
        OUTER_SHELL_TAG,
        False,
    ):
        remove_object_and_mesh(old_object)
    else:
        print(
            f"[CC SHELL WARNING] '{name}' is not script-generated; Blender "
            "will assign a unique suffix."
        )


def move_to_collection(obj, collection):
    if collection not in obj.users_collection:
        collection.objects.link(obj)
    for user_collection in list(obj.users_collection):
        if user_collection != collection:
            user_collection.objects.unlink(obj)


def link_sources_to_collection(sources, collection):
    """Add source vehicle objects beside their generated shells."""

    linked = 0
    for source in sources:
        if collection not in source.users_collection:
            collection.objects.link(source)
            linked += 1
    return linked


def remove_legacy_source_collisions(sources):
    """Undo Collision modifiers added to sources by older script versions."""

    removed = 0
    for source in sources:
        modifier = source.modifiers.get("CC Shell Cloth Collision")
        if modifier is not None and modifier.type == "COLLISION":
            source.modifiers.remove(modifier)
            removed += 1
        for key in (
            "collision_shell_collection",
            "collision_source_high_resolution",
            "collision_proxy_thickness_mm",
            "collision_proxy_friction",
        ):
            if key in source:
                del source[key]
    return removed


def finalize_outer_shell(obj, name, collection, sources, report, bounds_report):
    replace_previous_generated(name, obj)
    obj.name = name
    obj.data.name = f"{name} Mesh"
    obj[OUTER_SHELL_TAG] = True
    obj[GENERATED_TAG] = True
    if WORK_TAG in obj:
        del obj[WORK_TAG]
    obj["collision_shell_preset"] = PRESET_NAME
    obj["collision_shell_sources"] = ", ".join(source.name for source in sources)
    obj["collision_shell_collection"] = collection.name
    obj["collision_shell_stage"] = "OUTER_SHELL"
    obj["collision_shell_voxel_mm"] = OUTER_SHELL_VOXEL_MM
    obj["collision_shell_inward_compensation_mm"] = (
        OUTER_SHELL_VOXEL_MM * VOXEL_INWARD_COMPENSATION_FACTOR
    )
    store_report(obj, report, bounds_report)
    move_to_collection(obj, collection)
    obj.display_type = "WIRE"
    obj.show_in_front = SHOW_IN_FRONT
    obj.hide_render = HIDE_FROM_RENDER


def configure_collision(obj):
    modifier = next(
        (item for item in obj.modifiers if item.type == "COLLISION"),
        None,
    )
    if modifier is None:
        modifier = obj.modifiers.new("CC Shell Cloth Collision", type="COLLISION")
    settings = obj.collision
    settings.use = True
    settings.thickness_outer = COLLISION_THICKNESS_MM / 1000.0
    settings.cloth_friction = COLLISION_FRICTION
    if hasattr(settings, "use_culling"):
        settings.use_culling = COLLISION_USE_CULLING
    if hasattr(settings, "use_normal"):
        settings.use_normal = COLLISION_USE_NORMAL


def store_report(obj, report, bounds_report):
    for key, value in report.items():
        if key == "problems":
            obj[f"collision_shell_{key}"] = ", ".join(value)
        else:
            obj[f"collision_shell_{key}"] = value
    scales, before_error_mm, after_error_mm = bounds_report
    obj["collision_shell_bounds_scale_xyz"] = list(scales)
    obj["collision_shell_bounds_error_before_mm"] = before_error_mm
    obj["collision_shell_bounds_error_after_mm"] = after_error_mm


def store_top_surface_report(obj, repair_used, before_report, after_report):
    obj["collision_shell_thin_surface_repair_used"] = repair_used
    obj["collision_shell_thin_surface_repair_needed"] = (
        top_surface_is_damaged(before_report)
    )
    obj["collision_shell_thin_surface_protection_mm"] = (
        THIN_SURFACE_PROTECTION_MM if repair_used else 0.0
    )
    obj["collision_shell_top_probe_samples"] = before_report["sample_count"]
    for stage, report in (("before", before_report), ("after", after_report)):
        obj[f"collision_shell_top_damage_{stage}_samples"] = report[
            "damaged_samples"
        ]
        obj[f"collision_shell_top_damage_{stage}_fraction"] = report[
            "damage_fraction"
        ]
        obj[f"collision_shell_top_missing_{stage}_samples"] = report[
            "missing_samples"
        ]
        obj[f"collision_shell_top_max_drop_{stage}_mm"] = report[
            "maximum_drop_mm"
        ]


def finalize_collision(obj, name, collection, sources, report, bounds_report):
    replace_previous_generated(name, obj)
    obj.name = name
    obj.data.name = f"{name} Mesh"
    obj[GENERATED_TAG] = True
    obj[COLLISION_PROXY_TAG] = True
    if WORK_TAG in obj:
        del obj[WORK_TAG]
    obj["collision_proxy_preset"] = PRESET_NAME
    obj["collision_proxy_sources"] = ", ".join(source.name for source in sources)
    obj["collision_shell_collection"] = collection.name
    obj["collision_shell_stage"] = "COLLISION_FROM_OUTER_SHELL"
    obj["collision_shell_outer_voxel_mm"] = OUTER_SHELL_VOXEL_MM
    obj["collision_shell_collision_voxel_mm"] = COLLISION_VOXEL_MM
    obj["collision_proxy_thickness_mm"] = COLLISION_THICKNESS_MM
    obj["collision_proxy_friction"] = COLLISION_FRICTION
    obj["collision_shell_inward_compensation_mm"] = (
        COLLISION_VOXEL_MM * VOXEL_INWARD_COMPENSATION_FACTOR
    )
    store_report(obj, report, bounds_report)
    move_to_collection(obj, collection)
    obj.display_type = "WIRE"
    obj.show_in_front = SHOW_IN_FRONT
    obj.hide_render = HIDE_FROM_RENDER
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    configure_collision(obj)


def print_report(label, report, bounds_report):
    scales, before_error_mm, after_error_mm = bounds_report
    if report.get("validation_mode") == "lightweight":
        print(
            f"{label}: vertices={report['vertices']}, "
            f"faces={report['faces']}, triangles={report['triangles']}; "
            "lightweight integrity checks passed"
        )
    else:
        print(
            f"{label}: vertices={report['vertices']}, faces={report['faces']}, "
            f"triangles={report['triangles']}, "
            f"components={report['surface_components']}, "
            f"boundary={report['boundary_edges']}, "
            f"nonManifold={report['non_manifold_edges']}, "
            f"looseEdges={report['loose_edges']}, "
            f"volume={report['signed_volume']:.4f} m^3"
        )
    print(
        f"  bounds correction: before={before_error_mm:.3f} mm, "
        f"after={after_error_mm:.6f} mm, "
        f"scale=({scales[0]:.6f}, {scales[1]:.6f}, {scales[2]:.6f})"
    )


def main():
    if bpy.context.mode != "OBJECT":
        raise RuntimeError("Switch to Object Mode before running this script")

    validate_parameters()
    stale_count = cleanup_stale_work_objects()
    original_selection = list(bpy.context.selected_objects)
    original_active = bpy.context.view_layer.objects.active
    sources, skipped = selected_vehicle_sources()
    if not sources:
        raise RuntimeError(
            "Select one or more original vehicle Mesh objects; do not select "
            "cloth or an existing generated proxy"
        )
    removed_source_collisions = remove_legacy_source_collisions(sources)
    for name, reason in skipped:
        print(f"[CC SHELL] skipped {name}: {reason}")

    base_name = source_base_name(sources, original_active)
    outer_name = f"{base_name}{OUTER_SHELL_SUFFIX}"
    collision_name = f"{base_name}{COLLISION_SUFFIX}"
    # Keep the generated shells beside the logical target, in a collection
    # whose name matches the active source object (or the first valid source
    # when no selected source is active). The collection is organizational;
    # setup_cloth allows Collision objects from every scene collection.
    collection = ensure_collection(bpy.context.scene, base_name)
    work_objects = []
    outer_shell = None
    collision = None

    print("")
    print("=" * 72)
    print(f"GENERATE TWO-STAGE COLLISION SHELL: {PRESET_NAME}")
    print("=" * 72)
    print(f"Sources ({len(sources)}): {', '.join(obj.name for obj in sources)}")
    print(f"Target collection: {collection.name}")
    if stale_count:
        print(f"Removed {stale_count} stale work object(s)")

    try:
        print("[CC SHELL] Copying evaluated source geometry...", flush=True)
        work_objects = create_evaluated_work_objects(sources, collection)
        source_bounds = combined_bounds(work_objects)
        source_triangles = sum(
            mesh_triangle_count(work.data) for work in work_objects
        )
        validate_voxel_budget(source_bounds)
        predecimate_work_objects(work_objects)
        print("[CC SHELL] Joining temporary source copies...", flush=True)
        outer_shell = join_work_objects(work_objects)
        work_objects = [outer_shell]
        print("[CC SHELL] Sampling the upper silhouette...", flush=True)
        top_samples, top_ray_start_z = capture_top_surface_samples(
            outer_shell,
            source_bounds,
        )
        print(
            f"[CC SHELL] Captured {len(top_samples):,} top samples; "
            "building stage 1...",
            flush=True,
        )
        (
            removed_islands,
            removed_island_faces,
            outer_bounds_report,
            outer_report,
        ) = build_stage_one_shell(
            outer_shell,
            source_bounds,
            protect_thin_surfaces=False,
        )
        print("[CC SHELL] Comparing stage-1 upper silhouette...", flush=True)
        top_damage_before = measure_top_surface_damage(
            outer_shell,
            top_samples,
            top_ray_start_z,
        )
        repair_needed = top_surface_is_damaged(top_damage_before)
        repair_used = False
        top_damage_after = top_damage_before

        if repair_needed and not ENABLE_THIN_SURFACE_REPAIR:
            print(
                "[CC SHELL WARNING] Top-surface loss detected: "
                f"{top_damage_before['damaged_samples']}/"
                f"{top_damage_before['sample_count']} samples "
                f"({top_damage_before['damage_fraction']:.1%}). Fast mode "
                "will keep this shell for manual correction; set "
                "ENABLE_THIN_SURFACE_REPAIR=True for an automatic rebuild.",
                flush=True,
            )
        elif repair_needed:
            repair_used = True
            print(
                "[CC SHELL] Top-surface loss detected: "
                f"{top_damage_before['damaged_samples']}/"
                f"{top_damage_before['sample_count']} samples "
                f"({top_damage_before['damage_fraction']:.1%}); rebuilding "
                f"from a temporary {THIN_SURFACE_PROTECTION_MM:g} mm "
                "solidified copy"
            )
            remove_object_and_mesh(outer_shell)
            outer_shell = None
            work_objects = create_evaluated_work_objects(sources, collection)
            predecimate_work_objects(work_objects)
            outer_shell = join_work_objects(work_objects)
            work_objects = [outer_shell]
            (
                removed_islands,
                removed_island_faces,
                outer_bounds_report,
                outer_report,
            ) = build_stage_one_shell(
                outer_shell,
                source_bounds,
                protect_thin_surfaces=True,
            )
            top_damage_after = measure_top_surface_damage(
                outer_shell,
                top_samples,
                top_ray_start_z,
            )
            if (
                ENFORCE_TOP_SURFACE_ACCURACY
                and top_surface_is_damaged(top_damage_after)
            ):
                raise RuntimeError(
                    "Thin-surface repair could not preserve the source top "
                    "silhouette: "
                    f"{top_damage_after['damaged_samples']}/"
                    f"{top_damage_after['sample_count']} samples remain "
                    "damaged"
                )
            if top_surface_is_damaged(top_damage_after):
                print(
                    "[CC SHELL WARNING] Automatic repair left "
                    f"{top_damage_after['damaged_samples']}/"
                    f"{top_damage_after['sample_count']} damaged samples; "
                    "continuing for manual correction.",
                    flush=True,
                )

        print("[CC SHELL] Creating stage-2 collision copy...", flush=True)
        collision_mesh = outer_shell.data.copy()
        collision = bpy.data.objects.new(
            "CC_SHELL_COLLISION_WORK",
            collision_mesh,
        )
        collision[WORK_TAG] = True
        collection.objects.link(collision)
        apply_voxel_remesh(
            collision,
            COLLISION_VOXEL_MM,
            "CC Stage 2 Collision Extraction",
        )
        apply_laplacian_smooth(
            collision,
            COLLISION_SMOOTH_ITERATIONS,
            COLLISION_SMOOTH_FACTOR,
            "CC Stage 2 Collision Smooth",
        )
        collision_removed_islands, collision_removed_island_faces = (
            keep_largest_surface_component(collision)
        )
        pre_decimate, post_decimate = apply_decimation(collision)
        clean_low_poly_surface(collision)
        apply_laplacian_smooth(
            collision,
            POST_DECIMATE_SMOOTH_ITERATIONS,
            POST_DECIMATE_SMOOTH_FACTOR,
            "CC Stage 2 Post-Decimate Surface Repair",
        )
        compensate_voxel_surface_expansion(collision, COLLISION_VOXEL_MM)
        collision_bounds_report = restore_reference_bounds(
            collision,
            source_bounds,
        )
        recalculate_normals(collision)
        print("[CC SHELL] Running lightweight stage-2 checks...", flush=True)
        collision_report = inspect_lightweight_mesh(
            collision,
            "Collision Shell",
            max_triangles=MAX_TRIANGLES,
        )
        final_top_damage = measure_top_surface_damage(
            collision,
            top_samples,
            top_ray_start_z,
        )
        if (
            ENFORCE_TOP_SURFACE_ACCURACY
            and top_surface_is_damaged(final_top_damage)
        ):
            raise RuntimeError(
                "Collision Shell lost too much of the source top silhouette: "
                f"{final_top_damage['damaged_samples']}/"
                f"{final_top_damage['sample_count']} samples damaged; "
                "reduce COLLISION_VOXEL_MM or smoothing"
            )
        if top_surface_is_damaged(final_top_damage):
            print(
                "[CC SHELL WARNING] Final Collision Shell has "
                f"{final_top_damage['damaged_samples']}/"
                f"{final_top_damage['sample_count']} damaged top samples; "
                "continuing for manual correction.",
                flush=True,
            )
        print(
            "[CC SHELL] Stage 2 lightweight geometry and silhouette checks "
            "complete",
            flush=True,
        )

        finalize_outer_shell(
            outer_shell,
            outer_name,
            collection,
            sources,
            outer_report,
            outer_bounds_report,
        )
        outer_shell["collision_shell_removed_islands"] = removed_islands
        outer_shell["collision_shell_removed_island_faces"] = (
            removed_island_faces
        )
        store_top_surface_report(
            outer_shell,
            repair_used,
            top_damage_before,
            top_damage_after,
        )
        work_objects = []
        finalize_collision(
            collision,
            collision_name,
            collection,
            sources,
            collision_report,
            collision_bounds_report,
        )
        collision["collision_shell_removed_islands"] = (
            collision_removed_islands
        )
        collision["collision_shell_removed_island_faces"] = (
            collision_removed_island_faces
        )
        store_top_surface_report(
            collision,
            repair_used,
            top_damage_before,
            top_damage_after,
        )
        collision["collision_shell_final_top_damage_samples"] = (
            final_top_damage["damaged_samples"]
        )
        collision["collision_shell_final_top_damage_fraction"] = (
            final_top_damage["damage_fraction"]
        )
        collision["collision_shell_final_top_max_drop_mm"] = (
            final_top_damage["maximum_drop_mm"]
        )
        linked_source_count = link_sources_to_collection(sources, collection)

        if not KEEP_OUTER_SHELL:
            remove_object_and_mesh(outer_shell)
            outer_shell = None

        dimensions = bounds_dimensions(mesh_bounds(collision.data))
        print(f"Source triangles: {source_triangles}")
        print_report("Stage 1 Outer Shell", outer_report, outer_bounds_report)
        repair_status = (
            "ON"
            if repair_used
            else "OFF (manual review recommended)"
            if repair_needed
            else "not needed"
        )
        print(
            "  top-surface probe: "
            f"{top_damage_before['damaged_samples']}/"
            f"{top_damage_before['sample_count']} damaged before, "
            f"{top_damage_after['damaged_samples']}/"
            f"{top_damage_after['sample_count']} after; "
            f"thin-surface repair={repair_status}"
        )
        print(
            f"  removed detached islands={removed_islands}, "
            f"faces={removed_island_faces}"
        )
        print_report(
            "Stage 2 Collision",
            collision_report,
            collision_bounds_report,
        )
        print(
            "  final top-surface probe: "
            f"{final_top_damage['damaged_samples']}/"
            f"{final_top_damage['sample_count']} damaged, "
            f"max drop={final_top_damage['maximum_drop_mm']:.1f} mm"
        )
        print(
            f"  removed detached islands={collision_removed_islands}, "
            f"faces={collision_removed_island_faces}"
        )
        print(
            f"Decimation: {pre_decimate} -> {post_decimate} triangles; "
            f"target={TARGET_TRIANGLES}, max={MAX_TRIANGLES}"
        )
        print(
            "Final dimensions: "
            f"X={dimensions[0] * 1000.0:.1f} mm, "
            f"Y={dimensions[1] * 1000.0:.1f} mm, "
            f"Z={dimensions[2] * 1000.0:.1f} mm"
        )
        print(
            f"Collision: thickness={COLLISION_THICKNESS_MM:g} mm, "
            f"friction={COLLISION_FRICTION:g}, "
            f"doubleSided={not COLLISION_USE_CULLING}"
        )
        print(f"Outer Shell: {outer_name if outer_shell else 'not kept'}")
        print(f"Collision: {collision.name}")
        print(
            f"Target sources in collection: {len(sources)} "
            f"({linked_source_count} newly linked)"
        )
        print("High-resolution source colliders: disabled")
        if removed_source_collisions:
            print(
                "Removed legacy script-added Collision modifiers from "
                f"{removed_source_collisions} source object(s)"
            )
        print("Only the final Collision proxy participates in Cloth collision.")
        print("=" * 72)

        select_only([collision], collision)
        return outer_shell, collision
    except Exception:
        for work in list(work_objects):
            remove_object_and_mesh(work)
        if object_exists(collision) and collision.get(WORK_TAG, False):
            remove_object_and_mesh(collision)
        if object_exists(outer_shell) and outer_shell.get(WORK_TAG, False):
            remove_object_and_mesh(outer_shell)
        select_only(
            [obj for obj in original_selection if object_exists(obj)],
            original_active if object_exists(original_active) else None,
        )
        raise


if __name__ == "__main__":
    main()
