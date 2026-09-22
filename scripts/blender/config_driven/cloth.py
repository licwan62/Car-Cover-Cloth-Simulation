import bpy
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from project_config import load_cloth_preset


# ============================================================
# 210D OXFORD CAR COVER - CLOTH PRESET V1
#
# 假设：
# - Blender 单位：1 BU = 1 m
# - Cloth Mesh 平均边长约：40~60 mm
# - 用于汽车罩版型适配模拟
# ============================================================


# ------------------------------------------------------------
# Simulation Quality
# ------------------------------------------------------------

QUALITY_STEPS = 15
TIME_SCALE = 1.0


# ------------------------------------------------------------
# Mass
#
# Blender 的 mass 是“每个 Cloth Vertex 的质量”，
# 不是直接的 g/m²。
#
# 因此它和网格密度强相关。
#
# 对你当前约 50mm 网格：
# 推荐先从 0.08~0.15 测试。
# ------------------------------------------------------------

MASS = 0.10


# ------------------------------------------------------------
# Structural Stiffness
#
# 210D 牛津布：
# 抗拉高
# 抗剪较高
# 抗压较高
# ------------------------------------------------------------

TENSION_STIFFNESS = 60.0
COMPRESSION_STIFFNESS = 45.0
SHEAR_STIFFNESS = 35.0


# ------------------------------------------------------------
# Bending
#
# 这是减少“丝绸式小碎褶皱”的关键。
#
# Cotton 默认会明显偏软。
# 车罩推荐先 3~8 测试。
# ------------------------------------------------------------

BENDING_STIFFNESS = 6.0

BENDING_MODEL = 'ANGULAR'


# ------------------------------------------------------------
# Damping
#
# 提高阻尼可以减少：
# - 高频抖动
# - 小褶皱来回震荡
# - Sewing 后反复弹跳
# ------------------------------------------------------------

TENSION_DAMPING = 8.0
COMPRESSION_DAMPING = 8.0
SHEAR_DAMPING = 8.0
BENDING_DAMPING = 3.0


# ------------------------------------------------------------
# Air Damping
# ------------------------------------------------------------

AIR_DAMPING = 2.0


# ------------------------------------------------------------
# Sewing
#
# 0 = Unlimited，不建议。
#
# 对已经预摆到比较近的位置：
# 5~15 是比较适合调试的范围。
# ------------------------------------------------------------

ENABLE_SEWING = True
MAX_SEWING_FORCE = 8.0


# ------------------------------------------------------------
# Object Collision
# ------------------------------------------------------------

ENABLE_OBJECT_COLLISION = True

COLLISION_QUALITY = 6


# Cloth 到 Collision Object 的最小距离
OBJECT_COLLISION_DISTANCE_MM = 6.0


# ------------------------------------------------------------
# Self Collision
# ------------------------------------------------------------

ENABLE_SELF_COLLISION = True

SELF_COLLISION_DISTANCE_MM = 5.0

SELF_FRICTION = 8.0


# ------------------------------------------------------------
# Collision Friction
#
# 这里是 Cloth 自身 collision settings 里的 friction。
# 汽车 Collision Object 本身的 cloth_friction
# 需要在汽车碰撞体上另外设置。
# ------------------------------------------------------------

OBJECT_COLLISION_FRICTION = 8.0


# ------------------------------------------------------------
# Pin
#
# 如果已经存在 PIN_ROOF：
# 可以自动启用。
#
# 建议 Pin Weight 本身不要太大，
# 例如 0.15~0.30。
# ------------------------------------------------------------

PIN_GROUP_NAME = "PIN_ROOF"

PIN_STIFFNESS = 0.25


# config/cloth/oxford_210d.json is the single source of truth. Keeping the
# named constants below makes Blender API assignments easy to inspect.
PRESET_CONFIG = load_cloth_preset()
SIMULATION_CONFIG = PRESET_CONFIG["simulation"]
STIFFNESS_CONFIG = PRESET_CONFIG["stiffness"]
DAMPING_CONFIG = PRESET_CONFIG["damping"]
SEWING_CONFIG = PRESET_CONFIG["sewing"]
OBJECT_COLLISION_CONFIG = PRESET_CONFIG["object_collision"]
SELF_COLLISION_CONFIG = PRESET_CONFIG["self_collision"]
PIN_CONFIG = PRESET_CONFIG["pin"]
DISPLAY_CONFIG = PRESET_CONFIG.get("display", {})

QUALITY_STEPS = int(SIMULATION_CONFIG["quality_steps"])
TIME_SCALE = float(SIMULATION_CONFIG["time_scale"])
MASS = float(SIMULATION_CONFIG["mass_per_vertex"])
AIR_DAMPING = float(SIMULATION_CONFIG["air_damping"])

TENSION_STIFFNESS = float(STIFFNESS_CONFIG["tension"])
COMPRESSION_STIFFNESS = float(STIFFNESS_CONFIG["compression"])
SHEAR_STIFFNESS = float(STIFFNESS_CONFIG["shear"])
BENDING_STIFFNESS = float(STIFFNESS_CONFIG["bending"])
BENDING_MODEL = str(STIFFNESS_CONFIG["bending_model"])

TENSION_DAMPING = float(DAMPING_CONFIG["tension"])
COMPRESSION_DAMPING = float(DAMPING_CONFIG["compression"])
SHEAR_DAMPING = float(DAMPING_CONFIG["shear"])
BENDING_DAMPING = float(DAMPING_CONFIG["bending"])

ENABLE_SEWING = bool(SEWING_CONFIG["enabled"])
MAX_SEWING_FORCE = float(SEWING_CONFIG["max_force"])

ENABLE_OBJECT_COLLISION = bool(OBJECT_COLLISION_CONFIG["enabled"])
COLLISION_QUALITY = int(OBJECT_COLLISION_CONFIG["quality"])
OBJECT_COLLISION_DISTANCE_MM = float(OBJECT_COLLISION_CONFIG["distance_mm"])
OBJECT_COLLISION_FRICTION = float(OBJECT_COLLISION_CONFIG["friction"])

ENABLE_SELF_COLLISION = bool(SELF_COLLISION_CONFIG["enabled"])
SELF_COLLISION_DISTANCE_MM = float(SELF_COLLISION_CONFIG["distance_mm"])
SELF_FRICTION = float(SELF_COLLISION_CONFIG["friction"])

PIN_GROUP_NAME = str(PIN_CONFIG["group"])
PIN_STIFFNESS = float(PIN_CONFIG["stiffness"])
SHADE_SMOOTH = bool(DISPLAY_CONFIG.get("shade_smooth", True))


# ============================================================
# INTERNAL
# ============================================================

OBJECT_COLLISION_DISTANCE = (
    OBJECT_COLLISION_DISTANCE_MM / 1000.0
)

SELF_COLLISION_DISTANCE = (
    SELF_COLLISION_DISTANCE_MM / 1000.0
)


# ============================================================
# GET SELECTED MESH OBJECTS
# ============================================================

objects = [
    obj
    for obj in bpy.context.selected_objects
    if obj.type == 'MESH'
]


if not objects:

    raise RuntimeError(
        "请先选择需要设置 Oxford Cloth 的 Mesh 对象。"
    )


# ============================================================
# APPLY
# ============================================================

baked_objects = []

for obj in objects:

    # --------------------------------------------------------
    # 找 Cloth Modifier
    # --------------------------------------------------------

    cloth_mod = None

    for mod in obj.modifiers:

        if mod.type == 'CLOTH':
            cloth_mod = mod
            break


    # --------------------------------------------------------
    # 没有 Cloth 就自动添加
    # --------------------------------------------------------

    if cloth_mod is None:

        bpy.context.view_layer.objects.active = obj

        obj.select_set(True)

        cloth_mod = obj.modifiers.new(
            name="Oxford 210D Cloth",
            type='CLOTH'
        )


    settings = cloth_mod.settings
    collision = cloth_mod.collision_settings

    if getattr(cloth_mod.point_cache, "is_baked", False):
        baked_objects.append(obj.name)


    # ========================================================
    # DISPLAY NORMALS
    #
    # Smooth shading does not change simulation geometry or Fit metrics. It
    # only prevents every 50 mm triangle from reading as a hard facet.
    # ========================================================

    if SHADE_SMOOTH:
        for polygon in obj.data.polygons:
            polygon.use_smooth = True


    # ========================================================
    # GENERAL
    # ========================================================

    settings.quality = QUALITY_STEPS

    settings.time_scale = TIME_SCALE

    settings.mass = MASS

    settings.air_damping = AIR_DAMPING


    # ========================================================
    # PHYSICAL PROPERTIES
    # ========================================================

    settings.tension_stiffness = (
        TENSION_STIFFNESS
    )

    settings.compression_stiffness = (
        COMPRESSION_STIFFNESS
    )

    settings.shear_stiffness = (
        SHEAR_STIFFNESS
    )

    settings.bending_stiffness = (
        BENDING_STIFFNESS
    )

    settings.bending_model = (
        BENDING_MODEL
    )


    # ========================================================
    # DAMPING
    # ========================================================

    settings.tension_damping = (
        TENSION_DAMPING
    )

    settings.compression_damping = (
        COMPRESSION_DAMPING
    )

    settings.shear_damping = (
        SHEAR_DAMPING
    )

    settings.bending_damping = (
        BENDING_DAMPING
    )


    # ========================================================
    # SEWING
    # ========================================================

    settings.use_sewing_springs = (
        ENABLE_SEWING
    )

    settings.sewing_force_max = (
        MAX_SEWING_FORCE
    )


    # ========================================================
    # PIN
    # ========================================================

    pin_group = obj.vertex_groups.get(
        PIN_GROUP_NAME
    )

    if pin_group:

        settings.vertex_group_mass = (
            PIN_GROUP_NAME
        )

        settings.pin_stiffness = (
            PIN_STIFFNESS
        )

        print(
            f"{obj.name}: "
            f"使用 Pin Group = {PIN_GROUP_NAME}"
        )

    else:

        # 没有 PIN_ROOF 就不设置
        settings.vertex_group_mass = ""


    # ========================================================
    # OBJECT COLLISION
    # ========================================================

    collision.use_collision = (
        ENABLE_OBJECT_COLLISION
    )

    collision.collision_quality = (
        COLLISION_QUALITY
    )

    collision.distance_min = (
        OBJECT_COLLISION_DISTANCE
    )

    collision.friction = (
        OBJECT_COLLISION_FRICTION
    )

    # None tells Blender to consider Collision objects from the entire scene,
    # regardless of which collection contains them.
    collision.collection = None

    obj["cloth_collision_collection"] = (
        collision.collection.name
        if collision.collection is not None
        else "ALL"
    )


    # ========================================================
    # SELF COLLISION
    # ========================================================

    collision.use_self_collision = (
        ENABLE_SELF_COLLISION
    )

    collision.self_distance_min = (
        SELF_COLLISION_DISTANCE
    )

    collision.self_friction = (
        SELF_FRICTION
    )


    # ========================================================
    # SAVE CUSTOM PROPERTIES
    # ========================================================

    obj["cloth_preset"] = (
        PRESET_CONFIG["preset"]
    )

    obj["cloth_mesh_edge_target_mm"] = (
        PRESET_CONFIG["mesh_edge_target_mm"]
    )

    obj["cloth_mass"] = MASS

    obj["cloth_tension"] = (
        TENSION_STIFFNESS
    )

    obj["cloth_compression"] = (
        COMPRESSION_STIFFNESS
    )

    obj["cloth_shear"] = (
        SHEAR_STIFFNESS
    )

    obj["cloth_bending"] = (
        BENDING_STIFFNESS
    )

    obj["cloth_sewing_force"] = (
        MAX_SEWING_FORCE
    )

    obj["cloth_shade_smooth"] = SHADE_SMOOTH


    print("")
    print("=" * 60)

    print(
        "Oxford Cloth Applied:",
        obj.name
    )

    print(
        "Mass:",
        MASS
    )

    print(
        "Tension:",
        TENSION_STIFFNESS
    )

    print(
        "Compression:",
        COMPRESSION_STIFFNESS
    )

    print(
        "Shear:",
        SHEAR_STIFFNESS
    )

    print(
        "Bending:",
        BENDING_STIFFNESS
    )

    print(
        "Sew Force:",
        MAX_SEWING_FORCE
    )

    print(
        "Self Collision:",
        ENABLE_SELF_COLLISION
    )

    print(
        "Shade Smooth:",
        SHADE_SMOOTH
    )

    print("=" * 60)


print("")
print("Oxford 210D Cloth preset applied.")

if baked_objects:
    print("")
    print("[IMPORTANT] 以下对象存在已烘焙的 Cloth Cache：")
    for object_name in baked_objects:
        print(f"  - {object_name}")
    print("请执行 Physics > Cache > Delete Bake/Free Bake 后重新模拟。")
