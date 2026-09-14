"""Standalone Blender exterior-envelope collider; run on selected vehicle meshes.

World Z is up. Millimetres respect scene.unit_settings.scale_length.
Only the nearest surface from each of six axial directions contributes. Fill
between opposing hits, close small gaps, and remesh this solid envelope, never
the original high-poly/interior topology. This intentionally bridges undercuts,
wheel wells and spaces under wings; it is a drape collider, not a fit reference.
Open bodywork can expose interior parts; details below the voxel size can vanish.
"""

import math
import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


VOXEL_SIZE_MM = 40.0
GAP_CLOSE_CELLS = 1
TARGET_TRIANGLES = 12000
MAX_GRID_CELLS = 2000000
MAX_SOURCE_TRIANGLES = 8000000
SMOOTH_ITERATIONS = 2
SMOOTH_FACTOR = 0.15
COLLISION_THICKNESS_MM = 1.0
GENERATED_TAG = "car_cover_generated_collision_proxy"
SUFFIX = " Exterior Collision"


def log(message):
    print(f"[CC EXTERIOR] {message}", flush=True)


def select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply(obj, modifier):
    select_only(obj)
    if "FINISHED" not in bpy.ops.object.modifier_apply(modifier=modifier.name):
        raise RuntimeError(f"Failed to apply {modifier.name}")


def source_trees(sources):
    """Evaluate one mesh at a time; no source decimation or normal dependency."""
    trees = []
    low = Vector((math.inf,) * 3)
    high = Vector((-math.inf,) * 3)
    total = 0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for source in sources:
        evaluated = source.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            if not mesh.loop_triangles:
                continue
            total += len(mesh.loop_triangles)
            if total > MAX_SOURCE_TRIANGLES:
                raise RuntimeError("Evaluated triangle budget exceeded; disable unnecessary subdivision.")
            points = [evaluated.matrix_world @ v.co for v in mesh.vertices]
            triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
            used = {index for tri in triangles for index in tri}
            for index in used:
                point = points[index]
                if not all(math.isfinite(value) for value in point):
                    raise RuntimeError(f"Non-finite geometry: {source.name}")
                for axis in range(3):
                    low[axis] = min(low[axis], point[axis])
                    high[axis] = max(high[axis], point[axis])
            trees.append(BVHTree.FromPolygons(points, triangles, all_triangles=True))
        finally:
            evaluated.to_mesh_clear()
    if not trees:
        raise RuntimeError("No evaluated faces in selection")
    log(f"BVH ready: {total:,} evaluated triangles in {len(trees)} meshes")
    return trees, low, high


def nearest_hit(trees, origin, direction, distance):
    nearest = None
    for tree in trees:
        point, _normal, _index, hit_distance = tree.ray_cast(origin, direction, distance)
        if point is not None and (nearest is None or hit_distance < nearest[0]):
            nearest = hit_distance, point
    return None if nearest is None else nearest[1]


def sample_envelope(trees, low, high, voxel):
    padding = GAP_CLOSE_CELLS + 3
    origin = low - Vector((padding * voxel,) * 3)
    shape = tuple(math.ceil((high[a] - low[a]) / voxel) + 2 * padding for a in range(3))
    if math.prod(shape) > MAX_GRID_CELLS:
        raise RuntimeError(f"Grid {shape} exceeds {MAX_GRID_CELLS:,} cells; check units or increase VOXEL_SIZE_MM")
    occupied = np.zeros(shape, dtype=bool)
    for axis in range(3):
        log(f"Sampling opposing exterior views on axis {axis + 1}/3; grid {shape}")
        transverse = [a for a in range(3) if a != axis]
        direction = Vector((0.0, 0.0, 0.0))
        direction[axis] = 1.0
        length = shape[axis] * voxel
        for i in range(shape[transverse[0]]):
            for j in range(shape[transverse[1]]):
                start = origin.copy()
                start[transverse[0]] += (i + 0.5) * voxel
                start[transverse[1]] += (j + 0.5) * voxel
                end = start + direction * length
                first = nearest_hit(trees, start, direction, length)
                last = nearest_hit(trees, end, -direction, length)
                if first is None or last is None:
                    continue
                lower, upper = sorted((first[axis], last[axis]))
                begin = max(0, math.floor((lower - origin[axis]) / voxel))
                finish = min(shape[axis] - 1, math.floor((upper - origin[axis]) / voxel))
                index = [slice(None)] * 3
                index[axis] = slice(begin, finish + 1)
                index[transverse[0]], index[transverse[1]] = i, j
                occupied[tuple(index)] = True
    if not occupied.any():
        raise RuntimeError("Exterior sampling is empty; reduce VOXEL_SIZE_MM")
    return occupied, origin


def close_gaps(grid, iterations):
    """Six-neighbour morphological closing; padding prevents wraparound."""
    result = grid.copy()
    for dilate in (True, False):
        for _ in range(iterations):
            previous = result
            result = previous.copy()
            for axis in range(3):
                for shift in (-1, 1):
                    neighbour = np.roll(previous, shift, axis=axis)
                    if dilate:
                        result |= neighbour
                    else:
                        result &= neighbour
            for axis in range(3):
                for side in (0, -1):
                    boundary = [slice(None)] * 3
                    boundary[axis] = side
                    result[tuple(boundary)] = False
    return result


def boundary_mesh(grid, origin, voxel):
    """Emit only exposed voxel faces, sharing integer-grid corner vertices."""
    vertices, faces, lookup = [], [], {}
    for axis in range(3):
        u, v = (axis + 1) % 3, (axis + 2) % 3
        for sign in (-1, 1):
            exposed = grid & ~np.roll(grid, -sign, axis=axis)
            for cell in np.argwhere(exposed):
                corners = []
                for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    corner = [int(x) for x in cell]
                    corner[axis] += int(sign > 0)
                    corner[u] += du
                    corner[v] += dv
                    key = tuple(corner)
                    if key not in lookup:
                        lookup[key] = len(vertices)
                        vertices.append(tuple(origin[a] + key[a] * voxel for a in range(3)))
                    corners.append(lookup[key])
                faces.append(corners if sign > 0 else corners[::-1])
    mesh = bpy.data.meshes.new("CC Exterior Envelope")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def retain_exterior_and_validate(mesh):
    """Drop enclosed cavity surfaces/islands and reject broken final topology."""
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        unseen = set(bm.verts)
        components = []
        while unseen:
            seed = unseen.pop()
            component, stack = {seed}, [seed]
            while stack:
                for edge in stack.pop().link_edges:
                    for vertex in edge.verts:
                        if vertex in unseen:
                            unseen.remove(vertex)
                            component.add(vertex)
                            stack.append(vertex)
            components.append(component)
        if not components or not bm.faces:
            raise RuntimeError("Empty exterior mesh")
        # Largest enclosed spatial volume selects the body, not a dense small part.
        def extent(component):
            return math.prod(max(v.co[a] for v in component) - min(v.co[a] for v in component) for a in range(3))
        keep = max(components, key=extent)
        remove = [v for v in bm.verts if v not in keep]
        bmesh.ops.delete(bm, geom=remove, context="VERTS")
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        if any(not edge.is_manifold for edge in bm.edges) or any(not v.is_manifold for v in bm.verts):
            raise RuntimeError("Exterior is not manifold; increase VOXEL_SIZE_MM or GAP_CLOSE_CELLS")
        if abs(bm.calc_volume(signed=True)) <= 1e-12:
            raise RuntimeError("Exterior has no enclosed volume")
        if bm.calc_volume(signed=True) < 0:
            bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()


def main():
    if bpy.context.mode != "OBJECT":
        raise RuntimeError("Switch to Object Mode and select the original vehicle meshes")
    if (not math.isfinite(VOXEL_SIZE_MM) or VOXEL_SIZE_MM <= 0
            or not isinstance(GAP_CLOSE_CELLS, int) or GAP_CLOSE_CELLS < 0
            or TARGET_TRIANGLES < 100 or MAX_GRID_CELLS < 1000
            or SMOOTH_ITERATIONS < 0 or not 0 <= SMOOTH_FACTOR <= 1
            or COLLISION_THICKNESS_MM <= 0):
        raise ValueError("Invalid exterior collision settings")
    selected = list(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    sources = [o for o in selected if o.type == "MESH" and o.visible_get()
               and not any(o.get(tag) for tag in (GENERATED_TAG, "car_cover_generated_collision_shell_test", "car_cover_generated_outer_shell_test"))
               and not any(m.type == "CLOTH" for m in o.modifiers)]
    if not sources:
        raise RuntimeError("Select visible original vehicle meshes, excluding cloth/proxies")
    scale = bpy.context.scene.unit_settings.scale_length
    voxel = VOXEL_SIZE_MM / (1000.0 * scale)
    obj = None
    try:
        trees, low, high = source_trees(sources)
        grid, origin = sample_envelope(trees, low, high, voxel)
        del trees
        log("Closing small gaps and extracting envelope boundary")
        grid = close_gaps(grid, GAP_CLOSE_CELLS)
        mesh = boundary_mesh(grid, origin, voxel)
        basis = active if active in sources else sources[0]
        obj = bpy.data.objects.new(basis.name + SUFFIX, mesh)
        bpy.context.scene.collection.objects.link(obj)
        log("Remeshing the envelope and removing enclosed/disconnected surfaces")
        modifier = obj.modifiers.new("Exterior envelope remesh", "REMESH")
        modifier.mode = "VOXEL"
        modifier.voxel_size = voxel
        modifier.use_smooth_shade = True
        apply(obj, modifier)
        retain_exterior_and_validate(obj.data)
        modifier = obj.modifiers.new("Exterior smooth", "SMOOTH")
        modifier.factor = SMOOTH_FACTOR
        modifier.iterations = SMOOTH_ITERATIONS
        apply(obj, modifier)
        obj.data.calc_loop_triangles()
        count = len(obj.data.loop_triangles)
        if count > TARGET_TRIANGLES:
            modifier = obj.modifiers.new("Exterior decimate", "DECIMATE")
            modifier.ratio = TARGET_TRIANGLES / count
            modifier.use_collapse_triangulate = True
            apply(obj, modifier)
        retain_exterior_and_validate(obj.data)
        if any(not math.isfinite(c) for v in obj.data.vertices for c in v.co):
            raise RuntimeError("Non-finite output geometry")
        obj.modifiers.new("CC Exterior Collision", "COLLISION")
        obj.collision.thickness_outer = COLLISION_THICKNESS_MM / (1000.0 * scale)
        obj.collision.cloth_friction = 3.0
        obj.collision.use_culling = False
        obj.collision.use_normal = True
        obj[GENERATED_TAG] = True
        obj["exterior_method"] = "six_direction_first_hit_envelope"
        obj["voxel_size_mm"] = VOXEL_SIZE_MM
        obj.hide_render = True
        obj.display_type = "WIRE"
        obj.show_in_front = True
        select_only(obj)
        obj.data.calc_loop_triangles()
        log(f"Created {obj.name}: {len(obj.data.loop_triangles):,} triangles; closed manifold exterior")
        if any(any(m.type == "COLLISION" for m in o.modifiers) for o in sources):
            log("Source Collision modifiers remain enabled: disable them before cloth simulation to use only this shell.")
        return obj
    except Exception:
        if obj is not None:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        bpy.ops.object.select_all(action="DESELECT")
        for source in selected:
            source.select_set(True)
        bpy.context.view_layer.objects.active = active
        raise


if __name__ == "__main__":
    main()
