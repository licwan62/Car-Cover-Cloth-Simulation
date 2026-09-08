"""Add non-physical left/right mirror-pocket reference marks to a settled cover.

Usage in Blender:
1. Go to the settled comparison frame.
2. Select the car-cover mesh and make it active.
3. Ensure it has PANEL_LEFT and PANEL_RIGHT vertex groups from the semantic SVG.
4. Run this script. Re-running replaces the previous marker assignment.

The marks are material assignments on existing cloth faces. They add no geometry,
mass, collision, constraints, or modifiers and therefore do not affect Cloth.
"""

import bpy
import copy
from mathutils import Vector


MARKER_CONFIG = {
    "front_axis": "-Y",
    "mirror": {
        "distance_from_front_mm": 1600.0,
        "height_from_bottom_mm": 1020.0,
        "width_mm": 430.0,
        "height_mm": 320.0,
        "material_name": "CC Mirror Position Mark",
        "color_rgba": [1.0, 0.12, 0.015, 1.0],
    },
    "charge_port": {
        "side": "PANEL_LEFT",
        "distance_from_rear_mm": 340.0,
        "height_from_bottom_mm": 820.0,
        "width_mm": 180.0,
        "height_mm": 160.0,
        "material_name": "CC Charge Port Position Mark",
        "color_rgba": [0.02, 0.35, 1.0, 1.0],
    },
}

MARK_ATTRIBUTE = "cc_mirror_marker"
MARK_MATERIAL_SLOT = "cc_mirror_marker_material_slot"
COORDINATE_SOURCE = "cc_mirror_marker_coordinate_source"


def _is_cloth(obj):
    return obj.type == "MESH" and any(mod.type == "CLOTH" for mod in obj.modifiers)


def _active_cloth():
    active = bpy.context.view_layer.objects.active
    if active and _is_cloth(active):
        return active
    selected = [obj for obj in bpy.context.selected_objects if _is_cloth(obj)]
    if len(selected) == 1:
        return selected[0]
    raise RuntimeError("请激活唯一的 Cloth 网格后再运行耳位标记脚本。")


def _ensure_material(mark_config):
    name = str(mark_config["material_name"])
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    color = tuple(float(v) for v in mark_config["color_rgba"])
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


def _marker_slot(obj, material):
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


def _ensure_base_slot(obj, excluded_slots=()):
    existing = next((i for i in range(len(obj.data.materials)) if i not in excluded_slots), None)
    if existing is not None:
        return existing
    name = "CC Cloth Base"
    base = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    base.diffuse_color = (0.18, 0.22, 0.28, 1.0)
    obj.data.materials.append(base)
    return len(obj.data.materials) - 1


def _vertex_group_indices(obj, name):
    group = obj.vertex_groups.get(name)
    if group is None:
        raise RuntimeError(
            f"缺少 {name} 顶点组；请先运行 generate_sewing_standalone.py "
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
                "耳位标记要求评估网格与基础网格拓扑一致；"
                "请暂时关闭会改变拓扑的显示修改器。"
            )
        matrix = evaluated.matrix_world
        centers = [matrix @ polygon.center for polygon in mesh.polygons]
        vertices = [matrix @ vertex.co for vertex in mesh.vertices]
        return centers, vertices
    finally:
        evaluated.to_mesh_clear()


def _bounds(points):
    return (
        Vector((
            min(point.x for point in points),
            min(point.y for point in points),
            min(point.z for point in points),
        )),
        Vector((
            max(point.x for point in points),
            max(point.y for point in points),
            max(point.z for point in points),
        )),
    )


def _panel_geometry(obj, evaluated_vertices):
    result = {}
    for name in ("PANEL_LEFT", "PANEL_RIGHT"):
        vertex_indices = _vertex_group_indices(obj, name)
        polygon_indices = {
            polygon.index
            for polygon in obj.data.polygons
            if all(index in vertex_indices for index in polygon.vertices)
        }
        if not polygon_indices:
            raise RuntimeError(f"{name} 没有包含任何完整布料面。")
        result[name] = {
            "bounds": _bounds([evaluated_vertices[index] for index in vertex_indices]),
            "polygons": polygon_indices,
        }
    return result


def _longitudinal_position(low, high, axis, distance_mm, from_front):
    distance = float(distance_mm) / 1000.0
    front_is_high = axis.startswith("+")
    use_high = front_is_high if from_front else not front_is_high
    component = 0 if axis.endswith("X") else 1
    return high[component] - distance if use_high else low[component] + distance


def _longitudinal_axis(config):
    axis = str(config["front_axis"]).upper()
    if axis not in {"+X", "-X", "+Y", "-Y"}:
        raise ValueError("mirror_markers.front_axis 必须为 '+X'、'-X'、'+Y' 或 '-Y'。")
    return axis, 0 if axis.endswith("X") else 1


def _target_center(bounds, axis, distance_mm, from_front, height_mm):
    low, high = bounds
    longitudinal = 0 if axis.endswith("X") else 1
    result = (low + high) * 0.5
    result[longitudinal] = _longitudinal_position(
        low, high, axis, distance_mm, from_front
    )
    result.z = low.z + float(height_mm) / 1000.0
    return result


def _inside_rectangle(point, target, mark_config, longitudinal):
    # ``target`` is the rectangle center; width and height extend equally in
    # both directions from the configured ear/charge-port position.
    half_width = max(float(mark_config["width_mm"]) / 2000.0, 1.0e-6)
    half_height = max(float(mark_config["height_mm"]) / 2000.0, 1.0e-6)
    return (
        abs(point[longitudinal] - target[longitudinal]) <= half_width
        and abs(point.z - target.z) <= half_height
    )


def _charge_panel_name(side):
    value = str(side).upper()
    if value in {"PANEL_LEFT", "LEFT", "-LATERAL"}:
        return "PANEL_LEFT"
    if value in {"PANEL_RIGHT", "RIGHT", "+LATERAL"}:
        return "PANEL_RIGHT"
    raise ValueError("charge_port.side 必须为 PANEL_LEFT 或 PANEL_RIGHT。")


def apply_mirror_markers(cloth=None, config=None):
    config = copy.deepcopy(MARKER_CONFIG if config is None else config)
    cloth = cloth or _active_cloth()
    centers, evaluated_vertices = _evaluated_geometry(cloth)
    panels = _panel_geometry(cloth, evaluated_vertices)
    axis, longitudinal = _longitudinal_axis(config)

    mirror = config["mirror"]
    targets = {"mirror": []}
    for panel_name in ("PANEL_LEFT", "PANEL_RIGHT"):
        targets["mirror"].append((
            panel_name,
            _target_center(
                panels[panel_name]["bounds"], axis,
                mirror["distance_from_front_mm"], True,
                mirror["height_from_bottom_mm"],
            ),
        ))

    charge = config["charge_port"]
    charge_panel = _charge_panel_name(charge["side"])
    targets["charge_port"] = [(
        charge_panel,
        _target_center(
            panels[charge_panel]["bounds"], axis,
            charge["distance_from_rear_mm"], False,
            charge["height_from_bottom_mm"],
        ),
    )]

    marker_slots = {}
    for kind in ("mirror", "charge_port"):
        marker_slots[kind] = _marker_slot(cloth, _ensure_material(config[kind]))
    fallback_slot = _ensure_base_slot(cloth, set(marker_slots.values()))
    # Repair the previous version too: faces defaulted to marker slot 0 when the
    # cloth initially had no material, making the whole cover orange.
    for polygon in cloth.data.polygons:
        if polygon.material_index in marker_slots.values():
            polygon.material_index = fallback_slot

    marked = set()
    counts = {}
    for kind, kind_targets in targets.items():
        kind_marked = set()
        for panel_name, target in kind_targets:
            selected = [
                index for index in panels[panel_name]["polygons"]
                if _inside_rectangle(centers[index], target, config[kind], longitudinal)
            ]
            if not selected:
                raise RuntimeError(
                    f"{kind} 在 {panel_name} 的矩形坐标范围内没有布料面；"
                    "请确认当前帧已经完成落罩，"
                    "并检查 front_axis、位置及矩形宽高。"
                )
            kind_marked.update(selected)
        for index in kind_marked:
            cloth.data.polygons[index].material_index = marker_slots[kind]
        marked.update(kind_marked)
        counts[kind] = len(kind_marked)

    if not marked:
        raise RuntimeError("未能在布料上找到耳位标记面。")
    cloth[MARK_ATTRIBUTE] = ",".join(str(i) for i in sorted(marked))
    cloth[COORDINATE_SOURCE] = "evaluated_panel_left_right_bounds"
    cloth["cc_mirror_marker_front_offset_mm"] = float(config["mirror"]["distance_from_front_mm"])
    cloth["cc_mirror_marker_height_mm"] = float(config["mirror"]["height_from_bottom_mm"])
    cloth["cc_charge_marker_rear_offset_mm"] = float(config["charge_port"]["distance_from_rear_mm"])
    cloth["cc_charge_marker_height_mm"] = float(config["charge_port"]["height_from_bottom_mm"])
    cloth.data.update()
    print(
        f"Mirror markers: cloth={cloth.name}, reference=PANEL_LEFT/PANEL_RIGHT, "
        f"charge_panel={charge_panel}, faces={len(marked)}, counts={counts}"
    )
    return marked


class CC_OT_setup_mirror_markers(bpy.types.Operator):
    """按版型坐标添加后视镜耳位和充电口材质标记"""

    bl_idname = "cc.setup_mirror_markers"
    bl_label = "车罩耳位 / 充电口标记"
    bl_options = {"REGISTER", "UNDO"}

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager
        layout.prop(settings, "cc_marker_front_axis")
        mirror = layout.box()
        mirror.label(text="后视镜耳位：输入坐标为矩形中心")
        mirror.prop(settings, "cc_marker_mirror_x_mm")
        mirror.prop(settings, "cc_marker_mirror_y_mm")
        row = mirror.row(align=True)
        row.prop(settings, "cc_marker_mirror_width_mm")
        row.prop(settings, "cc_marker_mirror_height_mm")
        charge = layout.box()
        charge.label(text="充电口：车尾底部端点为原点")
        charge.prop(settings, "cc_marker_charge_side")
        charge.prop(settings, "cc_marker_charge_x_mm")
        charge.prop(settings, "cc_marker_charge_y_mm")
        row = charge.row(align=True)
        row.prop(settings, "cc_marker_charge_width_mm")
        row.prop(settings, "cc_marker_charge_height_mm")

    def execute(self, context):
        config = copy.deepcopy(MARKER_CONFIG)
        settings = context.window_manager
        config["front_axis"] = settings.cc_marker_front_axis
        config["mirror"].update({
            "distance_from_front_mm": settings.cc_marker_mirror_x_mm,
            "height_from_bottom_mm": settings.cc_marker_mirror_y_mm,
            "width_mm": settings.cc_marker_mirror_width_mm,
            "height_mm": settings.cc_marker_mirror_height_mm,
        })
        config["charge_port"].update({
            "side": settings.cc_marker_charge_side,
            "distance_from_rear_mm": settings.cc_marker_charge_x_mm,
            "height_from_bottom_mm": settings.cc_marker_charge_y_mm,
            "width_mm": settings.cc_marker_charge_width_mm,
            "height_mm": settings.cc_marker_charge_height_mm,
        })
        try:
            marked = apply_mirror_markers(config=config)
        except (RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, f"已生成 {len(marked)} 个标记面")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=520)


def launch_marker_dialog():
    """Register safely on repeated Text Editor runs and open the settings dialog."""
    previous = getattr(bpy.types, CC_OT_setup_mirror_markers.__name__, None)
    if previous is not None:
        try:
            bpy.utils.unregister_class(previous)
        except RuntimeError:
            pass
    wm = bpy.types.WindowManager
    wm.cc_marker_front_axis = bpy.props.EnumProperty(
        name="车头方向", items=(("-Y", "-Y", "Model X 默认"), ("+Y", "+Y", ""),
                                 ("-X", "-X", ""), ("+X", "+X", "")),
        default=MARKER_CONFIG["front_axis"])
    wm.cc_marker_mirror_x_mm = bpy.props.FloatProperty(
        name="耳位中心距车头 X (mm)", min=0.0, default=MARKER_CONFIG["mirror"]["distance_from_front_mm"])
    wm.cc_marker_mirror_y_mm = bpy.props.FloatProperty(
        name="耳位中心距底部 Y (mm)", min=0.0, default=MARKER_CONFIG["mirror"]["height_from_bottom_mm"])
    wm.cc_marker_mirror_width_mm = bpy.props.FloatProperty(
        name="耳位宽 (mm)", min=1.0, default=MARKER_CONFIG["mirror"]["width_mm"])
    wm.cc_marker_mirror_height_mm = bpy.props.FloatProperty(
        name="耳位高 (mm)", min=1.0, default=MARKER_CONFIG["mirror"]["height_mm"])
    wm.cc_marker_charge_side = bpy.props.EnumProperty(
        name="充电口版片", items=(("PANEL_LEFT", "PANEL_LEFT", "左侧版片"),
                                     ("PANEL_RIGHT", "PANEL_RIGHT", "右侧版片")),
        default=MARKER_CONFIG["charge_port"]["side"])
    wm.cc_marker_charge_x_mm = bpy.props.FloatProperty(
        name="充电口距车尾 X (mm)", min=0.0, default=MARKER_CONFIG["charge_port"]["distance_from_rear_mm"])
    wm.cc_marker_charge_y_mm = bpy.props.FloatProperty(
        name="充电口距底部 Y (mm)", min=0.0, default=MARKER_CONFIG["charge_port"]["height_from_bottom_mm"])
    wm.cc_marker_charge_width_mm = bpy.props.FloatProperty(
        name="充电口宽 (mm)", min=1.0, default=MARKER_CONFIG["charge_port"]["width_mm"])
    wm.cc_marker_charge_height_mm = bpy.props.FloatProperty(
        name="充电口高 (mm)", min=1.0, default=MARKER_CONFIG["charge_port"]["height_mm"])
    bpy.utils.register_class(CC_OT_setup_mirror_markers)
    if bpy.app.background:
        return apply_mirror_markers(config=copy.deepcopy(MARKER_CONFIG))
    return bpy.ops.cc.setup_mirror_markers("INVOKE_DEFAULT")


if __name__ == "__main__":
    launch_marker_dialog()
