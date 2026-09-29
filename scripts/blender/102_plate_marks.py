"""Paint plate-opening mockups on the settled PANEL_TOP cloth.

Select the Cloth mesh, go to the comparison frame, then run in Blender's Text
Editor. The dark rectangles are material marks, not physical cutouts; they do
not change Cloth topology, mass, or collision. Distances are clear gaps from a
front/rear PANEL_TOP edge to the nearest rectangle edge in world coordinates.
"""

import bpy
import re


PLATES_CONFIG = {
    "front_axis": "-Y",
    "front_distance_mm": 300.0,
    "rear_distance_mm": 300.0,
    "length_mm": 440.0,
    "width_mm": 140.0,
    "front_only": False,
    "material_name": "CC Plate Opening Mockup",
    "color_rgba": (0.012, 0.012, 0.016, 1.0),
    "color_hex": "#1C1C21",
}

SLOT_KEY = "cc_plates_material_slot"
FACES_KEY = "cc_plates_faces"


def _active_cloth():
    obj = bpy.context.view_layer.objects.active
    if obj and obj.type == "MESH" and any(m.type == "CLOTH" for m in obj.modifiers):
        return obj
    raise RuntimeError("请先选中并激活带 Cloth 修改器的车衣网格")


def _top_faces(obj):
    group = obj.vertex_groups.get("PANEL_TOP")
    if group is None:
        raise RuntimeError("缺少 PANEL_TOP 顶点组")
    vertices = {
        v.index for v in obj.data.vertices
        if any(g.group == group.index and g.weight > 0.001 for g in v.groups)
    }
    faces = [p for p in obj.data.polygons if all(i in vertices for i in p.vertices)]
    if not faces:
        raise RuntimeError("PANEL_TOP 没有完整的布料面")
    return faces


def _world_vertices(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    try:
        if len(mesh.vertices) != len(obj.data.vertices) or len(mesh.polygons) != len(obj.data.polygons):
            raise RuntimeError("评估后的网格拓扑已变化；请暂时关闭改变拓扑的显示修改器")
        return [evaluated.matrix_world @ v.co for v in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()


def _material_slot(obj, config):
    material = bpy.data.materials.get(config["material_name"])
    if material is None:
        material = bpy.data.materials.new(config["material_name"])
    color_hex = config.get("color_hex")
    if color_hex is not None:
        match = re.fullmatch(r"#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", color_hex.strip())
        if not match:
            raise ValueError("颜色色值须为 #RRGGBB 或 #RRGGBBAA")
        channels = [int(match.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        rgb = tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                    for c in channels)
        alpha = int(match.group(2), 16) / 255 if match.group(2) else 1.0
        color = (*rgb, alpha)
    else:
        color = tuple(config["color_rgba"])
    material.diffuse_color = color
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    if shader:
        shader.inputs["Base Color"].default_value = color
        shader.inputs["Roughness"].default_value = 0.8
    for index, existing in enumerate(obj.data.materials):
        if existing == material:
            return index
    obj.data.materials.append(material)
    return len(obj.data.materials) - 1


def apply_plate_marks(cloth=None, config=None):
    config = dict(PLATES_CONFIG if config is None else config)
    for key in ("front_distance_mm", "rear_distance_mm"):
        if float(config[key]) < 0:
            raise ValueError(f"{key} 不能小于零")
    for key in ("length_mm", "width_mm"):
        if float(config[key]) <= 0:
            raise ValueError(f"{key} 必须大于零")
    axis = config["front_axis"].upper()
    if axis not in ("-X", "+X", "-Y", "+Y"):
        raise ValueError("front_axis 必须是 ±X 或 ±Y")
    longitudinal = 0 if axis.endswith("X") else 1
    transverse = 1 - longitudinal
    cloth = cloth or _active_cloth()
    faces = _top_faces(cloth)
    world = _world_vertices(cloth)
    indices = {i for face in faces for i in face.vertices}
    positions = [world[i][longitudinal] for i in indices]
    cross_positions = [world[i][transverse] for i in indices]
    low, high = min(positions), max(positions)
    front = high if axis.startswith("+") else low
    rear = low if axis.startswith("+") else high
    direction = -1 if axis.startswith("+") else 1
    mid_cross = (min(cross_positions) + max(cross_positions)) / 2
    half_length = float(config["length_mm"]) / 2000
    half_width = float(config["width_mm"]) / 2000
    # The UI distance is an edge gap, rather than a distance to the center.
    centers = [
        front + direction * (float(config["front_distance_mm"]) / 1000 + half_length),
    ]
    if not config.get("front_only", False):
        centers.append(
            rear - direction * (float(config["rear_distance_mm"]) / 1000 + half_length)
        )
    for center in centers:
        if center - half_length < low or center + half_length > high:
            raise ValueError("矩形超出 PANEL_TOP 前后范围；请调整距离或长度")
    if mid_cross - half_width < min(cross_positions) or mid_cross + half_width > max(cross_positions):
        raise ValueError("矩形宽度超出 PANEL_TOP 横向范围")

    marks = []
    for center in centers:
        selected = {
            face.index for face in faces
            if min(world[i][longitudinal] for i in face.vertices) <= center + half_length
            and max(world[i][longitudinal] for i in face.vertices) >= center - half_length
            and min(world[i][transverse] for i in face.vertices) <= mid_cross + half_width
            and max(world[i][transverse] for i in face.vertices) >= mid_cross - half_width
        }
        if not selected:
            raise RuntimeError("矩形没有覆盖布料面；请增大长宽或检查车头方向")
        marks.append(selected)

    slot = _material_slot(cloth, config)
    old_slot = cloth.get(SLOT_KEY)
    if isinstance(old_slot, int) and old_slot < len(cloth.data.materials):
        old_faces = {int(i) for i in cloth.get(FACES_KEY, "").split(",") if i.isdigit()}
        fallback = next((i for i in range(len(cloth.data.materials)) if i != old_slot), None)
        if fallback is None:
            base = bpy.data.materials.new("CC Cloth Base")
            cloth.data.materials.append(base)
            fallback = len(cloth.data.materials) - 1
        for index in old_faces:
            if index < len(cloth.data.polygons) and cloth.data.polygons[index].material_index == old_slot:
                cloth.data.polygons[index].material_index = fallback
    marked = set().union(*marks)
    for index in marked:
        cloth.data.polygons[index].material_index = slot
    cloth[SLOT_KEY] = slot
    cloth[FACES_KEY] = ",".join(map(str, sorted(marked)))
    cloth["cc_plates_front_distance_mm"] = float(config["front_distance_mm"])
    cloth["cc_plates_rear_distance_mm"] = float(config["rear_distance_mm"])
    cloth["cc_plates_length_mm"] = float(config["length_mm"])
    cloth["cc_plates_width_mm"] = float(config["width_mm"])
    cloth["cc_plates_front_only"] = bool(config.get("front_only", False))
    cloth.data.update()
    counts = f"{len(marks[0])} front faces"
    if len(marks) > 1:
        counts += f", {len(marks[1])} rear faces"
    print(f"Plate opening mockups: {counts}")
    return marks


class CC_OT_setup_plates_maker(bpy.types.Operator):
    bl_idname = "cc.setup_plates_maker"
    bl_label = "车牌开孔模拟标记"
    bl_options = {"REGISTER", "UNDO"}

    def draw(self, context):
        wm = context.window_manager
        self.layout.prop(wm, "cc_plates_front_axis")
        self.layout.prop(wm, "cc_plates_front_only")
        self.layout.prop(wm, "cc_plates_front_distance_mm")
        if not wm.cc_plates_front_only:
            self.layout.prop(wm, "cc_plates_rear_distance_mm")
        for name in ("length_mm", "width_mm"):
            self.layout.prop(wm, "cc_plates_" + name)
        self.layout.prop(wm, "cc_plates_color_hex")

    def execute(self, context):
        wm = context.window_manager
        config = dict(PLATES_CONFIG)
        for name in ("front_axis", "front_distance_mm", "rear_distance_mm", "length_mm", "width_mm"):
            config[name] = getattr(wm, "cc_plates_" + name)
        config["front_only"] = wm.cc_plates_front_only
        config["color_hex"] = wm.cc_plates_color_hex
        try:
            marks = apply_plate_marks(config=config)
        except (RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        marked = set().union(*marks)
        label = "车头矩形" if len(marks) == 1 else "前后两个矩形"
        self.report({"INFO"}, f"已标记{label}，共 {len(marked)} 个面")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)


def launch_plates_dialog():
    previous = getattr(bpy.types, CC_OT_setup_plates_maker.__name__, None)
    if previous is not None:
        bpy.utils.unregister_class(previous)
    wm = bpy.types.WindowManager
    wm.cc_plates_front_axis = bpy.props.EnumProperty(
        name="车头方向", items=(("-Y", "-Y", ""), ("+Y", "+Y", ""),
                              ("-X", "-X", ""), ("+X", "+X", "")),
        default=PLATES_CONFIG["front_axis"],
    )
    wm.cc_plates_front_only = bpy.props.BoolProperty(
        name="仅添加车头矩形",
        description="启用后不添加车尾矩形",
        default=PLATES_CONFIG["front_only"],
    )
    for key, label in (
        ("front_distance_mm", "车头端净距 (mm)"),
        ("rear_distance_mm", "车尾端净距 (mm)"),
        ("length_mm", "矩形长度 (mm)"),
        ("width_mm", "矩形宽度 (mm)"),
    ):
        setattr(wm, "cc_plates_" + key, bpy.props.FloatProperty(
            name=label,
            min=0.0 if "distance" in key else 1.0,
            default=PLATES_CONFIG[key],
        ))
    wm.cc_plates_color_hex = bpy.props.StringProperty(
        name="颜色色值", description="十六进制颜色，例如 #FF6600", default=PLATES_CONFIG["color_hex"])
    bpy.utils.register_class(CC_OT_setup_plates_maker)
    if bpy.app.background:
        return apply_plate_marks()
    return bpy.ops.cc.setup_plates_maker("INVOKE_DEFAULT")


if __name__ == "__main__":
    launch_plates_dialog()
