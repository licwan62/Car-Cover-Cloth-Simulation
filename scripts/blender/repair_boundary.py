import bpy
import bmesh
from pathlib import Path
import sys
from mathutils import Vector


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from project_config import load_simulation_config

# ============================================================
# 设置：单位 mm
# ============================================================

WELD_DISTANCE_MM = 2.0       # 小于此距离：直接焊接
BRIDGE_GAP_MM = 20.0         # 小于此距离：允许补边闭合
DEGENERATE_MM = 0.05         # 删除超短边

REPAIR_CONFIG = load_simulation_config()["boundary_repair"]
WELD_DISTANCE_MM = float(REPAIR_CONFIG["weld_distance_mm"])
BRIDGE_GAP_MM = float(REPAIR_CONFIG["bridge_gap_mm"])
DEGENERATE_MM = float(REPAIR_CONFIG["degenerate_edge_mm"])

WELD_DISTANCE = WELD_DISTANCE_MM / 1000.0
BRIDGE_GAP = BRIDGE_GAP_MM / 1000.0
DEGENERATE = DEGENERATE_MM / 1000.0


# ============================================================
# 工具
# ============================================================

def adjacency_map(bm):
    adj = {}
    for v in bm.verts:
        adj[v] = [e.other_vert(v) for e in v.link_edges]
    return adj


def components(bm):
    adj = adjacency_map(bm)
    unseen = set(bm.verts)
    result = []

    while unseen:
        start = next(iter(unseen))
        stack = [start]
        comp = set()

        while stack:
            v = stack.pop()
            if v in comp:
                continue

            comp.add(v)
            unseen.discard(v)

            for n in adj[v]:
                if n not in comp:
                    stack.append(n)

        result.append(comp)

    return result


def endpoints_of_component(comp):
    result = []

    for v in comp:
        degree = sum(
            1 for e in v.link_edges
            if e.other_vert(v) in comp
        )

        if degree == 1:
            result.append(v)

    return result


def segment_intersection_2d(a, b, c, d, eps=1e-9):
    """
    XY 平面中 AB 与 CD 是否相交。
    返回交点 Vector((x,y)) 或 None。
    """

    r = b - a
    s = d - c

    cross_rs = r.x * s.y - r.y * s.x

    if abs(cross_rs) < eps:
        return None

    ca = c - a

    t = (ca.x * s.y - ca.y * s.x) / cross_rs
    u = (ca.x * r.y - ca.y * r.x) / cross_rs

    if -eps <= t <= 1.0 + eps and -eps <= u <= 1.0 + eps:
        return a + r * t

    return None


def terminal_neighbor(v):
    if len(v.link_edges) != 1:
        return None
    return v.link_edges[0].other_vert(v)


def trim_intersecting_endpoints(bm):
    """
    如果两个开放链的末端边互相交叉：
    把两个末端剪到交点并合并。
    """

    changed = False
    comps = components(bm)

    endpoint_data = []

    for ci, comp in enumerate(comps):
        for v in endpoints_of_component(comp):
            n = terminal_neighbor(v)
            if n:
                endpoint_data.append((ci, v, n))

    for i in range(len(endpoint_data)):
        ci, v1, n1 = endpoint_data[i]

        if not v1.is_valid or not n1.is_valid:
            continue

        for j in range(i + 1, len(endpoint_data)):
            cj, v2, n2 = endpoint_data[j]

            if ci == cj:
                continue

            if not v2.is_valid or not n2.is_valid:
                continue

            p = segment_intersection_2d(
                Vector((n1.co.x, n1.co.y)),
                Vector((v1.co.x, v1.co.y)),
                Vector((n2.co.x, n2.co.y)),
                Vector((v2.co.x, v2.co.y)),
            )

            if p is None:
                continue

            z = (v1.co.z + v2.co.z) * 0.5
            co = Vector((p.x, p.y, z))

            bmesh.ops.pointmerge(
                bm,
                verts=[v1, v2],
                merge_co=co
            )

            changed = True
            return changed

    return changed


def weld_near_endpoints(bm):
    """
    不同开放链端点距离很小时自动焊接。
    """

    comps = components(bm)

    best = None

    for i, comp_a in enumerate(comps):

        ends_a = endpoints_of_component(comp_a)

        for j in range(i + 1, len(comps)):

            comp_b = comps[j]
            ends_b = endpoints_of_component(comp_b)

            for a in ends_a:
                for b in ends_b:

                    d = (a.co - b.co).length

                    if d <= WELD_DISTANCE:
                        if best is None or d < best[0]:
                            best = (d, a, b)

    if best is None:
        return False

    _, a, b = best

    midpoint = (a.co + b.co) * 0.5

    bmesh.ops.pointmerge(
        bm,
        verts=[a, b],
        merge_co=midpoint
    )

    return True


def bridge_near_endpoints(bm):
    """
    两条不同开放链有小间隙时补一条 Boundary Edge。
    """

    comps = components(bm)

    best = None

    for i, comp_a in enumerate(comps):

        ends_a = endpoints_of_component(comp_a)

        for j in range(i + 1, len(comps)):

            comp_b = comps[j]
            ends_b = endpoints_of_component(comp_b)

            for a in ends_a:
                for b in ends_b:

                    d = (a.co - b.co).length

                    if d <= BRIDGE_GAP:
                        if best is None or d < best[0]:
                            best = (d, a, b)

    if best is None:
        return False

    _, a, b = best

    try:
        bm.edges.new((a, b))
        return True
    except ValueError:
        return False


def close_single_open_chain(bm):
    """
    所有 SVG 段已经连成一条链以后，
    如果只剩两个端点，则闭合最后缺口。
    """

    comps = components(bm)

    if len(comps) != 1:
        return False

    ends = endpoints_of_component(comps[0])

    if len(ends) != 2:
        return False

    a, b = ends
    d = (a.co - b.co).length

    if d <= WELD_DISTANCE:

        midpoint = (a.co + b.co) * 0.5

        bmesh.ops.pointmerge(
            bm,
            verts=[a, b],
            merge_co=midpoint
        )

        return True

    if d <= BRIDGE_GAP:

        try:
            bm.edges.new((a, b))
            return True
        except ValueError:
            pass

    return False


# ============================================================
# 主程序
# ============================================================

src = bpy.context.active_object

if src is None:
    raise RuntimeError("请先选中 SVG 转换后的版型 Mesh。")

if src.type != 'MESH':
    raise RuntimeError(
        "当前对象不是 Mesh。\n"
        "请先 Object → Convert → Mesh。"
    )

if any(abs(s - 1.0) > 1e-4 for s in src.scale):
    raise RuntimeError(
        "请先 Ctrl + A → Scale，确保 Scale = 1,1,1。"
    )


# ------------------------------------------------------------
# 复制，原对象不修改
# ------------------------------------------------------------

new_mesh = src.data.copy()

dst = src.copy()
dst.data = new_mesh
dst.name = src.name + "_CLOSED"

src.users_collection[0].objects.link(dst)


# ------------------------------------------------------------
# BMesh
# ------------------------------------------------------------

bm = bmesh.new()
bm.from_mesh(new_mesh)


# 如果已有 Face，只留下边界本身
if bm.faces:
    bmesh.ops.delete(
        bm,
        geom=list(bm.faces),
        context='FACES_ONLY'
    )


# 初始合并重复点
bmesh.ops.remove_doubles(
    bm,
    verts=list(bm.verts),
    dist=WELD_DISTANCE
)

# 删除退化几何
bmesh.ops.dissolve_degenerate(
    bm,
    edges=list(bm.edges),
    dist=DEGENERATE
)


# ============================================================
# 自动修复循环
# ============================================================

MAX_ITERATIONS = int(REPAIR_CONFIG["max_iterations"])

for iteration in range(MAX_ITERATIONS):

    changed = False

    # ① 末端边已经交叉：自动剪到交点
    if trim_intersecting_endpoints(bm):
        changed = True

    # ② 非常接近：焊接
    elif weld_near_endpoints(bm):
        changed = True

    # ③ 有小缺口：补 Boundary Edge
    elif bridge_near_endpoints(bm):
        changed = True

    # ④ 最后只剩一条开放链
    elif close_single_open_chain(bm):
        changed = True

    if not changed:
        break


# 最后清理一次
bmesh.ops.remove_doubles(
    bm,
    verts=list(bm.verts),
    dist=DEGENERATE
)

bmesh.ops.dissolve_degenerate(
    bm,
    edges=list(bm.edges),
    dist=DEGENERATE
)


# ============================================================
# 检查结果
# ============================================================

comps = components(bm)

total_endpoints = 0
branch_vertices = []

for comp in comps:

    ends = endpoints_of_component(comp)
    total_endpoints += len(ends)

    for v in comp:

        degree = len(v.link_edges)

        if degree > 2:
            branch_vertices.append(v)


closed = (
    len(comps) == 1
    and total_endpoints == 0
    and len(branch_vertices) == 0
)


bm.to_mesh(new_mesh)
bm.free()

new_mesh.update()


# ------------------------------------------------------------
# 选择结果：不用 bpy.ops，避免你上次 context 报错
# ------------------------------------------------------------

view_layer = bpy.context.view_layer

for ob in view_layer.objects:
    try:
        ob.select_set(False)
    except:
        pass

dst.select_set(True)
view_layer.objects.active = dst


# ============================================================
# 输出
# ============================================================

print("")
print("==========================================")
print("SVG Boundary 自动修复完成")
print("==========================================")
print("对象：", dst.name)
print("Components：", len(comps))
print("Remaining endpoints：", total_endpoints)
print("Branch vertices：", len(branch_vertices))

if closed:
    print("")
    print("✅ RESULT: 已形成单一闭合轮廓")
    dst["boundary_closed"] = True
else:
    print("")
    print("⚠ RESULT: 仍未完全闭合")
    print(
        f"当前只允许自动修复 ≤ {BRIDGE_GAP_MM:.1f} mm 的缺口。"
    )
    print("更大的缺口没有强行连接，以免改变真实版型。")
    dst["boundary_closed"] = False

print("==========================================")
