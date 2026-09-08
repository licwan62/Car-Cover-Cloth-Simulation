"""Build semantic seam vertex groups and Sewing loose edges from an SVG.

Blender usage:
1. Import/mesh the SVG PANEL objects and select the flat panel Mesh objects.
2. Run this script and choose the matching semantic SVG file.
3. Selected Mesh objects are joined automatically. The script creates
   PANEL/HEM groups, maps SEAM paths to boundary vertices,
   creates automatic Sxxx_PANEL_A/B groups, then creates matched loose edges.

The SVG must contain PANEL and SEAM groups. Each Sxxx ID must occur exactly
twice, for example S001_TOP and S001_LEFT. MARK is not required: SVG path
starts become A and path ends become B, except TOP seams are normalized so A is
the left endpoint and B is the right endpoint. Run this before arranging in 3D.
"""

import re
import xml.etree.ElementTree as ET
from collections import defaultdict

import bmesh
import bpy
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector


# Standalone settings: 1 Blender unit = 1 metre.
MIN_SEGMENT_LENGTH_MM = 20.0
MAX_LENGTH_DIFFERENCE_RATIO = 0.15
MAPPING_TOLERANCE_FACTOR = 0.70
MAX_MAPPING_ERROR_FACTOR = 1.50
MAX_SEWING_CONNECTORS_PER_VERTEX = 2
DELETE_EXISTING_LOOSE_EDGES = True
FLAT_PANEL_TOLERANCE_MM = 2.0
TOP_SEAMS_LEFT_TO_RIGHT = True

_SEAM_NAME = re.compile(r"^(?:SEAM_)?(?P<id>S\d{3,})_(?P<panel>[A-Z][A-Z0-9]*)$")
_PATH_TOKEN = re.compile(
    r"[MmLlHhVvCcZz]|[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?"
)


def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


def _distance_to_segment(point, start, end):
    delta = end - start
    length_squared = delta.length_squared
    if length_squared <= 1.0e-20:
        return (point - start).length
    factor = max(0.0, min(1.0, (point - start).dot(delta) / length_squared))
    return (point - (start + factor * delta)).length


def _distance_to_polyline(point, polyline):
    return min(
        _distance_to_segment(point, polyline[index - 1], polyline[index])
        for index in range(1, len(polyline))
    )


def _cubic(a, b, c, d, factor):
    inverse = 1.0 - factor
    return (
        a * (inverse ** 3)
        + b * (3.0 * inverse * inverse * factor)
        + c * (3.0 * inverse * factor * factor)
        + d * (factor ** 3)
    )


def _flatten_path(data, curve_steps=16):
    """Flatten Illustrator M/L/H/V/C/Z path data into one polyline."""

    tokens = _PATH_TOKEN.findall(data.replace(",", " "))
    points = []
    cursor = Vector((0.0, 0.0))
    subpath_start = None
    command = None
    index = 0

    def number():
        nonlocal index
        if index >= len(tokens) or tokens[index].isalpha():
            raise ValueError("SVG path command is missing a coordinate")
        value = float(tokens[index])
        index += 1
        return value

    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
        if command is None:
            raise ValueError("SVG path must begin with M/m")
        relative = command.islower()
        upper = command.upper()

        if upper == "Z":
            if subpath_start is not None and (not points or points[-1] != subpath_start):
                points.append(subpath_start.copy())
            cursor = subpath_start.copy()
            command = None
            continue
        if upper == "M" or upper == "L":
            value = Vector((number(), number()))
            cursor = cursor + value if relative else value
            points.append(cursor.copy())
            if upper == "M":
                subpath_start = cursor.copy()
                command = "l" if relative else "L"
            continue
        if upper == "H":
            value = number()
            cursor.x = cursor.x + value if relative else value
            points.append(cursor.copy())
            continue
        if upper == "V":
            value = number()
            cursor.y = cursor.y + value if relative else value
            points.append(cursor.copy())
            continue
        if upper == "C":
            values = [number() for _ in range(6)]
            control_a = Vector(values[0:2])
            control_b = Vector(values[2:4])
            end = Vector(values[4:6])
            if relative:
                control_a += cursor
                control_b += cursor
                end += cursor
            start = cursor.copy()
            for step in range(1, curve_steps + 1):
                points.append(_cubic(start, control_a, control_b, end, step / curve_steps))
            cursor = end
            continue
        raise ValueError(f"Unsupported SVG path command: {command}")

    if len(points) < 2:
        raise ValueError("SVG path contains fewer than two points")
    return points


def _element_polyline(element):
    kind = _local_name(element.tag)
    if kind == "line":
        return [
            Vector((float(element.get("x1", 0.0)), float(element.get("y1", 0.0)))),
            Vector((float(element.get("x2", 0.0)), float(element.get("y2", 0.0)))),
        ]
    if kind == "rect":
        x = float(element.get("x", 0.0))
        y = float(element.get("y", 0.0))
        width = float(element.get("width", 0.0))
        height = float(element.get("height", 0.0))
        return [
            Vector((x, y)), Vector((x + width, y)),
            Vector((x + width, y + height)), Vector((x, y + height)),
            Vector((x, y)),
        ]
    if kind == "path":
        return _flatten_path(element.get("d", ""))
    raise ValueError(f"Unsupported semantic SVG element: {kind}")


def _semantic_svg(filepath):
    root = ET.parse(filepath).getroot()
    panels = {}
    seams = {}
    hems = {}

    def visit(element, semantic_layer=None):
        element_id = element.get("id", "")
        if _local_name(element.tag) == "g" and element_id in {"PANEL", "SEAM", "HEM"}:
            semantic_layer = element_id
        kind = _local_name(element.tag)
        if semantic_layer in {"PANEL", "SEAM", "HEM"} and kind in {"path", "line", "rect"}:
            if not element_id:
                raise ValueError(f"{semantic_layer} contains an unnamed {kind}")
            target = {"PANEL": panels, "SEAM": seams, "HEM": hems}[semantic_layer]
            if element_id in target:
                raise ValueError(f"Duplicate SVG id: {element_id}")
            target[element_id] = _element_polyline(element)
        for child in element:
            visit(child, semantic_layer)

    visit(root)
    if not panels:
        raise ValueError("SVG does not contain named geometry in the PANEL group")
    if not seams:
        raise ValueError("SVG does not contain named geometry in the SEAM group")

    by_id = defaultdict(list)
    for name in seams:
        match = _SEAM_NAME.fullmatch(name)
        if match is None:
            raise ValueError(f"Invalid SEAM id '{name}'; expected S001_TOP")
        by_id[match.group("id")].append(name)
    for seam_id, names in sorted(by_id.items()):
        if len(names) != 2:
            raise ValueError(
                f"{seam_id} must define exactly two SEAM paths; got {', '.join(names)}"
            )
    for name in seams:
        panel_name = f"PANEL_{_SEAM_NAME.fullmatch(name).group('panel')}"
        if panel_name not in panels:
            raise ValueError(f"{name} has no matching {panel_name} geometry in PANEL")
    return panels, seams, hems, [(names[0], names[1]) for _, names in sorted(by_id.items())]


def _boundary_data(mesh):
    face_counts = defaultdict(int)
    for polygon in mesh.polygons:
        vertices = polygon.vertices
        for index in range(len(vertices)):
            face_counts[tuple(sorted((vertices[index], vertices[(index + 1) % len(vertices)])))] += 1
    edges = [tuple(edge.vertices) for edge in mesh.edges if face_counts[tuple(sorted(edge.vertices))] == 1]
    vertices = sorted({vertex for edge in edges for vertex in edge})
    if not edges:
        loose_count = sum(1 for count in face_counts.values() if count == 0)
        if not mesh.polygons:
            raise RuntimeError(
                f"活动 Mesh 没有面（vertices={len(mesh.vertices)}, edges={len(mesh.edges)}）；"
                "它可能是 SVG 轮廓或 SEAM 线框。请选中 remesh.py 生成的 "
                "*_CLOTH_* 三角网格。"
            )
        raise RuntimeError(
            f"活动 Mesh 没有 Cloth Boundary Edge（faces={len(mesh.polygons)}, "
            f"edges={len(mesh.edges)}, loose={loose_count}）。"
            "网格可能已经封闭、应用了 Solidify，或边界存在重复面。"
        )
    return edges, vertices


def _bounds_2d(polylines):
    points = [point for polyline in polylines for point in polyline]
    return (
        Vector((min(point.x for point in points), min(point.y for point in points))),
        Vector((max(point.x for point in points), max(point.y for point in points))),
    )


def _candidate_mappers(svg_bounds, mesh_bounds):
    svg_low, svg_high = svg_bounds
    mesh_low, mesh_high = mesh_bounds
    svg_size = svg_high - svg_low
    mesh_size = mesh_high - mesh_low
    if min(svg_size) <= 0.0 or min(mesh_size) <= 0.0:
        raise RuntimeError("SVG 或 Mesh 的二维包围盒尺寸无效。")

    for swap in (False, True):
        source_size = Vector((svg_size.y, svg_size.x)) if swap else svg_size
        scale = Vector((mesh_size.x / source_size.x, mesh_size.y / source_size.y))
        for flip_x in (False, True):
            for flip_y in (False, True):
                def mapper(point, swap=swap, scale=scale.copy(), flip_x=flip_x, flip_y=flip_y):
                    normalized = Vector((
                        (point.x - svg_low.x) / svg_size.x,
                        (point.y - svg_low.y) / svg_size.y,
                    ))
                    if swap:
                        normalized = Vector((normalized.y, normalized.x))
                    if flip_x:
                        normalized.x = 1.0 - normalized.x
                    if flip_y:
                        normalized.y = 1.0 - normalized.y
                    return mesh_low + Vector((normalized.x * mesh_size.x, normalized.y * mesh_size.y))
                yield mapper


def _best_mapper(panel_paths, seam_paths, boundary_points, boundary_segments):
    """Choose the SVG orientation using distance to the actual mesh boundary.

    Measuring probes against boundary vertices produces a resolution-dependent
    error: a point on the middle of a long boundary edge is reported as being
    half an edge length away.  Measure against boundary segments instead so the
    mapping error represents geometric misalignment rather than mesh density.
    """

    svg_bounds = _bounds_2d(panel_paths.values())
    mesh_bounds = _bounds_2d([[point for point in boundary_points]])
    probes = [point for path in seam_paths.values() for point in path]
    best = None
    for mapper in _candidate_mappers(svg_bounds, mesh_bounds):
        error = sum(
            min(
                _distance_to_segment(mapper(point), start, end)
                for start, end in boundary_segments
            )
            for point in probes
        ) / len(probes)
        if best is None or error < best[0]:
            best = (error, mapper)
    return best


def _inside_polygon(point, polygon):
    inside = False
    previous = polygon[-1]
    for current in polygon:
        crosses = (current.y > point.y) != (previous.y > point.y)
        if crosses:
            crossing_x = (
                (previous.x - current.x) * (point.y - current.y)
                / (previous.y - current.y) + current.x
            )
            if point.x < crossing_x:
                inside = not inside
        previous = current
    return inside


def _replace_group(obj, name, indices):
    old = obj.vertex_groups.get(name)
    if old is not None:
        obj.vertex_groups.remove(old)
    group = obj.vertex_groups.new(name=name)
    group.add(list(indices), 1.0, "REPLACE")


def _is_flat_panel_mesh(obj):
    if obj.type != "MESH" or not obj.data.vertices or not obj.data.polygons:
        return False
    z_values = [vertex.co.z for vertex in obj.data.vertices]
    local_thickness = max(z_values) - min(z_values)
    scale_z = abs(obj.matrix_world.to_scale().z)
    return local_thickness * scale_z <= FLAT_PANEL_TOLERANCE_MM / 1000.0


def _prepare_active_mesh(context):
    """Enter Object Mode and join the selected flat panel Mesh objects."""

    active = context.active_object
    if active is None:
        raise RuntimeError("没有活动对象；请选择平面版片 Mesh。")

    if active.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError as error:
            raise RuntimeError(
                f"无法从 {active.mode} 切换到 Object Mode：{error}"
            ) from error

    selected_meshes = [obj for obj in context.selected_objects if _is_flat_panel_mesh(obj)]
    if not _is_flat_panel_mesh(active):
        if selected_meshes:
            active = selected_meshes[0]
            context.view_layer.objects.active = active
            print(f"活动对象不是 Cloth 面网格，自动改用: {active.name}")
        elif active.type == "MESH" and not active.data.polygons:
            raise RuntimeError(
                f"活动 Mesh '{active.name}' 没有面；请选择 remesh.py 生成的 "
                "*_CLOTH_* 三角网格，而不是 SVG 轮廓线。"
            )
        elif active.type != "MESH":
            raise RuntimeError(
                f"活动对象类型为 {active.type}；请选择 remesh 后的 Mesh。"
            )
        else:
            raise RuntimeError(
                f"活动 Mesh '{active.name}' 不是平面 XY 版片；局部 Z 厚度必须不超过 "
                f"{FLAT_PANEL_TOLERANCE_MM:g} mm。"
            )

    if active not in selected_meshes:
        active.select_set(True)
        selected_meshes.append(active)

    if len(selected_meshes) > 1:
        # Join only Mesh panels. Selected cameras, empties or SVG guide curves
        # must not participate in the operation.
        for selected in list(context.selected_objects):
            selected.select_set(selected in selected_meshes)
        context.view_layer.objects.active = active
        names = [obj.name for obj in selected_meshes]
        result = bpy.ops.object.join()
        if result != {"FINISHED"}:
            raise RuntimeError("自动合并所选版片 Mesh 失败。")
        active = context.active_object
        print(f"自动合并 {len(names)} 个版片 Mesh: {', '.join(names)}")

    if active is None or active.type != "MESH" or active.mode != "OBJECT":
        raise RuntimeError("未能准备有效的 Object Mode Cloth Mesh。")
    return active


def _ordered_boundary_path(group_indices, boundary_edges):
    selected = set(group_indices)
    adjacency = defaultdict(list)
    for start, end in boundary_edges:
        if start in selected and end in selected:
            adjacency[start].append(end)
            adjacency[end].append(start)
    active = set(adjacency)
    terminals = [index for index in active if len(adjacency[index]) == 1]
    if len(terminals) != 2 or any(len(adjacency[index]) > 2 for index in active):
        raise RuntimeError("Seam 顶点组没有形成一条开放、无分支的 Boundary Path。")
    path = [terminals[0]]
    previous = None
    current = terminals[0]
    while True:
        following = [index for index in adjacency[current] if index != previous]
        if not following:
            break
        previous, current = current, following[0]
        path.append(current)
    if set(path) != active:
        raise RuntimeError("Seam 顶点组包含不连续的 Boundary 段。")
    return path


def _orient_semantic_path(path, name, coordinates, mapped_path):
    """Apply the project direction rule before creating automatic A/B groups."""

    parsed = _SEAM_NAME.fullmatch(name)
    if parsed and parsed.group("panel") == "TOP" and TOP_SEAMS_LEFT_TO_RIGHT:
        # TOP is authoritative in Blender local XY: A is always the endpoint
        # with the smaller local X and B is always the endpoint to its right.
        if coordinates[path[0]].x > coordinates[path[-1]].x:
            path.reverse()
        return path

    start_target = mapped_path[0]
    if (
        Vector((coordinates[path[-1]].x, coordinates[path[-1]].y)) - start_target
    ).length < (
        Vector((coordinates[path[0]].x, coordinates[path[0]].y)) - start_target
    ).length:
        path.reverse()
    return path


def _cumulative_lengths(path, coordinates):
    values = [0.0]
    for index in range(1, len(path)):
        values.append(values[-1] + (coordinates[path[index]] - coordinates[path[index - 1]]).length)
    return values


def _sample_path(path, coordinates, count):
    cumulative = _cumulative_lengths(path, coordinates)
    total = cumulative[-1]
    if total <= 0.0:
        raise RuntimeError("Seam Path 长度为零。")
    result = []
    for sample in range(count):
        target = total * sample / (count - 1)
        nearest = min(range(len(path)), key=lambda index: abs(cumulative[index] - target))
        if not result or result[-1] != path[nearest]:
            result.append(path[nearest])
    return result, total


def build_semantic_sewing(obj, filepath):
    if obj is None or obj.type != "MESH" or obj.mode != "OBJECT":
        raise RuntimeError("请在 Object Mode 激活已合并的平面 Cloth Mesh。")

    panels, seams, hems, seam_pairs = _semantic_svg(filepath)
    mesh = obj.data
    boundary_edges, boundary_indices = _boundary_data(mesh)
    coordinates = {vertex.index: vertex.co.copy() for vertex in mesh.vertices}
    boundary_points = [Vector((coordinates[index].x, coordinates[index].y)) for index in boundary_indices]
    boundary_segments = [
        (
            Vector((coordinates[start].x, coordinates[start].y)),
            Vector((coordinates[end].x, coordinates[end].y)),
        )
        for start, end in boundary_edges
    ]
    edge_lengths = sorted(
        (coordinates[start] - coordinates[end]).length for start, end in boundary_edges
    )
    median_edge = edge_lengths[len(edge_lengths) // 2]
    tolerance = max(median_edge * MAPPING_TOLERANCE_FACTOR, 1.0e-6)

    semantic_edges = dict(seams)
    semantic_edges.update(hems)
    mapping_error, mapper = _best_mapper(
        panels, semantic_edges, boundary_points, boundary_segments
    )
    if mapping_error > tolerance * MAX_MAPPING_ERROR_FACTOR:
        raise RuntimeError(
            f"SVG→Mesh 平均映射误差 {mapping_error * 1000.0:.1f} mm 过大；"
            "请在裁片仍为平面且布局未改变时运行。"
        )

    for name, svg_path in panels.items():
        mapped_path = [mapper(point) for point in svg_path]
        selected = {
            vertex.index for vertex in mesh.vertices
            if _inside_polygon(Vector((vertex.co.x, vertex.co.y)), mapped_path)
            or _distance_to_polyline(Vector((vertex.co.x, vertex.co.y)), mapped_path) <= tolerance
        }
        if not selected:
            raise RuntimeError(f"{name} 没有映射到 Mesh 顶点。")
        _replace_group(obj, name, selected)

    mapped_boundary_groups = {}
    for name, svg_path in semantic_edges.items():
        mapped_path = [mapper(point) for point in svg_path]
        selected = {
            index for index in boundary_indices
            if _distance_to_polyline(
                Vector((coordinates[index].x, coordinates[index].y)), mapped_path
            ) <= tolerance
        }
        if len(selected) < 2:
            raise RuntimeError(f"{name} 只映射到 {len(selected)} 个边界顶点。")
        _replace_group(obj, name, selected)
        path = _ordered_boundary_path(selected, boundary_edges)
        mapped_boundary_groups[name] = path
        if name not in seams:
            continue
        _orient_semantic_path(path, name, coordinates, mapped_path)
        _replace_group(obj, f"{name}_A", [path[0]])
        _replace_group(obj, f"{name}_B", [path[-1]])

    if DELETE_EXISTING_LOOSE_EDGES:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        loose = [edge for edge in bm.edges if not edge.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="EDGES")
        bm.to_mesh(mesh)
        bm.free()

    connectors = []
    degree = defaultdict(int)
    for name_a, name_b in seam_pairs:
        path_a = mapped_boundary_groups[name_a]
        path_b = mapped_boundary_groups[name_b]
        count = max(2, min(len(path_a), len(path_b)))
        sampled_a, length_a = _sample_path(path_a, coordinates, count)
        sampled_b, length_b = _sample_path(path_b, coordinates, count)
        difference = abs(length_a - length_b) / max(length_a, length_b)
        if difference > MAX_LENGTH_DIFFERENCE_RATIO:
            raise RuntimeError(
                f"{name_a} ↔ {name_b} 长度差 {difference:.1%} 超过 "
                f"{MAX_LENGTH_DIFFERENCE_RATIO:.0%}。"
            )
        pair_count = min(len(sampled_a), len(sampled_b))
        for index_a, index_b in zip(sampled_a[:pair_count], sampled_b[:pair_count]):
            if index_a == index_b:
                continue
            degree[index_a] += 1
            degree[index_b] += 1
            if max(degree[index_a], degree[index_b]) > MAX_SEWING_CONNECTORS_PER_VERTEX:
                raise RuntimeError("Sewing 配对会产生多对一汇聚点，已停止。")
            connectors.append(tuple(sorted((index_a, index_b))))

    connectors = sorted(set(connectors))
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    existing = {tuple(sorted((edge.verts[0].index, edge.verts[1].index))) for edge in bm.edges}
    for start, end in connectors:
        if (start, end) not in existing:
            bm.edges.new((bm.verts[start], bm.verts[end]))
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj["semantic_sewing_svg"] = filepath
    obj["semantic_sewing_edges"] = len(connectors)
    print(
        f"Semantic Sewing: svg={filepath}, panel_groups={len(panels)}, "
        f"seam_groups={len(seams)}, hem_groups={len(hems)}, "
        f"pairs={len(seam_pairs)}, loose_edges={len(connectors)}, "
        f"mapping_error={mapping_error * 1000.0:.2f} mm"
    )
    return len(connectors)


class CC_OT_generate_semantic_sewing(bpy.types.Operator, ImportHelper):
    """从语义 SVG 创建缝合顶点组与 Sewing Loose Edge"""

    bl_idname = "cc.generate_semantic_sewing"
    bl_label = "从语义 SVG 生成 Sewing"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".svg"
    filter_glob: bpy.props.StringProperty(default="*.svg", options={"HIDDEN"})

    def execute(self, context):
        try:
            cloth = _prepare_active_mesh(context)
            count = build_semantic_sewing(cloth, self.filepath)
        except (ET.ParseError, OSError, RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, f"已生成 {count} 条 Sewing Loose Edge")
        return {"FINISHED"}


def launch_svg_dialog():
    previous = getattr(bpy.types, CC_OT_generate_semantic_sewing.__name__, None)
    if previous is not None:
        try:
            bpy.utils.unregister_class(previous)
        except RuntimeError:
            pass
    bpy.utils.register_class(CC_OT_generate_semantic_sewing)
    if bpy.app.background:
        raise RuntimeError("后台模式请直接调用 build_semantic_sewing(obj, svg_filepath)。")
    return bpy.ops.cc.generate_semantic_sewing("INVOKE_DEFAULT")


if __name__ == "__main__":
    launch_svg_dialog()
