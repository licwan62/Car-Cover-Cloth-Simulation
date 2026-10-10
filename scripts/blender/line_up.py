import bpy
from mathutils import Vector


# ============================================================
# 工具函数
# ============================================================

def get_world_bbox(obj):
    """获取物体世界坐标下的 Bounding Box"""
    corners = [
        obj.matrix_world @ Vector(corner)
        for corner in obj.bound_box
    ]

    min_v = Vector((
        min(v.x for v in corners),
        min(v.y for v in corners),
        min(v.z for v in corners),
    ))

    max_v = Vector((
        max(v.x for v in corners),
        max(v.y for v in corners),
        max(v.z for v in corners),
    ))

    size = max_v - min_v
    center = (min_v + max_v) * 0.5

    return min_v, max_v, size, center


def get_length(obj, mode):
    """取得用于排序的长度"""
    _, _, size, _ = get_world_bbox(obj)

    if mode == 'X':
        return size.x

    elif mode == 'Y':
        return size.y

    elif mode == 'Z':
        return size.z

    elif mode == 'MAX':
        return max(size.x, size.y, size.z)

    return size.x


def move_world(obj, offset):
    """按世界坐标移动物体"""
    matrix = obj.matrix_world.copy()
    matrix.translation += offset
    obj.matrix_world = matrix


# ============================================================
# 参数记忆（保存在场景自定义属性中，随 .blend 一起保存）
# ============================================================

SETTINGS_KEY = "sort_arrange_settings"

REMEMBERED_PROPS = (
    "spacing",
    "sort_dimension",
    "arrange_axis",
    "ascending",
    "reverse_direction",
    "align_mode",
    "ground_to_zero",
)


def load_settings(op, scene):
    """从场景读取上次输入的参数"""
    stored = scene.get(SETTINGS_KEY)
    if not stored:
        return

    for name in REMEMBERED_PROPS:
        if name in stored:
            try:
                setattr(op, name, stored[name])
            except (TypeError, ValueError):
                pass


def save_settings(op, scene):
    """把本次输入的参数写入场景"""
    scene[SETTINGS_KEY] = {
        name: getattr(op, name)
        for name in REMEMBERED_PROPS
    }


def axis_index(axis):
    return {
        'X': 0,
        'Y': 1,
        'Z': 2,
    }[axis]


# ============================================================
# Operator
# ============================================================

class OBJECT_OT_sort_arrange(bpy.types.Operator):

    bl_idname = "object.sort_arrange_selected"
    bl_label = "按长度排序并排列"
    bl_options = {'REGISTER', 'UNDO'}


    spacing: bpy.props.FloatProperty(
        name="间距",
        description="物体边缘之间的实际间距",
        default=0.2,
        min=0.0,
        unit='LENGTH'
    )


    sort_dimension: bpy.props.EnumProperty(
        name="长度依据",
        items=[
            ('X', "X 长度", ""),
            ('Y', "Y 长度", ""),
            ('Z', "Z 长度", ""),
            ('MAX', "最长边", ""),
        ],
        default='MAX'
    )


    arrange_axis: bpy.props.EnumProperty(
        name="排列方向",
        items=[
            ('X', "X 轴", ""),
            ('Y', "Y 轴", ""),
            ('Z', "Z 轴", ""),
        ],
        default='X'
    )


    ascending: bpy.props.BoolProperty(
        name="从小到大",
        description="开启：小 → 大；关闭：大 → 小",
        default=True
    )


    reverse_direction: bpy.props.BoolProperty(
        name="反向排列",
        description="沿坐标轴负方向排列",
        default=False
    )


    align_mode: bpy.props.EnumProperty(
        name="对齐方式",
        items=[
            ('CENTER', "居中对齐", ""),
            ('MIN', "最小边对齐", ""),
            ('MAX', "最大边对齐", ""),
        ],
        default='CENTER'
    )


    ground_to_zero: bpy.props.BoolProperty(
        name="底部对齐到 Z=0",
        description="所有物体底部对齐，并把底面放到 Z=0（覆盖 Z 方向的对齐方式）",
        default=False
    )


    def invoke(self, context, event):
        load_settings(self, context.scene)

        return context.window_manager.invoke_props_dialog(
            self,
            width=400
        )


    def draw(self, context):

        layout = self.layout

        layout.prop(self, "sort_dimension")
        layout.prop(self, "ascending")

        layout.separator()

        layout.prop(self, "arrange_axis")
        layout.prop(self, "reverse_direction")
        layout.prop(self, "spacing")

        layout.separator()

        layout.prop(self, "align_mode")
        layout.prop(self, "ground_to_zero")


    def execute(self, context):

        objects = [
            obj
            for obj in context.selected_objects
            if hasattr(obj, "bound_box")
            and obj.type != 'EMPTY'
        ]

        if len(objects) < 2:
            self.report(
                {'WARNING'},
                "至少选择两个物体"
            )
            return {'CANCELLED'}


        # ====================================================
        # 按长度排序
        # ====================================================

        objects.sort(
            key=lambda obj: get_length(
                obj,
                self.sort_dimension
            ),
            reverse=not self.ascending
        )


        arrange_idx = axis_index(
            self.arrange_axis
        )


        # ====================================================
        # 获取整个选择区域
        # ====================================================

        bounds = [
            get_world_bbox(obj)
            for obj in objects
        ]


        global_min = Vector((
            min(b[0].x for b in bounds),
            min(b[0].y for b in bounds),
            min(b[0].z for b in bounds),
        ))


        global_max = Vector((
            max(b[1].x for b in bounds),
            max(b[1].y for b in bounds),
            max(b[1].z for b in bounds),
        ))


        global_center = (
            global_min + global_max
        ) * 0.5


        # ====================================================
        # 设置排列起点
        # ====================================================

        if self.reverse_direction:
            cursor = global_max[arrange_idx]
        else:
            cursor = global_min[arrange_idx]


        # 沿 Z 轴堆叠时，底部落地 = 整摞最底端放到 Z=0
        if self.ground_to_zero and arrange_idx == 2:

            if self.reverse_direction:
                cursor = (
                    sum(b[2].z for b in bounds)
                    + self.spacing * (len(objects) - 1)
                )
            else:
                cursor = 0.0


        # ====================================================
        # 逐个物体排列
        # ====================================================

        for obj in objects:

            min_v, max_v, size, center = \
                get_world_bbox(obj)


            offset = Vector(
                (0.0, 0.0, 0.0)
            )


            # ------------------------------------------------
            # 排列轴
            # ------------------------------------------------

            if not self.reverse_direction:

                offset[arrange_idx] = (
                    cursor
                    - min_v[arrange_idx]
                )

                cursor += (
                    size[arrange_idx]
                    + self.spacing
                )

            else:

                offset[arrange_idx] = (
                    cursor
                    - max_v[arrange_idx]
                )

                cursor -= (
                    size[arrange_idx]
                    + self.spacing
                )


            # ------------------------------------------------
            # 另外两个轴进行对齐
            # ------------------------------------------------

            for i in range(3):

                if i == arrange_idx:
                    continue


                if self.align_mode == 'CENTER':

                    offset[i] = (
                        global_center[i]
                        - center[i]
                    )


                elif self.align_mode == 'MIN':

                    offset[i] = (
                        global_min[i]
                        - min_v[i]
                    )


                elif self.align_mode == 'MAX':

                    offset[i] = (
                        global_max[i]
                        - max_v[i]
                    )


                # 底部对齐到 Z=0（覆盖 Z 轴的对齐方式）
                if self.ground_to_zero and i == 2:

                    offset[i] = -min_v[i]


            # ------------------------------------------------
            # 移动物体
            # ------------------------------------------------

            move_world(
                obj,
                offset
            )


        save_settings(self, context.scene)

        self.report(
            {'INFO'},
            f"已排列 {len(objects)} 个物体"
        )

        return {'FINISHED'}


# ============================================================
# 注册并运行
# ============================================================

try:
    bpy.utils.unregister_class(
        OBJECT_OT_sort_arrange
    )
except:
    pass


bpy.utils.register_class(
    OBJECT_OT_sort_arrange
)


bpy.ops.object.sort_arrange_selected(
    'INVOKE_DEFAULT'
)