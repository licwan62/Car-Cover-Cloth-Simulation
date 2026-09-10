import bpy
import bmesh
import bisect
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from project_config import load_simulation_config
from seam_naming import (
    endpoint_marker_names,
    pair_seam_paths,
    parse_seam_name,
    validate_direction_markers,
)


# ============================================================
# SEAM 配对
# ============================================================

SEWING_CONFIG = load_simulation_config()["sewing"]
LEGACY_SEAM_PAIRS = [tuple(pair) for pair in SEWING_CONFIG["legacy_pairs"]]


# ============================================================
# 设置
# ============================================================

# 重跑脚本时：
# 自动删除原有 Loose Edge / Sewing Spring
DELETE_EXISTING_LOOSE_EDGES = bool(
    SEWING_CONFIG["delete_existing_loose_edges"]
)

# 自动把误选顶点从 Vertex Group 中移除
CLEAN_VERTEX_GROUPS = bool(SEWING_CONFIG["clean_vertex_groups"])

# 小于这个长度的独立边段直接视作误选
MIN_SEGMENT_LENGTH_MM = float(SEWING_CONFIG["minimum_segment_length_mm"])

MIN_SEGMENT_LENGTH = (
    MIN_SEGMENT_LENGTH_MM / 1000.0
)

# A boundary corner may legitimately participate in two seams. Three or more
# sewing connectors on one vertex create a many-to-one convergence point and
# are rejected before any new loose edges are written.
MAX_SEWING_CONNECTORS_PER_VERTEX = 2


# ============================================================
# 当前对象
# ============================================================

obj = bpy.context.active_object

if obj is None or obj.type != 'MESH':
    raise RuntimeError(
        "请先选中 Ctrl+J 后的 Cloth Mesh 对象。"
    )

if obj.mode != 'OBJECT':
    raise RuntimeError(
        "请先切换到 Object Mode。"
    )

mesh = obj.data
mw = obj.matrix_world


# New projects derive pairs solely from the Sewing ID. Legacy names are used
# only when no semantic pair exists and compatibility is explicitly enabled.
vertex_group_names = [group.name for group in obj.vertex_groups]
SEAM_PAIRS = pair_seam_paths(vertex_group_names)

if SEAM_PAIRS:
    direction_errors = validate_direction_markers(vertex_group_names)
    if direction_errors:
        raise RuntimeError(
            "语义 Sewing Group 缺少 A/B 方向标记：\n"
            + "\n".join(direction_errors)
        )
    print(f"[Preflight] semantic Sewing pairs: {len(SEAM_PAIRS)}")
elif SEWING_CONFIG["allow_legacy_pairs"]:
    SEAM_PAIRS = LEGACY_SEAM_PAIRS
    print("[Preflight] using configured legacy Sewing pairs")
else:
    raise RuntimeError(
        "没有找到 S001_PANEL 形式的语义 Sewing Group，且旧命名兼容已关闭。"
    )


# ============================================================
# 基础函数
# ============================================================

def world_co(i):
    return mw @ mesh.vertices[i].co


def path_length(path):

    return sum(
        (
            world_co(path[i])
            -
            world_co(path[i - 1])
        ).length

        for i in range(1, len(path))
    )


# ============================================================
# 删除旧 Loose Edge
# ============================================================

def delete_loose_edges():

    bm = bmesh.new()
    bm.from_mesh(mesh)

    loose = [
        e for e in bm.edges
        if len(e.link_faces) == 0
    ]

    count = len(loose)

    if loose:

        bmesh.ops.delete(
            bm,
            geom=loose,
            context='EDGES'
        )

        bm.to_mesh(mesh)
        mesh.update()

    bm.free()

    return count


if DELETE_EXISTING_LOOSE_EDGES:

    removed_loose = delete_loose_edges()

    print(
        f"[Preflight] "
        f"removed old/stray loose edges: "
        f"{removed_loose}"
    )


# ============================================================
# Edge 使用 Face 数
# ============================================================

def build_edge_face_count():

    counts = {
        tuple(sorted(e.vertices)): 0
        for e in mesh.edges
    }

    for p in mesh.polygons:

        vs = list(p.vertices)

        for i in range(len(vs)):

            key = tuple(sorted((
                vs[i],
                vs[(i + 1) % len(vs)]
            )))

            counts[key] = (
                counts.get(key, 0) + 1
            )

    return counts


edge_face_count = build_edge_face_count()


# ============================================================
# 获取 Vertex Group 顶点
# ============================================================

def group_vertex_set(name):

    vg = obj.vertex_groups.get(name)

    if vg is None:
        raise RuntimeError(
            f"找不到 Vertex Group：{name}"
        )

    gi = vg.index
    out = set()

    for v in mesh.vertices:

        for g in v.groups:

            if (
                g.group == gi
                and g.weight > 0.001
            ):
                out.add(v.index)
                break

    if not out:
        raise RuntimeError(
            f"{name} 是空的。"
        )

    return out


def marker_world_center(name):
    """Return a marker group's world-space centroid."""

    indices = group_vertex_set(name)
    center = sum((world_co(index) for index in indices), world_co(next(iter(indices))) * 0.0)
    return center / len(indices)


def orient_path_by_markers(path, path_name):
    """Orient a semantic path from its explicit A marker toward B."""

    marker_a_name, marker_b_name = endpoint_marker_names(path_name)
    marker_a = marker_world_center(marker_a_name)
    marker_b = marker_world_center(marker_b_name)

    forward = (
        (world_co(path[0]) - marker_a).length
        + (world_co(path[-1]) - marker_b).length
    )
    reverse = (
        (world_co(path[-1]) - marker_a).length
        + (world_co(path[0]) - marker_b).length
    )
    return list(path) if forward <= reverse else list(reversed(path))


# ============================================================
# 从一个乱选的 Group 中提取所有连续 Boundary 段
# ============================================================

def extract_candidates(name):

    group_verts = group_vertex_set(name)

    # --------------------------------------------------------
    # 只认可真正 Cloth Boundary
    #
    # Face Count = 1
    # --------------------------------------------------------

    adj = {}

    for e in mesh.edges:

        a, b = e.vertices

        if (
            a not in group_verts
            or
            b not in group_verts
        ):
            continue

        key = tuple(sorted((a, b)))

        if edge_face_count.get(key, 0) != 1:
            continue

        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)


    active = set(adj.keys())

    # Group 中那些内部点 / 孤点
    ignored_points = len(
        group_verts - active
    )


    if len(active) < 2:

        raise RuntimeError(
            f"{name} 没有形成可用的 "
            f"Cloth Boundary Edge。"
        )


    # ========================================================
    # Connected Components
    # ========================================================

    unseen = set(active)
    components = []

    while unseen:

        seed = next(iter(unseen))

        stack = [seed]
        comp = set()

        while stack:

            v = stack.pop()

            if v in comp:
                continue

            comp.add(v)
            unseen.discard(v)

            for nb in adj.get(v, []):

                if nb not in comp:
                    stack.append(nb)

        components.append(comp)


    candidates = []
    closed_components = 0


    # ========================================================
    # 每个 Component 拆成简单连续 Path
    # ========================================================

    for comp_id, comp in enumerate(components):

        deg = {
            v: len([
                n for n in adj[v]
                if n in comp
            ])
            for v in comp
        }


        # ----------------------------------------------------
        # 整圈被选中
        # ----------------------------------------------------

        if all(
            d == 2
            for d in deg.values()
        ):

            closed_components += 1
            continue


        # ----------------------------------------------------
        # degree != 2：
        #
        # endpoint
        # branch
        #
        # 都作为拆分点
        # ----------------------------------------------------

        terminals = {
            v
            for v, d in deg.items()
            if d != 2
        }

        visited = set()


        for start in terminals:

            for nb in adj[start]:

                if nb not in comp:
                    continue

                edge_key = tuple(
                    sorted((start, nb))
                )

                if edge_key in visited:
                    continue


                path = [start]

                prev = start
                cur = nb

                visited.add(edge_key)

                safety = 0


                while True:

                    path.append(cur)


                    # 到达下一个 endpoint / branch
                    if (
                        cur in terminals
                        and cur != start
                    ):
                        break


                    nexts = []

                    for nxt in adj[cur]:

                        if (
                            nxt == prev
                            or
                            nxt not in comp
                        ):
                            continue

                        k = tuple(
                            sorted((cur, nxt))
                        )

                        if k not in visited:
                            nexts.append(nxt)


                    if not nexts:
                        break


                    nxt = nexts[0]

                    visited.add(
                        tuple(
                            sorted((cur, nxt))
                        )
                    )

                    prev, cur = cur, nxt


                    safety += 1

                    if safety > len(comp) + 5:
                        break


                # ------------------------------------------------
                # 有效 Path
                # ------------------------------------------------

                if len(path) >= 2:

                    L = path_length(path)

                    if L >= MIN_SEGMENT_LENGTH:

                        candidates.append({
                            "path": path,
                            "length": L,
                            "component": comp_id,
                        })


    if not candidates:

        if closed_components:

            raise RuntimeError(
                f"{name} 只检测到完整闭合环。\n"
                "脚本无法判断整圈中的哪一段"
                "才是真正 Seam。\n"
                "这种情况下至少需要大致选择"
                "正确区域。"
            )

        raise RuntimeError(
            f"{name} 没有找到长度 >= "
            f"{MIN_SEGMENT_LENGTH_MM:.1f} mm "
            f"的连续边段。"
        )


    return (
        candidates,
        len(group_verts),
        ignored_points,
        closed_components
    )


# ============================================================
# 判断 SAME / REVERSE
# ============================================================

def endpoint_pairing(ca, cb):

    pa = ca["path"]
    pb = cb["path"]

    a0 = world_co(pa[0])
    a1 = world_co(pa[-1])

    b0 = world_co(pb[0])
    b1 = world_co(pb[-1])


    same = (
        (a0 - b0).length
        +
        (a1 - b1).length
    )


    rev = (
        (a0 - b1).length
        +
        (a1 - b0).length
    )


    if rev < same:

        return (
            list(reversed(pb)),
            rev,
            "REVERSE"
        )

    return (
        list(pb),
        same,
        "SAME"
    )


# ============================================================
# 自动从多个 Segment 中选最佳配对
# ============================================================

def choose_best_pair(
    name_a,
    name_b
):

    (
        ca_list,
        total_a,
        ignored_a,
        closed_a

    ) = extract_candidates(name_a)


    (
        cb_list,
        total_b,
        ignored_b,
        closed_b

    ) = extract_candidates(name_b)


    max_a = max(
        c["length"]
        for c in ca_list
    )

    max_b = max(
        c["length"]
        for c in cb_list
    )


    best = None


    for ca in ca_list:

        for cb in cb_list:


            (
                oriented_b,
                end_dist,
                direction

            ) = endpoint_pairing(
                ca,
                cb
            )


            la = ca["length"]
            lb = cb["length"]


            avg = max(
                (la + lb) * 0.5,
                1e-9
            )


            # ------------------------------------------------
            # 两条边长度差
            # ------------------------------------------------

            length_diff = (
                abs(la - lb)
                /
                max(la, lb)
            )


            # ------------------------------------------------
            # Endpoint 距离归一化
            # ------------------------------------------------

            endpoint_norm = (
                end_dist / avg
            )


            # ------------------------------------------------
            # 更倾向于长 Segment
            #
            # 防止选中旁边一小截恰好很近的误选边
            # ------------------------------------------------

            size_bonus = min(
                la / max_a
                if max_a else 0,

                lb / max_b
                if max_b else 0
            )


            # ------------------------------------------------
            # 综合评分
            #
            # 越低越好
            # ------------------------------------------------

            score = (
                endpoint_norm
                +
                3.0 * length_diff
                -
                0.75 * size_bonus
            )


            item = {

                "score": score,

                "path_a": ca["path"],
                "path_b": oriented_b,

                "len_a": la,
                "len_b": lb,

                "direction": direction,

                "total_a": total_a,
                "total_b": total_b,

                "ignored_a": ignored_a,
                "ignored_b": ignored_b,

                "count_a": len(ca_list),
                "count_b": len(cb_list),

                "closed_a": closed_a,
                "closed_b": closed_b,
            }


            if (
                best is None
                or
                score < best["score"]
            ):
                best = item


    # Semantic seams use Illustrator A/B markers as the authority. Spatial
    # endpoint comparison remains only for explicitly configured legacy data.
    if parse_seam_name(name_a) and parse_seam_name(name_b):
        best["path_a"] = orient_path_by_markers(best["path_a"], name_a)
        best["path_b"] = orient_path_by_markers(best["path_b"], name_b)
        best["direction"] = "MARK_A_TO_B"

    return best


# ============================================================
# 自动清理 Vertex Group
# ============================================================

def clean_vertex_group(
    name,
    keep_path
):

    vg = obj.vertex_groups.get(name)

    old = list(
        group_vertex_set(name)
    )

    keep = list(
        dict.fromkeys(keep_path)
    )


    if CLEAN_VERTEX_GROUPS:

        if old:
            vg.remove(old)

        vg.add(
            keep,
            1.0,
            'REPLACE'
        )


    return (
        len(old),
        len(keep)
    )


# ============================================================
# Path 累计弧长
# ============================================================

def cumulative_t(path):

    acc = [0.0]

    total = 0.0


    for i in range(1, len(path)):

        total += (
            world_co(path[i])
            -
            world_co(path[i - 1])
        ).length

        acc.append(total)


    if total <= 1e-12:

        raise RuntimeError(
            "Seam 长度为 0。"
        )


    return [
        x / total
        for x in acc
    ]


# ============================================================
# 按弧长均匀选择 K 个顶点
# ============================================================

def choose_k_vertices(
    path,
    k
):

    if k >= len(path):
        return list(path)


    ts = cumulative_t(path)

    n = len(path)

    out = []

    prev_idx = -1


    for j in range(k):


        if j == 0:

            idx = 0


        elif j == k - 1:

            idx = n - 1


        else:

            target = (
                j / (k - 1)
            )


            pos = bisect.bisect_left(
                ts,
                target
            )


            min_i = (
                prev_idx + 1
            )


            remaining = (
                (k - 1) - j
            )


            max_i = (
                n - 1 - remaining
            )


            cand = []


            if 0 <= pos < n:
                cand.append(pos)


            if 0 <= pos - 1 < n:
                cand.append(pos - 1)


            cand = [
                i
                for i in cand
                if min_i <= i <= max_i
            ]


            if cand:

                idx = min(
                    cand,
                    key=lambda i:
                    abs(
                        ts[i] - target
                    )
                )

            else:

                idx = max(
                    min_i,
                    min(
                        max_i,
                        pos
                    )
                )


        out.append(
            path[idx]
        )

        prev_idx = idx


    return out


# ============================================================
# 开始自动匹配
# ============================================================

spring_pairs = []


print("")
print("========================================")
print("ROBUST AUTO SEWING")
print("========================================")


for (
    name_a,
    name_b

) in SEAM_PAIRS:


    best = choose_best_pair(
        name_a,
        name_b
    )

    length_difference_ratio = (
        abs(best["len_a"] - best["len_b"])
        / max(best["len_a"], best["len_b"])
    )
    reject_ratio = float(SEWING_CONFIG["length_difference_reject_ratio"])
    warning_ratio = float(SEWING_CONFIG["length_difference_warning_ratio"])

    if length_difference_ratio > reject_ratio:
        raise RuntimeError(
            f"{name_a} <-> {name_b} 缝边长度差 "
            f"{length_difference_ratio:.1%}，超过拒绝阈值 {reject_ratio:.1%}。"
        )
    if length_difference_ratio > warning_ratio:
        print(
            f"[Warning] {name_a} <-> {name_b} 缝边长度差 "
            f"{length_difference_ratio:.1%}。"
        )


    old_a, new_a = (
        clean_vertex_group(
            name_a,
            best["path_a"]
        )
    )


    old_b, new_b = (
        clean_vertex_group(
            name_b,
            best["path_b"]
        )
    )


    print("")
    print(
        f"{name_a}"
        f"  <->  "
        f"{name_b}"
    )


    print(
        f"  candidate segments: "
        f"{best['count_a']} "
        f"<-> "
        f"{best['count_b']}"
    )


    print(
        f"  chosen vertices: "
        f"{new_a} "
        f"<-> "
        f"{new_b}"
    )


    print(
        f"  removed bad group verts: "
        f"{old_a - new_a} "
        f"<-> "
        f"{old_b - new_b}"
    )


    print(
        f"  ignored inner/isolated points: "
        f"{best['ignored_a']} "
        f"<-> "
        f"{best['ignored_b']}"
    )


    print(
        f"  length: "
        f"{best['len_a'] * 1000:.1f} mm "
        f"<-> "
        f"{best['len_b'] * 1000:.1f} mm"
    )


    print(
        f"  direction: "
        f"{best['direction']}"
    )


    print(
        f"  score: "
        f"{best['score']:.4f}"
    )


    # ========================================================
    # 用较少顶点的一侧决定 Sewing 数量
    # ========================================================

    k = min(
        len(best["path_a"]),
        len(best["path_b"])
    )


    sa = choose_k_vertices(
        best["path_a"],
        k
    )


    sb = choose_k_vertices(
        best["path_b"],
        k
    )


    for a, b in zip(sa, sb):

        if a != b:

            spring_pairs.append(
                (a, b)
            )


# Deduplicate connectors that may be repeated by overlapping semantic groups.
unique_pairs = []
seen_pairs = set()
for index_a, index_b in spring_pairs:
    key = tuple(sorted((index_a, index_b)))
    if key in seen_pairs:
        continue
    seen_pairs.add(key)
    unique_pairs.append((index_a, index_b))
spring_pairs = unique_pairs

connector_degree = {}
for index_a, index_b in spring_pairs:
    connector_degree[index_a] = connector_degree.get(index_a, 0) + 1
    connector_degree[index_b] = connector_degree.get(index_b, 0) + 1
hub_vertices = sorted(
    (vertex_index, degree)
    for vertex_index, degree in connector_degree.items()
    if degree > MAX_SEWING_CONNECTORS_PER_VERTEX
)
obj["sewing_spring_hub_vertex_count"] = len(hub_vertices)
if hub_vertices:
    preview = ", ".join(
        f"v{vertex_index}:degree{degree}"
        for vertex_index, degree in hub_vertices[:12]
    )
    raise RuntimeError(
        "Sewing pairing would create black-hole hubs: "
        f"{preview}. Each vertex may receive at most "
        f"{MAX_SEWING_CONNECTORS_PER_VERTEX} connectors. Check overlapping "
        "seam groups and A/B endpoint markers."
    )


# ============================================================
# 创建 Loose Edge / Sewing Spring
# ============================================================

initial_distances = [
    (world_co(index_a) - world_co(index_b)).length * 1000.0
    for index_a, index_b in spring_pairs
]

if not initial_distances:
    raise RuntimeError("没有生成任何 Sewing Spring 配对。")

maximum_initial_distance_mm = max(initial_distances)
configured_maximum_mm = float(SEWING_CONFIG["maximum_initial_distance_mm"])
preferred_maximum_mm = float(SEWING_CONFIG["preferred_initial_distance_mm"][1])

if maximum_initial_distance_mm > configured_maximum_mm:
    raise RuntimeError(
        f"Sewing Spring 最大初始距离 {maximum_initial_distance_mm:.1f} mm，"
        f"超过安全上限 {configured_maximum_mm:.1f} mm；请先重新 Arrangement。"
    )
if maximum_initial_distance_mm > preferred_maximum_mm:
    print(
        f"[Warning] Sewing Spring 最大初始距离 "
        f"{maximum_initial_distance_mm:.1f} mm，建议先优化 Arrangement。"
    )

bm = bmesh.new()

bm.from_mesh(mesh)

bm.verts.ensure_lookup_table()


created = 0
skipped = 0


for ia, ib in spring_pairs:

    va = bm.verts[ia]
    vb = bm.verts[ib]


    if (
        bm.edges.get((va, vb))
        is not None
    ):

        skipped += 1
        continue


    try:

        bm.edges.new(
            (va, vb)
        )

        created += 1


    except ValueError:

        skipped += 1


bm.to_mesh(mesh)
bm.free()

mesh.update()


obj[
    "sewing_springs_created"
] = created


print("")
print("========================================")
print(
    f"Created Sewing Springs: "
    f"{created}"
)
print(
    f"Skipped: "
    f"{skipped}"
)
print("========================================")
