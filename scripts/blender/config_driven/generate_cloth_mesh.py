import bpy
import math
from pathlib import Path
import sys
from mathutils import Vector
from mathutils import geometry


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from project_config import load_simulation_config


# ============================================================
# USER SETTINGS
# ============================================================

TARGET_EDGE_MM = 50.0

# 多大的转角视为真实版型拐角。
# 拐角会被强制保留，避免圆角化/削角。
CORNER_ANGLE_DEG = 20.0

# 内部采样点距离版型边缘至少多少个网格尺寸。
# 越大越不容易产生细长三角形。
BOUNDARY_CLEARANCE_FACTOR = 0.28

# 平面容差
PLANAR_TOLERANCE_MM = 2.0

# CDT 数值容差
CDT_EPSILON = 1e-7


# config/simulation.json is authoritative. The declarations above document
# safe historical defaults and keep this script readable inside Blender.
MESH_CONFIG = load_simulation_config()["cloth_mesh"]
TARGET_EDGE_MM = float(MESH_CONFIG["target_edge_mm"])
CORNER_ANGLE_DEG = float(MESH_CONFIG["corner_angle_deg"])
BOUNDARY_CLEARANCE_FACTOR = float(MESH_CONFIG["boundary_clearance_factor"])
PLANAR_TOLERANCE_MM = float(MESH_CONFIG["planar_tolerance_mm"])
CDT_EPSILON = float(MESH_CONFIG["cdt_epsilon"])


# Blender 中按：
# 1 BU = 1 m
TARGET = TARGET_EDGE_MM / 1000.0
PLANAR_TOL = PLANAR_TOLERANCE_MM / 1000.0


# ============================================================
# HELPERS
# ============================================================

def polygon_area_2d(poly):
    area = 0.0
    n = len(poly)

    for i in range(n):
        p = poly[i]
        q = poly[(i + 1) % n]
        area += p.x * q.y - q.x * p.y

    return area * 0.5


def polyline_length(poly):
    total = 0.0
    n = len(poly)

    for i in range(n):
        total += (poly[(i + 1) % n] - poly[i]).length

    return total


def newell_normal(points):
    n = Vector((0.0, 0.0, 0.0))

    count = len(points)

    for i in range(count):
        p = points[i]
        q = points[(i + 1) % count]

        n.x += (p.y - q.y) * (p.z + q.z)
        n.y += (p.z - q.z) * (p.x + q.x)
        n.z += (p.x - q.x) * (p.y + q.y)

    if n.length < 1e-10:
        raise RuntimeError("无法计算版片平面法线。")

    n.normalize()
    return n


def find_boundary_loop(mesh):
    """
    从 Mesh 找最外层闭合 Boundary。
    有 Face 时：
        只使用仅连接 1 个面的边。
    没有 Face 时：
        使用所有边。
    """

    edge_face_count = {}

    for e in mesh.edges:
        key = tuple(sorted(e.vertices))
        edge_face_count[key] = 0

    for poly in mesh.polygons:
        verts = list(poly.vertices)

        for i in range(len(verts)):
            key = tuple(sorted((
                verts[i],
                verts[(i + 1) % len(verts)]
            )))

            edge_face_count[key] = edge_face_count.get(key, 0) + 1

    if len(mesh.polygons) > 0:
        boundary_edges = [
            key
            for key, count in edge_face_count.items()
            if count == 1
        ]
    else:
        boundary_edges = [
            tuple(e.vertices)
            for e in mesh.edges
        ]

    if not boundary_edges:
        raise RuntimeError("没有找到版型 Boundary Edge。")

    adjacency = {}

    for a, b in boundary_edges:
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)

    # 找所有闭合 component
    unvisited = set(adjacency.keys())
    loops = []

    while unvisited:

        seed = next(iter(unvisited))

        component = set()
        stack = [seed]

        while stack:
            v = stack.pop()

            if v in component:
                continue

            component.add(v)
            unvisited.discard(v)

            for nb in adjacency.get(v, []):
                if nb not in component:
                    stack.append(nb)

        # 闭合环要求每个点 degree = 2
        if not all(
            len([x for x in adjacency[v] if x in component]) == 2
            for v in component
        ):
            continue

        start = next(iter(component))
        loop = [start]

        prev = None
        current = start

        while True:

            neighbors = [
                n for n in adjacency[current]
                if n in component and n != prev
            ]

            if not neighbors:
                break

            nxt = neighbors[0]

            if nxt == start:
                break

            loop.append(nxt)

            prev = current
            current = nxt

            if len(loop) > len(component) + 5:
                break

        if len(loop) >= 3:
            loops.append(loop)

    if not loops:
        raise RuntimeError(
            "没有找到完整闭合边界。\n"
            "请先在 Edit Mode 执行：A → M → By Distance。"
        )

    # 如果存在多个 loop，选择周长最大的
    def loop_perimeter(loop):
        result = 0.0

        for i in range(len(loop)):
            p = mesh.vertices[loop[i]].co
            q = mesh.vertices[loop[(i + 1) % len(loop)]].co
            result += (q - p).length

        return result

    loops.sort(key=loop_perimeter, reverse=True)

    return loops[0]


def turning_angle(poly, i):

    n = len(poly)

    prev = poly[(i - 1) % n]
    cur = poly[i]
    nxt = poly[(i + 1) % n]

    a = cur - prev
    b = nxt - cur

    if a.length < 1e-9 or b.length < 1e-9:
        return 180.0

    a.normalize()
    b.normalize()

    d = max(-1.0, min(1.0, a.dot(b)))

    return math.degrees(math.acos(d))


def interpolate_polyline(points, distance):

    if distance <= 0:
        return points[0].copy()

    remain = distance

    for i in range(len(points) - 1):

        a = points[i]
        b = points[i + 1]

        seg = b - a
        length = seg.length

        if length < 1e-12:
            continue

        if remain <= length:
            return a + seg * (remain / length)

        remain -= length

    return points[-1].copy()


def resample_segment(points, spacing):
    """
    对一个开放 polyline 均匀重采样。
    保留起点，不包含终点。
    """

    total = 0.0

    for i in range(len(points) - 1):
        total += (points[i + 1] - points[i]).length

    if total < 1e-9:
        return [points[0].copy()]

    segments = max(1, math.ceil(total / spacing))

    real_spacing = total / segments

    result = []

    for i in range(segments):

        d = i * real_spacing
        result.append(interpolate_polyline(points, d))

    return result


def resample_closed_boundary(poly, spacing):

    n = len(poly)

    corners = []

    for i in range(n):

        angle = turning_angle(poly, i)

        if angle >= CORNER_ANGLE_DEG:
            corners.append(i)

    # 完全光滑轮廓时至少保留一个 anchor
    if not corners:
        corners = [0]

    result = []

    for ci in range(len(corners)):

        start = corners[ci]
        end = corners[(ci + 1) % len(corners)]

        path = [poly[start]]

        idx = start

        while True:

            idx = (idx + 1) % n

            path.append(poly[idx])

            if idx == end:
                break

        sampled = resample_segment(path, spacing)

        result.extend(sampled)

    # 去掉可能出现的重复点
    cleaned = []

    for p in result:

        if not cleaned:
            cleaned.append(p)
        elif (p - cleaned[-1]).length > spacing * 0.05:
            cleaned.append(p)

    if len(cleaned) >= 2:
        if (cleaned[0] - cleaned[-1]).length < spacing * 0.05:
            cleaned.pop()

    return cleaned


def point_inside_polygon(p, poly):

    inside = False
    j = len(poly) - 1

    for i in range(len(poly)):

        pi = poly[i]
        pj = poly[j]

        intersects = (
            ((pi.y > p.y) != (pj.y > p.y))
            and
            (
                p.x <
                (pj.x - pi.x)
                * (p.y - pi.y)
                / ((pj.y - pi.y) + 1e-30)
                + pi.x
            )
        )

        if intersects:
            inside = not inside

        j = i

    return inside


def point_segment_distance(p, a, b):

    ab = b - a

    denom = ab.length_squared

    if denom < 1e-16:
        return (p - a).length

    t = (p - a).dot(ab) / denom
    t = max(0.0, min(1.0, t))

    nearest = a + ab * t

    return (p - nearest).length


def distance_to_boundary(p, boundary):

    minimum = 1e30

    for i in range(len(boundary)):

        a = boundary[i]
        b = boundary[(i + 1) % len(boundary)]

        d = point_segment_distance(p, a, b)

        if d < minimum:
            minimum = d

    return minimum


# ============================================================
# MAIN
# ============================================================

obj = bpy.context.active_object

if obj is None:
    raise RuntimeError("请先选中一块车罩版片。")

if obj.type != 'MESH':
    raise RuntimeError(
        "当前对象不是 Mesh。\n"
        "请先 Object → Convert → Mesh。"
    )


# Scale 检查
sx, sy, sz = obj.scale

if (
    abs(sx - 1.0) > 1e-4
    or abs(sy - 1.0) > 1e-4
    or abs(sz - 1.0) > 1e-4
):
    raise RuntimeError(
        "请先对版片执行：\n"
        "Ctrl + A → Scale\n"
        "确保 Scale = 1,1,1"
    )


mesh = obj.data

boundary_indices = find_boundary_loop(mesh)

boundary_3d = [
    mesh.vertices[i].co.copy()
    for i in boundary_indices
]


# ============================================================
# 建立版片二维坐标系
# ============================================================

normal = newell_normal(boundary_3d)

origin = boundary_3d[0].copy()


# 找最长边作为 U 轴，数值更稳定
longest = None
longest_len = 0.0

for i in range(len(boundary_3d)):

    a = boundary_3d[i]
    b = boundary_3d[(i + 1) % len(boundary_3d)]

    d = b - a

    if d.length > longest_len:
        longest = d
        longest_len = d.length

if longest is None or longest.length < 1e-9:
    raise RuntimeError("版片边界无有效长度。")

u_axis = longest.normalized()

# 去掉可能存在的法线方向分量
u_axis = (
    u_axis
    - normal * u_axis.dot(normal)
).normalized()

v_axis = normal.cross(u_axis).normalized()


def project_2d(p):

    d = p - origin

    return Vector((
        d.dot(u_axis),
        d.dot(v_axis)
    ))


def reconstruct_3d(p):

    return (
        origin
        + u_axis * p.x
        + v_axis * p.y
    )


boundary_2d_raw = [
    project_2d(p)
    for p in boundary_3d
]


# 检查平面程度
max_plane_error = 0.0

for p in boundary_3d:

    error = abs((p - origin).dot(normal))

    max_plane_error = max(
        max_plane_error,
        error
    )

if max_plane_error > PLANAR_TOL:
    raise RuntimeError(
        f"版片不是足够平的二维 Mesh。\n"
        f"最大平面误差：{max_plane_error * 1000:.2f} mm"
    )


# 保证 CCW
if polygon_area_2d(boundary_2d_raw) < 0:
    boundary_2d_raw.reverse()


# ============================================================
# 重采样 Boundary
# ============================================================

boundary = resample_closed_boundary(
    boundary_2d_raw,
    TARGET
)

if polygon_area_2d(boundary) < 0:
    boundary.reverse()

boundary_count = len(boundary)


# ============================================================
# 生成内部六角形采样点
# ============================================================

min_x = min(p.x for p in boundary)
max_x = max(p.x for p in boundary)

min_y = min(p.y for p in boundary)
max_y = max(p.y for p in boundary)


dx = TARGET
dy = TARGET * math.sqrt(3.0) / 2.0

clearance = TARGET * BOUNDARY_CLEARANCE_FACTOR

interior = []

row = 0
y = min_y + dy * 0.5

while y < max_y:

    offset = 0.5 * dx if row % 2 else 0.0

    x = min_x + dx * 0.5 + offset

    while x < max_x:

        p = Vector((x, y))

        if point_inside_polygon(p, boundary):

            if distance_to_boundary(p, boundary) >= clearance:
                interior.append(p)

        x += dx

    y += dy
    row += 1


print(
    "Boundary vertices:",
    boundary_count
)

print(
    "Interior samples:",
    len(interior)
)


# ============================================================
# Constrained Delaunay Triangulation
# ============================================================

input_vertices = boundary + interior

constraint_edges = [
    (i, (i + 1) % boundary_count)
    for i in range(boundary_count)
]

constraint_face = [
    list(range(boundary_count))
]


result = geometry.delaunay_2d_cdt(
    input_vertices,
    constraint_edges,
    constraint_face,

    # output_type = 1
    # triangles inside constraints
    1,

    CDT_EPSILON,

    True
)

(
    out_vertices,
    out_edges,
    out_faces,
    orig_verts,
    orig_edges,
    orig_faces
) = result


if not out_faces:
    raise RuntimeError(
        "Delaunay 没有生成任何面。\n"
        "请检查版型是否自交。"
    )


# ============================================================
# 建立新的 Cloth Mesh
# ============================================================

verts_3d = [
    reconstruct_3d(p)
    for p in out_vertices
]


new_mesh = bpy.data.meshes.new(
    obj.name + "_CLOTH_MESH"
)

new_mesh.from_pydata(
    verts_3d,
    [],
    out_faces
)

new_mesh.update()


name_mm = int(round(TARGET_EDGE_MM))

new_obj = bpy.data.objects.new(
    f"{obj.name}_CLOTH_{name_mm}mm",
    new_mesh
)

obj.users_collection[0].objects.link(new_obj)

new_obj.matrix_world = obj.matrix_world.copy()


# ============================================================
# 创建 Boundary Vertex Group
# ============================================================

boundary_output_indices = []

for output_index, source_ids in enumerate(orig_verts):

    if any(
        source_id < boundary_count
        for source_id in source_ids
    ):
        boundary_output_indices.append(output_index)


vg = new_obj.vertex_groups.new(
    name="CLOTH_BOUNDARY"
)

if boundary_output_indices:

    vg.add(
        boundary_output_indices,
        1.0,
        'REPLACE'
    )


# ============================================================
# 保存参数
# ============================================================

new_obj["cloth_target_edge_mm"] = TARGET_EDGE_MM
new_obj["cloth_boundary_vertices"] = len(boundary_output_indices)


# ============================================================
# 选择生成结果
# ============================================================

bpy.ops.object.select_all(
    action='DESELECT'
)

new_obj.select_set(True)

bpy.context.view_layer.objects.active = new_obj


print("")
print("===================================")
print("车罩 Cloth Mesh 创建完成")
print("===================================")
print(
    "Object:",
    new_obj.name
)
print(
    "Vertices:",
    len(new_mesh.vertices)
)
print(
    "Faces:",
    len(new_mesh.polygons)
)
print(
    "Target:",
    TARGET_EDGE_MM,
    "mm"
)
print("===================================")
