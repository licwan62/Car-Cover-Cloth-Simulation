import bpy
import os
import shutil
import base64

from mathutils import Vector, Matrix
from xml.sax.saxutils import escape as xml_escape


# ============================================================
# CONFIG
# ============================================================

# ------------------------------------------------------------
# SVG最终物理尺寸
#
# 关键：
#
# width  = 10000mm
# height = 10000mm
# viewBox = 0 0 10000 10000
#
# 因此：
#
# 1 SVG unit = 1 mm
# ------------------------------------------------------------

SHEET_W_MM = 10000.0
SHEET_H_MM = 10000.0


# ------------------------------------------------------------
# PNG清晰度
#
# 只控制PNG采样。
#
# 不影响SVG真实尺寸。
#
# 0.25 = 4mm / px
# 0.50 = 2mm / px
# 1.00 = 1mm / px
# ------------------------------------------------------------

RASTER_PX_PER_MM = 0.125


# ------------------------------------------------------------
# SVG组图Margin
#
# 注意：
#
# PNG本身完全没有Margin。
#
# 这些只负责最终SVG排版。
# ------------------------------------------------------------

LEFT_MARGIN_MM = 250.0
RIGHT_MARGIN_MM = 250.0
TOP_MARGIN_MM = 250.0
BOTTOM_MARGIN_MM = 250.0

VERTICAL_GAP_MM = 400.0

# LEFT 固定左边距、FRONT 固定右边距，横向 gap 使用两图之间的剩余空间。
# 图片变宽时 gap 会自动缩小；只有 gap 小于 0（两图重叠）才报错。
MIN_HORIZONTAL_GAP_MM = 0.0


# ------------------------------------------------------------
# 纵向排版宽松度
#
# 1.50 = 纵向留白为基础值的150%。
#
# 只放大标题与视图、两行视图之间的空白，
# 不缩放车辆图片，也不改变真实尺寸。
# ------------------------------------------------------------

VERTICAL_LOOSENESS = 1.50


# ------------------------------------------------------------
# 标题行
# ------------------------------------------------------------

TITLE_ROW_HEIGHT_MM = 180.0
TITLE_TO_VIEWS_GAP_MM = 160.0

TITLE_FONT = 100
TITLE_COLOR = "#111827"
TITLE_DIVIDER_COLOR = "#9ca3af"


# ------------------------------------------------------------
# 拍摄方向
#
# LEFT拍成右侧：
# -1 ↔ +1
#
# FRONT拍成车尾：
# -1 ↔ +1
# ------------------------------------------------------------

LEFT_SIGN = -1
FRONT_SIGN = -1


# ------------------------------------------------------------
# Workbench
# ------------------------------------------------------------

WORKBENCH_COLOR_TYPE = 'TEXTURE'

TRANSPARENT_PNG = True

PNG_COMPRESSION = 100

WORKBENCH_AA = '32'


# ------------------------------------------------------------
# 输出目录
# ------------------------------------------------------------

OUTPUT_FOLDER = "MEASURE_VIEWS"


# ============================================================
# ACTIVE OBJECT
# ============================================================

obj = bpy.context.active_object


if obj is None:
    raise RuntimeError(
        "当前没有 Active Object"
    )


if obj.type != 'MESH':
    raise RuntimeError(
        "当前 Active Object 不是 Mesh"
    )


scene = bpy.context.scene

bpy.context.view_layer.update()


# ============================================================
# SAFE MODEL NAME
# ============================================================

invalid_chars = '<>:"/\\|?*'


safe_name = "".join(

    "_"
    if (
        c in invalid_chars
        or ord(c) < 32
    )
    else c

    for c in obj.name

)


safe_name = safe_name.strip().strip(".")


if safe_name in (
    "",
    ".",
    ".."
):
    safe_name = "CAR_MEASURE"


# 标题显示原始物体名；转义XML特殊字符，避免SVG导入失败。
title_text = xml_escape(obj.name)


# ============================================================
# EVALUATED WORLD BOUNDING BOX
#
# 必须使用依赖图求值后的对象，否则 Array / Mirror / Geometry Nodes
# 等修改器产生的最终渲染几何可能与标识框使用的包围盒不一致。
# ============================================================

depsgraph = bpy.context.evaluated_depsgraph_get()


evaluated_obj = obj.evaluated_get(
    depsgraph
)


bbox_world = [

    evaluated_obj.matrix_world @ Vector(corner)

    for corner in evaluated_obj.bound_box

]


xs = [p.x for p in bbox_world]
ys = [p.y for p in bbox_world]
zs = [p.z for p in bbox_world]


min_x = min(xs)
max_x = max(xs)

min_y = min(ys)
max_y = max(ys)

min_z = min(zs)
max_z = max(zs)


dim_x = max_x - min_x
dim_y = max_y - min_y
dim_z = max_z - min_z


center = Vector((

    (min_x + max_x) / 2.0,

    (min_y + max_y) / 2.0,

    (min_z + max_z) / 2.0

))


# ============================================================
# BLENDER UNIT <-> MM
# ============================================================

scale_length = scene.unit_settings.scale_length


if not scale_length:
    scale_length = 1.0


def bu_to_mm(value):

    return (
        value
        * scale_length
        * 1000.0
    )


def mm_to_bu(value):

    return (
        value
        / 1000.0
        / scale_length
    )


x_mm = bu_to_mm(dim_x)
y_mm = bu_to_mm(dim_y)
z_mm = bu_to_mm(dim_z)


# ============================================================
# VEHICLE AXIS
#
# 默认：
#
# Z = Height
#
# X / Y：
#
# 长轴 = Length
# 短轴 = Width
# ============================================================

if dim_x >= dim_y:

    length_axis = 'X'

    length_mm = x_mm
    width_mm = y_mm

else:

    length_axis = 'Y'

    length_mm = y_mm
    width_mm = x_mm


height_mm = z_mm


# ============================================================
# EXACT VIEW SIZE
#
# PNG没有任何Margin。
#
#
# LEFT
# =
# Length × Height
#
#
# FRONT
# =
# Width × Height
#
#
# TOP
# =
# Length × Width
# ============================================================

left_svg_w = length_mm
left_svg_h = height_mm


front_svg_w = width_mm
front_svg_h = height_mm


top_svg_w = length_mm
top_svg_h = width_mm


# ============================================================
# PNG RASTER SIZE
#
# PNG只是采样。
#
# SVG真实尺寸不受像素取整影响。
# ============================================================

def raster_size(
    real_width_mm,
    real_height_mm
):

    width_px = max(
        2,
        int(
            round(
                real_width_mm
                * RASTER_PX_PER_MM
            )
        )
    )


    height_px = max(
        2,
        int(
            round(
                real_height_mm
                * RASTER_PX_PER_MM
            )
        )
    )


    return (
        width_px,
        height_px
    )


left_png_w, left_png_h = raster_size(
    left_svg_w,
    left_svg_h
)


front_png_w, front_png_h = raster_size(
    front_svg_w,
    front_svg_h
)


top_png_w, top_png_h = raster_size(
    top_svg_w,
    top_svg_h
)


# ============================================================
# SVG LAYOUT
#
#
# 0                                                10000
#
#      LEFT                            FRONT
#
#      █████████████████               ███████
#      █████████████████               ███████
#      █████████████████               ███████
#
#
#      TOP
#
#      █████████████████
#      █████████████████
#
#
# FRONT：
#
# right =
# 10000 - RIGHT_MARGIN
#
# 不参考LEFT来计算FRONT X。
# ============================================================

effective_vertical_gap = (
    VERTICAL_GAP_MM
    * VERTICAL_LOOSENESS
)


effective_title_gap = (
    TITLE_TO_VIEWS_GAP_MM
    * VERTICAL_LOOSENESS
)


title_x = SHEET_W_MM / 2.0
title_top = TOP_MARGIN_MM
title_baseline_y = (
    title_top
    + TITLE_FONT
)
title_bottom = (
    title_top
    + TITLE_ROW_HEIGHT_MM
)


# ============================================================
# LEFT
# ============================================================

left_x = LEFT_MARGIN_MM
left_y = (
    title_bottom
    + effective_title_gap
)


left_right = (
    left_x
    + left_svg_w
)


left_bottom = (
    left_y
    + left_svg_h
)


# ============================================================
# FRONT
#
# 最关键：
#
# FRONT右边界固定。
# ============================================================

front_right = (
    SHEET_W_MM
    - RIGHT_MARGIN_MM
)


front_x = (
    front_right
    - front_svg_w
)


# ------------------------------------------------------------
# LEFT和FRONT高度本来就完全一样
#
# 所以直接：
#
# front_y = left_y
#
# 不再通过bottom倒算。
# ------------------------------------------------------------

front_y = left_y


front_bottom = (
    front_y
    + front_svg_h
)


# ============================================================
# TOP
#
# TOP与LEFT左侧严格对齐
# ============================================================

top_x = left_x


top_y = (
    left_bottom
    + effective_vertical_gap
)


top_right = (
    top_x
    + top_svg_w
)


top_bottom = (
    top_y
    + top_svg_h
)


# ============================================================
# STRICT VALIDATION
# ============================================================

EPS = 0.001


if VERTICAL_LOOSENESS < 1.0:

    raise RuntimeError(
        "VERTICAL_LOOSENESS 不能小于 1.0"
    )


# ------------------------------------------------------------
# LEFT / FRONT高度必须相同
# ------------------------------------------------------------

if abs(
    left_svg_h
    - front_svg_h
) > EPS:

    raise RuntimeError(
        "LEFT / FRONT 高度不一致"
    )


# ------------------------------------------------------------
# LEFT / FRONT顶部必须相同
# ------------------------------------------------------------

if abs(
    left_y
    - front_y
) > EPS:

    raise RuntimeError(
        "LEFT / FRONT 顶部对齐失败"
    )


# ------------------------------------------------------------
# LEFT / FRONT底部必须相同
# ------------------------------------------------------------

if abs(
    left_bottom
    - front_bottom
) > EPS:

    raise RuntimeError(
        "LEFT / FRONT 底部对齐失败"
    )


# ------------------------------------------------------------
# FRONT实际右边界
# ------------------------------------------------------------

front_right_actual = (
    front_x
    + front_svg_w
)


front_right_expected = (
    SHEET_W_MM
    - RIGHT_MARGIN_MM
)


if abs(
    front_right_actual
    - front_right_expected
) > EPS:

    raise RuntimeError(

        "\nFRONT RIGHT ERROR\n\n"

        f"Actual = "
        f"{front_right_actual:.3f}\n"

        f"Expected = "
        f"{front_right_expected:.3f}"

    )


# ------------------------------------------------------------
# FRONT右Margin
# ------------------------------------------------------------

actual_right_margin = (
    SHEET_W_MM
    - front_right_actual
)


if abs(
    actual_right_margin
    - RIGHT_MARGIN_MM
) > EPS:

    raise RuntimeError(

        "\nFRONT RIGHT MARGIN ERROR\n\n"

        f"Actual = "
        f"{actual_right_margin:.3f}\n"

        f"Expected = "
        f"{RIGHT_MARGIN_MM:.3f}"

    )


# ------------------------------------------------------------
# LEFT / FRONT Gap
# ------------------------------------------------------------

actual_horizontal_gap = (
    front_x
    - left_right
)


if actual_horizontal_gap < MIN_HORIZONTAL_GAP_MM - EPS:

    required_width = (

        LEFT_MARGIN_MM

        + left_svg_w

        + MIN_HORIZONTAL_GAP_MM

        + front_svg_w

        + RIGHT_MARGIN_MM

    )


    raise RuntimeError(

        "\nSVG横向空间不足\n\n"

        f"LEFT right = "
        f"{left_right:.2f}\n"

        f"FRONT left = "
        f"{front_x:.2f}\n"

        f"Gap = "
        f"{actual_horizontal_gap:.2f}\n\n"

        f"至少需要画布宽度："
        f"{required_width:.2f}"

    )


# ============================================================
# HARD BOUNDARY VALIDATION
#
# 不使用：
#
# clipPath
# mask
# overflow裁切
#
# 越界直接Python报错。
# ============================================================

def validate_rect(
    name,
    x,
    y,
    width,
    height
):

    right = (
        x + width
    )


    bottom = (
        y + height
    )


    if x < -EPS:

        raise RuntimeError(
            f"{name} 超出左边界"
        )


    if y < -EPS:

        raise RuntimeError(
            f"{name} 超出上边界"
        )


    if right > SHEET_W_MM + EPS:

        raise RuntimeError(

            f"\n{name} 超出右边界\n\n"

            f"x = {x:.2f}\n"

            f"width = {width:.2f}\n"

            f"right = {right:.2f}\n"

            f"canvas = {SHEET_W_MM:.2f}"

        )


    if bottom > SHEET_H_MM + EPS:

        raise RuntimeError(

            f"\n{name} 超出下边界\n\n"

            f"y = {y:.2f}\n"

            f"height = {height:.2f}\n"

            f"bottom = {bottom:.2f}\n"

            f"canvas = {SHEET_H_MM:.2f}"

        )


validate_rect(
    "TITLE ROW",
    LEFT_MARGIN_MM,
    title_top,
    SHEET_W_MM - LEFT_MARGIN_MM - RIGHT_MARGIN_MM,
    TITLE_ROW_HEIGHT_MM
)


validate_rect(
    "LEFT",
    left_x,
    left_y,
    left_svg_w,
    left_svg_h
)


validate_rect(
    "FRONT",
    front_x,
    front_y,
    front_svg_w,
    front_svg_h
)


validate_rect(
    "TOP",
    top_x,
    top_y,
    top_svg_w,
    top_svg_h
)


# ------------------------------------------------------------
# TOP底部Margin
# ------------------------------------------------------------

if (
    top_bottom
    >
    SHEET_H_MM
    - BOTTOM_MARGIN_MM
    + EPS
):

    raise RuntimeError(

        "\nTOP底部Margin不足\n\n"

        f"TOP bottom = "
        f"{top_bottom:.2f}\n"

        f"最大允许 = "
        f"{SHEET_H_MM - BOTTOM_MARGIN_MM:.2f}"

    )


# ============================================================
# DIMENSION ANNOTATIONS
# ============================================================

DIM_OFFSET = 60.0
TICK_LEN = 30.0
DIM_COLOR = "#2563eb"
DIM_FONT = 40

# LEFT view
left_len_y = left_bottom + DIM_OFFSET
left_hgt_x = left_x - DIM_OFFSET

# FRONT view
front_wid_y = front_bottom + DIM_OFFSET
front_hgt_x = front_right + DIM_OFFSET

# TOP view
top_len_y = top_bottom + DIM_OFFSET
top_wid_x = top_right + DIM_OFFSET


# ============================================================
# OUTPUT DIRECTORY
# ============================================================

if bpy.data.filepath:

    base_dir = bpy.path.abspath("//")

else:

    base_dir = os.path.join(
        os.path.expanduser("~"),
        "Desktop"
    )


root_output_dir = os.path.join(
    base_dir,
    OUTPUT_FOLDER
)


os.makedirs(
    root_output_dir,
    exist_ok=True
)


output_dir = os.path.join(
    root_output_dir,
    safe_name
)


# ============================================================
# AUTO OVERWRITE MODEL DIRECTORY
# ============================================================

if os.path.exists(output_dir):

    root_real = os.path.realpath(
        root_output_dir
    )


    output_real = os.path.realpath(
        output_dir
    )


    if os.path.commonpath(
        [
            root_real,
            output_real
        ]
    ) != root_real:

        raise RuntimeError(
            "安全检查失败：拒绝删除目录"
        )


    if output_real == root_real:

        raise RuntimeError(
            "拒绝删除MEASURE_VIEWS根目录"
        )


    shutil.rmtree(
        output_dir
    )


os.makedirs(
    output_dir,
    exist_ok=False
)


# ============================================================
# FILENAMES
# ============================================================

left_filename = (
    f"{safe_name}_LEFT.png"
)


front_filename = (
    f"{safe_name}_FRONT.png"
)


top_filename = (
    f"{safe_name}_TOP.png"
)


svg_filename = (
    f"{safe_name}_THREE_VIEW.svg"
)


left_path = os.path.join(
    output_dir,
    left_filename
)


front_path = os.path.join(
    output_dir,
    front_filename
)


top_path = os.path.join(
    output_dir,
    top_filename
)


svg_path = os.path.join(
    output_dir,
    svg_filename
)


# ============================================================
# DEBUG REPORT
# ============================================================

print("\n")
print("=" * 72)

print("VEHICLE MEASURE EXPORT")

print("=" * 72)


print(
    f"Model: {obj.name}"
)


print(

    f"L × W × H = "

    f"{length_mm:.2f} × "
    f"{width_mm:.2f} × "
    f"{height_mm:.2f} mm"

)


print(
    "\nSVG:"
)


print(
    "Canvas = 10000mm × 10000mm"
)


print(
    "1 SVG unit = 1 mm"
)


print(
    f"Title = {obj.name}"
)


print(
    f"Vertical looseness = "
    f"{VERTICAL_LOOSENESS * 100:.0f}%"
)


print(
    "\nLEFT"
)


print(

    f"x = {left_x:.2f}\n"

    f"y = {left_y:.2f}\n"

    f"w = {left_svg_w:.2f}\n"

    f"h = {left_svg_h:.2f}\n"

    f"right = {left_right:.2f}\n"

    f"bottom = {left_bottom:.2f}"

)


print(
    "\nFRONT"
)


print(

    f"x = {front_x:.2f}\n"

    f"y = {front_y:.2f}\n"

    f"w = {front_svg_w:.2f}\n"

    f"h = {front_svg_h:.2f}\n"

    f"bottom = {front_bottom:.2f}"

)


print(
    "\nFRONT RIGHT-ALIGNMENT CHECK"
)


print(

    f"  right edge actual = "
    f"{front_right_actual:.3f} mm\n"

    f"  right edge expect = "
    f"{SHEET_W_MM - RIGHT_MARGIN_MM:.3f} mm\n"

    f"  right margin = "
    f"{actual_right_margin:.3f} mm\n"

    f"  delta = "
    f"{abs(front_right_actual - (SHEET_W_MM - RIGHT_MARGIN_MM)):.6f} mm"
)


if abs(
    front_right_actual
    - (SHEET_W_MM - RIGHT_MARGIN_MM)
) <= EPS:

    print(
        "  → FRONT 右对齐 OK"
    )


print(
    "\nTOP"
)


print(

    f"x = {top_x:.2f}\n"

    f"y = {top_y:.2f}\n"

    f"w = {top_svg_w:.2f}\n"

    f"h = {top_svg_h:.2f}\n"

    f"right = {top_right:.2f}\n"

    f"bottom = {top_bottom:.2f}"

)


print("=" * 72)


# ============================================================
# BACKUP RENDER SETTINGS
# ============================================================

render = scene.render
img_set = render.image_settings
shading = scene.display.shading

backup = {
    "camera": scene.camera,

    "engine": render.engine,

    "res_x": render.resolution_x,
    "res_y": render.resolution_y,
    "res_pct": render.resolution_percentage,

    "pixel_x": render.pixel_aspect_x,
    "pixel_y": render.pixel_aspect_y,

    "filepath": render.filepath,
    "film": render.film_transparent,

    "format": img_set.file_format,
    "color_mode": img_set.color_mode,
    "color_depth": img_set.color_depth,
    "compression": img_set.compression,

    "shading_light": shading.light,
    "shading_color_type": shading.color_type,
    "shading_bg_type": shading.background_type,
    "shading_bg_color": tuple(shading.background_color),
    "shading_single_color": tuple(shading.single_color),
    "shading_shadows": shading.show_shadows,
    "shading_cavity": shading.show_cavity,

    "render_aa": (
        scene.display.render_aa
        if hasattr(scene.display, "render_aa")
        else None
    ),
}


# ============================================================
# TEMP CAMERA
# ============================================================

camera_data = bpy.data.cameras.new(
    "__MEASURE_CAMERA"
)


camera = bpy.data.objects.new(

    "__MEASURE_CAMERA",

    camera_data

)


scene.collection.objects.link(
    camera
)


scene.camera = camera


camera.data.type = 'ORTHO'

camera.data.sensor_fit = 'HORIZONTAL'


camera.data.clip_start = 0.0001


camera.data.clip_end = max(

    10000.0,

    max(
        dim_x,
        dim_y,
        dim_z
    ) * 20.0

)


camera.data.shift_x = 0.0
camera.data.shift_y = 0.0


# ============================================================
# CAMERA ORIENTATION
# ============================================================

def orient_camera(
    cam,
    target,
    image_up_world
):

    direction = (
        target
        - cam.location
    ).normalized()


    z_axis = (
        -direction
    )


    up = (
        image_up_world.normalized()
    )


    y_axis = (

        up
        - z_axis
        * up.dot(z_axis)

    )


    if y_axis.length < 0.000001:

        raise RuntimeError(
            "Camera Up Axis与拍摄方向平行"
        )


    y_axis.normalize()


    x_axis = (

        y_axis.cross(
            z_axis
        )

    ).normalized()


    y_axis = (

        z_axis.cross(
            x_axis
        )

    ).normalized()


    rotation_matrix = Matrix((

        x_axis,
        y_axis,
        z_axis

    )).transposed()


    cam.rotation_euler = (
        rotation_matrix.to_euler()
    )


# ============================================================
# WORKBENCH
# ============================================================

try:
    render.engine = 'BLENDER_WORKBENCH'
except:
    pass


try:
    shading.light = 'STUDIO'

    try:
        shading.color_type = WORKBENCH_COLOR_TYPE
    except:
        shading.color_type = 'MATERIAL'

    shading.background_type = 'VIEWPORT'
    shading.background_color = (1.0, 1.0, 1.0)
    shading.single_color = (0.45, 0.45, 0.45)
    shading.show_shadows = True
    shading.show_cavity = True

except:
    pass


try:
    scene.display.render_aa = WORKBENCH_AA
except:
    pass


# ============================================================
# PNG
# ============================================================

img_set.file_format = 'PNG'

img_set.color_depth = '8'

img_set.compression = PNG_COMPRESSION


if TRANSPARENT_PNG:

    render.film_transparent = True

    img_set.color_mode = 'RGBA'

else:

    render.film_transparent = False

    img_set.color_mode = 'RGB'


# ============================================================
# HIDE EVERYTHING EXCEPT MODEL
# ============================================================

hide_status = {}


for other in scene.objects:

    if (
        other == obj
        or other == camera
    ):
        continue


    hide_status[other] = (
        other.hide_render
    )


    other.hide_render = True


obj_hide_original = (
    obj.hide_render
)


obj.hide_render = False


# ============================================================
# CAMERA DISTANCE
# ============================================================

distance = (

    max(
        dim_x,
        dim_y,
        dim_z
    )

    * 4.0

)


# ============================================================
# EXACT CAMERA VIEW
# ============================================================

def configure_view(
    png_width,
    png_height,
    real_width_mm,
    real_height_mm
):

    render.resolution_x = int(png_width)
    render.resolution_y = int(png_height)
    render.resolution_percentage = 100

    camera.data.sensor_fit = 'HORIZONTAL'

    camera.data.ortho_scale = mm_to_bu(real_width_mm)


    # --------------------------------------------------------
    # PNG整数像素宽高比补偿
    #
    # 保证Camera真实范围严格：
    #
    # real_width × real_height
    # --------------------------------------------------------

    render.pixel_aspect_x = 1.0

    render.pixel_aspect_y = (

        real_height_mm
        * png_width

        /

        (
            real_width_mm
            * png_height
        )

    )


def render_view(
    filepath,
    png_width,
    png_height,
    real_width_mm,
    real_height_mm
):

    configure_view(
        png_width, png_height,
        real_width_mm, real_height_mm
    )

    render.filepath = filepath

    bpy.ops.render.render(write_still=True)


# ============================================================
# RENDER
# ============================================================

try:

    # --------------------------------------------------------
    # LEFT
    # --------------------------------------------------------

    if length_axis == 'X':

        camera.location = Vector((

            center.x,

            center.y
            + distance
            * LEFT_SIGN,

            center.z

        ))

    else:

        camera.location = Vector((

            center.x
            + distance
            * LEFT_SIGN,

            center.y,

            center.z

        ))


    orient_camera(

        camera,

        center,

        Vector((
            0.0,
            0.0,
            1.0
        ))

    )


    render_view(

        left_path,

        left_png_w,
        left_png_h,

        left_svg_w,
        left_svg_h

    )


    # --------------------------------------------------------
    # FRONT
    # --------------------------------------------------------

    if length_axis == 'X':

        camera.location = Vector((

            center.x
            + distance
            * FRONT_SIGN,

            center.y,

            center.z

        ))

    else:

        camera.location = Vector((

            center.x,

            center.y
            + distance
            * FRONT_SIGN,

            center.z

        ))


    orient_camera(

        camera,

        center,

        Vector((
            0.0,
            0.0,
            1.0
        ))

    )


    render_view(

        front_path,

        front_png_w,
        front_png_h,

        front_svg_w,
        front_svg_h

    )


    # --------------------------------------------------------
    # TOP
    # --------------------------------------------------------

    camera.location = Vector((

        center.x,

        center.y,

        center.z
        + distance

    ))


    if length_axis == 'X':

        top_image_up = Vector((
            0.0,
            1.0,
            0.0
        ))

    else:

        top_image_up = Vector((
            1.0,
            0.0,
            0.0
        ))


    orient_camera(

        camera,

        center,

        top_image_up

    )


    render_view(

        top_path,

        top_png_w,
        top_png_h,

        top_svg_w,
        top_svg_h

    )


finally:

    # --------------------------------------------------------
    # Restore visibility
    # --------------------------------------------------------

    for other, value in hide_status.items():
        other.hide_render = value

    obj.hide_render = obj_hide_original


    # --------------------------------------------------------
    # Restore render settings
    # --------------------------------------------------------

    try:
        render.engine = backup["engine"]
    except:
        pass

    scene.camera = backup["camera"]

    render.resolution_x = backup["res_x"]
    render.resolution_y = backup["res_y"]
    render.resolution_percentage = backup["res_pct"]

    render.pixel_aspect_x = backup["pixel_x"]
    render.pixel_aspect_y = backup["pixel_y"]

    render.filepath = backup["filepath"]
    render.film_transparent = backup["film"]

    img_set.file_format = backup["format"]
    img_set.color_mode = backup["color_mode"]
    img_set.color_depth = backup["color_depth"]
    img_set.compression = backup["compression"]

    try:
        shading.light = backup["shading_light"]
        shading.color_type = backup["shading_color_type"]
        shading.background_type = backup["shading_bg_type"]
        shading.background_color = backup["shading_bg_color"]
        shading.single_color = backup["shading_single_color"]
        shading.show_shadows = backup["shading_shadows"]
        shading.show_cavity = backup["shading_cavity"]
    except:
        pass

    if backup["render_aa"] is not None:
        try:
            scene.display.render_aa = backup["render_aa"]
        except:
            pass

    if camera.name in bpy.data.objects:
        bpy.data.objects.remove(camera, do_unlink=True)

    if camera_data.name in bpy.data.cameras:
        bpy.data.cameras.remove(camera_data, do_unlink=True)


# ============================================================
# VERIFY PNG
# ============================================================

for path in [
    left_path,
    front_path,
    top_path
]:

    if not os.path.exists(path):

        raise RuntimeError(
            "PNG渲染失败：\n"
            + path
        )


# ============================================================
# BASE64 EMBED PNG
# ============================================================

def png_to_data_uri(filepath):

    with open(filepath, "rb") as f:
        raw = f.read()

    b64 = base64.b64encode(raw).decode("ascii")

    return f"data:image/png;base64,{b64}"


left_data_uri = png_to_data_uri(left_path)
front_data_uri = png_to_data_uri(front_path)
top_data_uri = png_to_data_uri(top_path)


# ============================================================
# SVG
#
# 重要：
#
# 恢复：
#
# width="10000mm"
# height="10000mm"
#
# 不再使用：
#
# width="10000"
# width="10000px"
#
#
# 不使用：
#
# clipPath
# mask
# overflow
#
#
# 所有内部坐标均为viewBox user units。
#
# 因为：
#
# viewport = 10000mm
# viewBox  = 10000
#
# 所以：
#
# 1 user unit = 1mm
# ============================================================

svg = f'''<?xml version="1.0" encoding="UTF-8"?>

<svg
    xmlns="http://www.w3.org/2000/svg"
    xmlns:xlink="http://www.w3.org/1999/xlink"

    version="1.1"

    width="{SHEET_W_MM:.0f}mm"
    height="{SHEET_H_MM:.0f}mm"

    viewBox="0 0 {SHEET_W_MM:.0f} {SHEET_H_MM:.0f}"
>

    <!-- ================================================
         BACKGROUND
         ================================================ -->

    <rect
        id="BACKGROUND"

        x="0"
        y="0"

        width="{SHEET_W_MM:.0f}"
        height="{SHEET_H_MM:.0f}"

        fill="#ffffff"
    />


    <!-- ================================================
         DEBUG: MARGIN / BOUNDARY GUIDES
         ================================================ -->

    <g
        id="DEBUG_GUIDES"

        fill="none"
        stroke="#cccccc"
        stroke-width="1"
        stroke-dasharray="8,4"
    >

        <!-- Left margin boundary -->

        <line
            x1="{LEFT_MARGIN_MM:.3f}"
            y1="0"
            x2="{LEFT_MARGIN_MM:.3f}"
            y2="{SHEET_H_MM:.0f}"
        />

        <!-- Right margin boundary -->

        <line
            x1="{SHEET_W_MM - RIGHT_MARGIN_MM:.3f}"
            y1="0"
            x2="{SHEET_W_MM - RIGHT_MARGIN_MM:.3f}"
            y2="{SHEET_H_MM:.0f}"
        />

        <!-- Top margin boundary -->

        <line
            x1="0"
            y1="{TOP_MARGIN_MM:.3f}"
            x2="{SHEET_W_MM:.0f}"
            y2="{TOP_MARGIN_MM:.3f}"
        />

        <!-- Bottom margin boundary -->

        <line
            x1="0"
            y1="{SHEET_H_MM - BOTTOM_MARGIN_MM:.3f}"
            x2="{SHEET_W_MM:.0f}"
            y2="{SHEET_H_MM - BOTTOM_MARGIN_MM:.3f}"
        />

    </g>


    <!-- ================================================
         TITLE
         ================================================ -->

    <g
        id="TITLE_ROW"
        font-family="sans-serif"
    >

        <text
            id="TITLE_TEXT"
            x="{title_x:.3f}"
            y="{title_baseline_y:.3f}"
            text-anchor="middle"
            fill="{TITLE_COLOR}"
            font-size="{TITLE_FONT}"
            font-weight="bold"
        >{title_text}</text>

        <line
            id="TITLE_DIVIDER"
            x1="{LEFT_MARGIN_MM:.3f}"
            y1="{title_bottom:.3f}"
            x2="{SHEET_W_MM - RIGHT_MARGIN_MM:.3f}"
            y2="{title_bottom:.3f}"
            stroke="{TITLE_DIVIDER_COLOR}"
            stroke-width="2"
        />

    </g>


    <!-- ================================================
         LEFT
         ================================================ -->

    <g
        id="LEFT_VIEW"
        transform="translate({left_x:.3f} {left_y:.3f})"
    >

        <image
            id="LEFT_VIEW_IMAGE"

            href="{left_data_uri}"
            xlink:href="{left_data_uri}"

            x="0"
            y="0"

            width="{left_svg_w:.3f}"
            height="{left_svg_h:.3f}"

            preserveAspectRatio="none"
        />

        <rect
            id="LEFT_VIEW_BOX"
            x="0"
            y="0"
            width="{left_svg_w:.3f}"
            height="{left_svg_h:.3f}"
            fill="none"
            stroke="#ff0000"
            stroke-width="2"
        />

        <text
            id="LEFT_VIEW_LABEL"
            x="10"
            y="50"
            fill="#ff0000"
            font-size="60"
            font-family="sans-serif"
            font-weight="bold"
        >LEFT</text>

    </g>


    <!-- ================================================
         FRONT

         X:
         {front_x:.3f}

         WIDTH:
         {front_svg_w:.3f}

         RIGHT:
         {front_right_actual:.3f}

         RIGHT MARGIN:
         {actual_right_margin:.3f}
         ================================================ -->

    <g
        id="FRONT_VIEW"
        transform="translate({front_x:.3f} {front_y:.3f})"
    >

        <image
            id="FRONT_VIEW_IMAGE"

            href="{front_data_uri}"
            xlink:href="{front_data_uri}"

            x="0"
            y="0"

            width="{front_svg_w:.3f}"
            height="{front_svg_h:.3f}"

            preserveAspectRatio="none"
        />

        <rect
            id="FRONT_VIEW_BOX"
            x="0"
            y="0"
            width="{front_svg_w:.3f}"
            height="{front_svg_h:.3f}"
            fill="none"
            stroke="#ff0000"
            stroke-width="2"
        />

        <text
            id="FRONT_VIEW_LABEL"
            x="10"
            y="50"
            fill="#ff0000"
            font-size="60"
            font-family="sans-serif"
            font-weight="bold"
        >FRONT</text>

    </g>


    <!-- ================================================
         TOP
         ================================================ -->

    <g
        id="TOP_VIEW"
        transform="translate({top_x:.3f} {top_y:.3f})"
    >

        <image
            id="TOP_VIEW_IMAGE"

            href="{top_data_uri}"
            xlink:href="{top_data_uri}"

            x="0"
            y="0"

            width="{top_svg_w:.3f}"
            height="{top_svg_h:.3f}"

            preserveAspectRatio="none"
        />

        <rect
            id="TOP_VIEW_BOX"
            x="0"
            y="0"
            width="{top_svg_w:.3f}"
            height="{top_svg_h:.3f}"
            fill="none"
            stroke="#ff0000"
            stroke-width="2"
        />

        <text
            id="TOP_VIEW_LABEL"
            x="10"
            y="50"
            fill="#ff0000"
            font-size="60"
            font-family="sans-serif"
            font-weight="bold"
        >TOP</text>

    </g>


    <!-- ================================================
         DIMENSIONS
         ================================================ -->

    <g
        id="DIMENSIONS"

        fill="none"
        stroke="{DIM_COLOR}"
        stroke-width="1.5"

        font-family="sans-serif"
        font-size="{DIM_FONT}"
    >

        <!-- ============================================
             LEFT: Length (horizontal)
             ============================================ -->

        <line
            x1="{left_x:.3f}"
            y1="{left_len_y:.3f}"
            x2="{left_x + left_svg_w:.3f}"
            y2="{left_len_y:.3f}"
        />

        <line
            x1="{left_x:.3f}"
            y1="{left_len_y - TICK_LEN / 2:.3f}"
            x2="{left_x:.3f}"
            y2="{left_len_y + TICK_LEN / 2:.3f}"
        />

        <line
            x1="{left_x + left_svg_w:.3f}"
            y1="{left_len_y - TICK_LEN / 2:.3f}"
            x2="{left_x + left_svg_w:.3f}"
            y2="{left_len_y + TICK_LEN / 2:.3f}"
        />

        <text
            x="{(left_x + left_x + left_svg_w) / 2:.3f}"
            y="{left_len_y - 20:.3f}"
            text-anchor="middle"
            stroke="none"
            fill="{DIM_COLOR}"
        >L = {length_mm:.0f} mm</text>


        <!-- ============================================
             LEFT: Height (vertical)
             ============================================ -->

        <line
            x1="{left_hgt_x:.3f}"
            y1="{left_y:.3f}"
            x2="{left_hgt_x:.3f}"
            y2="{left_y + left_svg_h:.3f}"
        />

        <line
            x1="{left_hgt_x - TICK_LEN / 2:.3f}"
            y1="{left_y:.3f}"
            x2="{left_hgt_x + TICK_LEN / 2:.3f}"
            y2="{left_y:.3f}"
        />

        <line
            x1="{left_hgt_x - TICK_LEN / 2:.3f}"
            y1="{left_y + left_svg_h:.3f}"
            x2="{left_hgt_x + TICK_LEN / 2:.3f}"
            y2="{left_y + left_svg_h:.3f}"
        />

        <text
            x="{left_hgt_x - 25:.3f}"
            y="{(left_y + left_y + left_svg_h) / 2:.3f}"
            text-anchor="end"
            stroke="none"
            fill="{DIM_COLOR}"

            transform="rotate(-90,
                {left_hgt_x - 25:.3f},
                {(left_y + left_y + left_svg_h) / 2:.3f})"
        >H = {height_mm:.0f} mm</text>


        <!-- ============================================
             FRONT: Width (horizontal)
             ============================================ -->

        <line
            x1="{front_x:.3f}"
            y1="{front_wid_y:.3f}"
            x2="{front_x + front_svg_w:.3f}"
            y2="{front_wid_y:.3f}"
        />

        <line
            x1="{front_x:.3f}"
            y1="{front_wid_y - TICK_LEN / 2:.3f}"
            x2="{front_x:.3f}"
            y2="{front_wid_y + TICK_LEN / 2:.3f}"
        />

        <line
            x1="{front_x + front_svg_w:.3f}"
            y1="{front_wid_y - TICK_LEN / 2:.3f}"
            x2="{front_x + front_svg_w:.3f}"
            y2="{front_wid_y + TICK_LEN / 2:.3f}"
        />

        <text
            x="{(front_x + front_x + front_svg_w) / 2:.3f}"
            y="{front_wid_y - 20:.3f}"
            text-anchor="middle"
            stroke="none"
            fill="{DIM_COLOR}"
        >W = {width_mm:.0f} mm</text>


        <!-- ============================================
             FRONT: Height (vertical)
             ============================================ -->

        <line
            x1="{front_hgt_x:.3f}"
            y1="{front_y:.3f}"
            x2="{front_hgt_x:.3f}"
            y2="{front_y + front_svg_h:.3f}"
        />

        <line
            x1="{front_hgt_x - TICK_LEN / 2:.3f}"
            y1="{front_y:.3f}"
            x2="{front_hgt_x + TICK_LEN / 2:.3f}"
            y2="{front_y:.3f}"
        />

        <line
            x1="{front_hgt_x - TICK_LEN / 2:.3f}"
            y1="{front_y + front_svg_h:.3f}"
            x2="{front_hgt_x + TICK_LEN / 2:.3f}"
            y2="{front_y + front_svg_h:.3f}"
        />

        <text
            x="{front_hgt_x - 25:.3f}"
            y="{(front_y + front_y + front_svg_h) / 2:.3f}"
            text-anchor="end"
            stroke="none"
            fill="{DIM_COLOR}"

            transform="rotate(-90,
                {front_hgt_x - 25:.3f},
                {(front_y + front_y + front_svg_h) / 2:.3f})"
        >H = {height_mm:.0f} mm</text>


        <!-- ============================================
             TOP: Length (horizontal)
             ============================================ -->

        <line
            x1="{top_x:.3f}"
            y1="{top_len_y:.3f}"
            x2="{top_x + top_svg_w:.3f}"
            y2="{top_len_y:.3f}"
        />

        <line
            x1="{top_x:.3f}"
            y1="{top_len_y - TICK_LEN / 2:.3f}"
            x2="{top_x:.3f}"
            y2="{top_len_y + TICK_LEN / 2:.3f}"
        />

        <line
            x1="{top_x + top_svg_w:.3f}"
            y1="{top_len_y - TICK_LEN / 2:.3f}"
            x2="{top_x + top_svg_w:.3f}"
            y2="{top_len_y + TICK_LEN / 2:.3f}"
        />

        <text
            x="{(top_x + top_x + top_svg_w) / 2:.3f}"
            y="{top_len_y - 20:.3f}"
            text-anchor="middle"
            stroke="none"
            fill="{DIM_COLOR}"
        >L = {length_mm:.0f} mm</text>


        <!-- ============================================
             TOP: Width (vertical)
             ============================================ -->

        <line
            x1="{top_wid_x:.3f}"
            y1="{top_y:.3f}"
            x2="{top_wid_x:.3f}"
            y2="{top_y + top_svg_h:.3f}"
        />

        <line
            x1="{top_wid_x - TICK_LEN / 2:.3f}"
            y1="{top_y:.3f}"
            x2="{top_wid_x + TICK_LEN / 2:.3f}"
            y2="{top_y:.3f}"
        />

        <line
            x1="{top_wid_x - TICK_LEN / 2:.3f}"
            y1="{top_y + top_svg_h:.3f}"
            x2="{top_wid_x + TICK_LEN / 2:.3f}"
            y2="{top_y + top_svg_h:.3f}"
        />

        <text
            x="{top_wid_x - 25:.3f}"
            y="{(top_y + top_y + top_svg_h) / 2:.3f}"
            text-anchor="end"
            stroke="none"
            fill="{DIM_COLOR}"

            transform="rotate(-90,
                {top_wid_x - 25:.3f},
                {(top_y + top_y + top_svg_h) / 2:.3f})"
        >W = {width_mm:.0f} mm</text>

    </g>

</svg>
'''


# ============================================================
# SAVE SVG
# ============================================================

with open(

    svg_path,

    "w",

    encoding="utf-8"

) as f:

    f.write(svg)


# ============================================================
# FINAL REPORT
# ============================================================

print("\n")
print("=" * 72)

print("EXPORT FINISHED")

print("=" * 72)


print(
    f"\nMODEL:  {obj.name}"
)


print(
    f"\nVEHICLE SIZE:\n"
    f"  {length_mm:.2f} × "
    f"{width_mm:.2f} × "
    f"{height_mm:.2f} mm"
)


print(
    f"\nTITLE:\n"
    f"  {obj.name}"
)


print(
    f"\nVERTICAL LAYOUT:\n"
    f"  looseness = {VERTICAL_LOOSENESS * 100:.0f}%\n"
    f"  title gap = {effective_title_gap:.3f} mm\n"
    f"  view gap  = {effective_vertical_gap:.3f} mm"
)


print(
    "\nSVG LAYOUT:"
)


print(

    f"  LEFT:  x={left_x:.3f}  "
    f"y={left_y:.3f}  "
    f"w={left_svg_w:.3f}  "
    f"h={left_svg_h:.3f}"

)


print(

    f"  FRONT: x={front_x:.3f}  "
    f"y={front_y:.3f}  "
    f"w={front_svg_w:.3f}  "
    f"h={front_svg_h:.3f}"

)


print(

    f"  TOP:   x={top_x:.3f}  "
    f"y={top_y:.3f}  "
    f"w={top_svg_w:.3f}  "
    f"h={top_svg_h:.3f}"

)


print(
    "\nFRONT RIGHT-ALIGNMENT:"
)


print(

    f"  right edge = {front_right_actual:.3f} mm\n"

    f"  expected   = "
    f"{SHEET_W_MM - RIGHT_MARGIN_MM:.3f} mm\n"

    f"  margin     = "
    f"{actual_right_margin:.3f} mm\n"

    f"  delta      = "
    f"{abs(front_right_actual - (SHEET_W_MM - RIGHT_MARGIN_MM)):.6f} mm"

)


if abs(
    front_right_actual
    - (SHEET_W_MM - RIGHT_MARGIN_MM)
) <= EPS:

    print("  → OK")


print(
    f"\nOUTPUT:\n"
    f"  {svg_path}"
)


print(
    "\nSVG layers:"
    " 灰色虚线 = margin 边界"
    " 红色实线 = FRONT 视图 bounding box"
    " 蓝色标注 = L / W / H 尺寸"
)


print("=" * 72)

print("\n✓ 完成 — 三视图已导出\n")
