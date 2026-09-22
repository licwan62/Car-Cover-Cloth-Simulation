"""Add a vertical door-position line to both sides of a settled car cover.

Usage in Blender:
1. Go to the settled comparison frame.
2. Select the car-cover mesh and make it active.
3. Ensure it has PANEL_LEFT and PANEL_RIGHT vertex groups.
4. Run this script and enter the distance from the vehicle front.

The marker is a material assignment on existing cloth faces. It adds no
geometry, mass, collision, constraints, or modifiers and does not affect Cloth.
"""

import bpy
import copy


DOOR_MARKER_CONFIG = {
    "front_axis": "-Y",
    "distance_from_front_mm": 1800.0,
    "line_width_mm": 30.0,
    "material_name": "CC Door Position Mark",
    "color_rgba": [0.04, 0.9, 0.16, 1.0],
}

MARK_ATTRIBUTE = "cc_door_marker_faces"
MARK_MATERIAL_SLOT = "cc_door_marker_material_slot"
COORDINATE_SOURCE = "cc_door_marker_coordinate_source"


def _is_cloth(obj):
    return obj.type == "MESH" and any(mod.type == "CLOTH" for mod in obj.modifiers)


def _active_cloth():
    active = bpy.context.view_layer.objects.active
    if active and _is_cloth(active):
        return active
    selected = [obj for obj in bpy.context.selected_objects if _is_cloth(obj)]
    if len(selected) == 1:
        return selected[0]
    raise RuntimeError("请激活唯一的 Cloth 网格后再运行车门标记脚本。")


def _vertex_group_indices(obj, name):
    group = obj.vertex_groups.get(name)
    if group is None:
        raise RuntimeError(
            f"缺少 {name} 顶点组；请先运行 generate_sewing.py "
            "从语义 SVG 创建 PANEL 顶点组。"
        )
    indices = {
        vertex.index
        for vertex in obj.data.vertices
        if any(item.group == group.index and item.weight > 0.001 for item in vertex.groups)
    }
    if not indices:
        raise RuntimeError(f"{name} 顶点组为空。")
    return indices


def _evaluated_geometry(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    try:
        if (
            len(mesh.polygons) != len(obj.data.polygons)
            or len(mesh.vertices) != len(obj.data.vertices)
        ):
            raise RuntimeError(
                "车门标记要求评估网格与基础网格拓扑一致；"
                "请暂时关闭会改变拓扑的显示修改器。"
            )
        matrix = evaluated.matrix_world
        centers = [matrix @ polygon.center for polygon in mesh.polygons]
        vertices = [matrix @ vertex.co for vertex in mesh.vertices]
        return centers, vertices
    finally:
        evaluated.to_mesh_clear()


def _panel_geometry(obj):
    panels = {}
    for name in ("PANEL_LEFT", "PANEL_RIGHT"):
        vertex_indices = _vertex_group_indices(obj, name)
        polygon_indices = {
            polygon.index
            for polygon in obj.data.polygons
            if all(index in vertex_indices for index in polygon.vertices)
        }
        if not polygon_indices:
            raise RuntimeError(f"{name} 没有包含任何完整布料面。")
        panels[name] = {
            "vertices": vertex_indices,
            "polygons": polygon_indices,
        }
    return panels


def _longitudinal_axis(config):
    axis = str(config["front_axis"]).upper()
    if axis not in {"+X", "-X", "+Y", "-Y"}:
        raise ValueError("front_axis 必须为 '+X'、'-X'、'+Y' 或 '-Y'。")
    return axis, 0 if axis.endswith("X") else 1


def _door_position(evaluated_vertices, panel_vertex_indices, axis, distance_mm):
    component = 0 if axis.endswith("X") else 1
    coordinates = [
        evaluated_vertices[index][component]
        for indices in panel_vertex_indices
        for index in indices
    ]
    front = max(coordinates) if axis.startswith("+") else min(coordinates)
    direction = -1.0 if axis.startswith("+") else 1.0
    return front + direction * float(distance_mm) / 1000.0


def _ensure_material(config):
    name = str(config["material_name"])
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    color = tuple(float(value) for value in config["color_rgba"])
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Roughness"].default_value = 0.48
        if "Emission Color" in principled.inputs:
            principled.inputs["Emission Color"].default_value = color
            principled.inputs["Emission Strength"].default_value = 0.18
    return material


def _material_slot(obj, material):
    stored = obj.get(MARK_MATERIAL_SLOT)
    if isinstance(stored, int) and stored < len(obj.data.materials):
        if obj.data.materials[stored] == material:
            return stored
    for index, slot_material in enumerate(obj.data.materials):
        if slot_material == material:
            obj[MARK_MATERIAL_SLOT] = index
            return index
    obj.data.materials.append(material)
    index = len(obj.data.materials) - 1
    obj[MARK_MATERIAL_SLOT] = index
    return index


def _base_slot(obj, excluded_slot):
    existing = next(
        (index for index in range(len(obj.data.materials)) if index != excluded_slot),
        None,
    )
    if existing is not None:
        return existing
    base = bpy.data.materials.get("CC Cloth Base") or bpy.data.materials.new("CC Cloth Base")
    base.diffuse_color = (0.18, 0.22, 0.28, 1.0)
    obj.data.materials.append(base)
    return len(obj.data.materials) - 1


def apply_door_marker(cloth=None, config=None):
    config = copy.deepcopy(DOOR_MARKER_CONFIG if config is None else config)
    cloth = cloth or _active_cloth()
    _, evaluated_vertices = _evaluated_geometry(cloth)
    panels = _panel_geometry(cloth)
    axis, longitudinal = _longitudinal_axis(config)
    position = _door_position(
        evaluated_vertices,
        [panel["vertices"] for panel in panels.values()],
        axis,
        config["distance_from_front_mm"],
    )
    half_width = max(float(config["line_width_mm"]) / 2000.0, 1.0e-6)

    material_slot = _material_slot(cloth, _ensure_material(config))
    fallback_slot = _base_slot(cloth, material_slot)
    for polygon in cloth.data.polygons:
        if polygon.material_index == material_slot:
            polygon.material_index = fallback_slot

    marked = set()
    counts = {}
    for panel_name, panel in panels.items():
        selected = {
            index
            for index in panel["polygons"]
            if min(
                evaluated_vertices[vertex_index][longitudinal]
                for vertex_index in cloth.data.polygons[index].vertices
            ) <= position + half_width
            and max(
                evaluated_vertices[vertex_index][longitudinal]
                for vertex_index in cloth.data.polygons[index].vertices
            ) >= position - half_width
        }
        if not selected:
            raise RuntimeError(
                f"距车头 {config['distance_from_front_mm']:g} mm 处未在 {panel_name} "
                "找到布料面；请检查车头方向、距离或增大线宽。"
            )
        for index in selected:
            cloth.data.polygons[index].material_index = material_slot
        marked.update(selected)
        counts[panel_name] = len(selected)

    cloth[MARK_ATTRIBUTE] = ",".join(str(index) for index in sorted(marked))
    cloth[COORDINATE_SOURCE] = "evaluated_panel_left_right_front_bound"
    cloth["cc_door_marker_front_offset_mm"] = float(config["distance_from_front_mm"])
    cloth["cc_door_marker_line_width_mm"] = float(config["line_width_mm"])
    cloth.data.update()
    print(
        f"Door marker: cloth={cloth.name}, distance_from_front="
        f"{config['distance_from_front_mm']:g} mm, faces={len(marked)}, counts={counts}"
    )
    return marked


class CC_OT_setup_door_marker(bpy.types.Operator):
    """按距车头的长度在左右侧版片上生成平行 Z 轴的车门标记线"""

    bl_idname = "cc.setup_door_marker"
    bl_label = "车门位置标记线"
    bl_options = {"REGISTER", "UNDO"}

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager
        layout.prop(settings, "cc_door_marker_front_axis")
        layout.prop(settings, "cc_door_marker_distance_mm")
        layout.prop(settings, "cc_door_marker_width_mm")

    def execute(self, context):
        settings = context.window_manager
        config = copy.deepcopy(DOOR_MARKER_CONFIG)
        config.update({
            "front_axis": settings.cc_door_marker_front_axis,
            "distance_from_front_mm": settings.cc_door_marker_distance_mm,
            "line_width_mm": settings.cc_door_marker_width_mm,
        })
        try:
            marked = apply_door_marker(config=config)
        except (RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, f"已生成车门标记线：{len(marked)} 个面")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)


def launch_door_marker_dialog():
    """Register safely on repeated Text Editor runs and open the dialog."""
    previous = getattr(bpy.types, CC_OT_setup_door_marker.__name__, None)
    if previous is not None:
        try:
            bpy.utils.unregister_class(previous)
        except RuntimeError:
            pass

    wm = bpy.types.WindowManager
    wm.cc_door_marker_front_axis = bpy.props.EnumProperty(
        name="车头方向",
        items=(("-Y", "-Y", "Model X 默认"), ("+Y", "+Y", ""),
               ("-X", "-X", ""), ("+X", "+X", "")),
        default=DOOR_MARKER_CONFIG["front_axis"],
    )
    wm.cc_door_marker_distance_mm = bpy.props.FloatProperty(
        name="距车头长度 (mm)",
        min=0.0,
        default=DOOR_MARKER_CONFIG["distance_from_front_mm"],
    )
    wm.cc_door_marker_width_mm = bpy.props.FloatProperty(
        name="标记线宽 (mm)",
        min=1.0,
        default=DOOR_MARKER_CONFIG["line_width_mm"],
    )
    bpy.utils.register_class(CC_OT_setup_door_marker)
    if bpy.app.background:
        return apply_door_marker(config=copy.deepcopy(DOOR_MARKER_CONFIG))
    return bpy.ops.cc.setup_door_marker("INVOKE_DEFAULT")


if __name__ == "__main__":
    launch_door_marker_dialog()
