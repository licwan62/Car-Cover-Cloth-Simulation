# Car Cover Cloth Simulation

基于 Illustrator 二维版型与 Blender 车辆模型的车罩适配验证项目。当前重点是几何、缝线和模拟流程的稳定性，不是渲染质量。

## 目录

```text
config/                 可版本化的布料、模拟和 Fit 阈值
illustrator/            AI 母版与 SVG/JSON 导出
blender/                车辆和模拟场景（不存放脚本）
scripts/blender/        Blender 脚本，按阶段编号（Text Editor 中手动运行）
scripts/blender/config_driven/  读取 config/ 的同阶段脚本
scripts/modules/        共享 Python 模块（Blender 通过 Script Directories 自动搜索）
scripts/tools/          仓库维护工具（普通 Python 运行，不在 Blender 中运行）
scripts/illustrator/    Illustrator 自动化模块
output/                 模拟、报告和调试产物
tests/unit/             不依赖 Blender 的单元测试
tests/blender/          需要用 blender --background 运行的检查脚本
doc/AGENT.md            完整设计依据
```

## Blender 脚本目录设置

多个 Blender 版本共用同一份项目脚本，每个版本只需设置一次：

1. 打开 **Edit → Preferences → File Paths → Script Directories**，点击 **Add**，
   目录填写 `D:\Licheng\Repo\Car Cover Cloth Simulation\scripts`（项目的
   `scripts` 目录，不是 `scripts\blender`）；
2. 保存 Preferences 并**重启 Blender**。

Blender 只会在该目录下搜索固定的三个子目录：`modules`（加入 `sys.path`，可
`import`）、`addons`（需带 `bl_info`/`register()` 的插件）和 `startup`（启动时自
动执行）。添加目录**不会**自动注册或运行 `scripts\blender` 下的普通 `.py` 文件；
这些脚本仍然要在 Text Editor 中 **Open** 后点击 **Run Script**。本项目目前没有
`addons` 或 `startup` 内容。

| 位置 | 用法 |
| --- | --- |
| `scripts/blender/*.py` | Text Editor 打开或粘贴后 Run Script；内嵌参数，不依赖项目文件 |
| `scripts/blender/config_driven/*.py` | 必须从项目路径 **Open** 已保存的文件后 Run Script；读取 `config/*.json` |
| `scripts/modules/project_config.py`、`seam_naming.py` | 共享模块，由 Blender 自动搜索，不要直接运行 |

`config_driven` 脚本通过 `project_config` 定位项目根目录和 `config/`，不依赖
Text Editor 中的 `__file__`（Blender 会把它设为 `<blend 路径>\<文本名>`）。未添加
Script Directory 时从 Text Editor 运行会报 `project_config not found`。命令行运行
`blender --python scripts/blender/config_driven/<脚本>.py` 即使使用
`--factory-startup`（不加载 Preferences）也能根据脚本路径找到 `scripts/modules`。

Script Directories 支持多个目录，需要 Blender 3.6 及以上；本项目当前在
Blender 5.2.1 验证。可在待测版本中运行以下检查（不修改已保存的 Preferences）：

```powershell
blender --background --factory-startup --python-exit-code 1 --python tests/blender/check_script_directories.py
```

## 当前 Blender 脚本

建议按以下顺序从 Blender 的 Scripting 工作区执行：

文件名前缀与 `.blend` 中 Text 块的阶段编号一致：`0xx` 主流程、`1xx` 标记、
`2xx` 碰撞体、`3xx` 导出；`config_driven/` 中的脚本沿用对应阶段的编号。

- 一键流程：`000_svg_to_cloth.py` 选择语义 SVG，依次完成导入、`001_remesh`、
  `002_sew_from_svg` 和 `003_cloth_setup`。
- 分步流程：`config_driven/000_repair_boundary.py` 修复开放边界 →
  `001_remesh.py` 生成约 50 mm 的约束 Delaunay Cloth Mesh →
  `002_sew_from_svg.py` 按语义 Sewing ID 生成 Loose Edge →
  `003_cloth_setup.py`（或配置版 `config_driven/003_cloth_setup.py`，应用
  `Oxford_210D_SmoothDrape_V2`）。
- 标记：`100_mirror_marks.py` 耳位/充电口、`101_door_marks.py` 车门线、
  `102_plate_marks.py` 车牌开口。
- 碰撞体：`200_collision_exterior.py` 生成外包络 Collision。
- 导出：`300_export_three_views.py`、`301_export_six_views.py`。

完整清单见 [scripts/blender/README.md](scripts/blender/README.md)。几何脚本会直接修改当前 Blender 场景；请在副本场景中先验证。

## 配置

- `config/cloth/oxford_210d.json`：布料、碰撞、自碰撞和 Pin 参数。
- `config/simulation.json`：网格、边界修复、Sewing 与分阶段模拟设置。
- `config/fit_thresholds.json`：Fit 指标定义和已校准阈值。

`SmoothDrape_V2` 针对 50 mm 三角网格减少细密碎褶：降低面内压缩/剪切刚度，提高弯曲阻尼，并启用仅影响显示法线的 Shade Smooth。重新应用预设后必须删除旧 Cloth Bake 再模拟。

Self-contained Blender scripts are in `scripts/blender/`. The V28 cloth preset samples free drape, then ramps per-vertex soft pin springs during frames 45-65 toward one shared HEM height and holds through frame 75. Clear the Cloth bake before setup and replay from Scene Start. See [Blender instructions](scripts/blender/README.md).

展开辅助力采用 `frame_change_pre` 调度；Sewing、后摆 Shape Key 与 Pin 强度使用持久化 Driver，避免逐帧改写 Cloth 设置而中断 Bake。两者都不创建 Action，兼容 Blender 5.x 的分层动画和依赖图。

V11 的第 30 帧仍带弱展开力和 `PIN_ROOF`，并非完全无约束的 Fit 平衡；数值 Fit 分析应另行把展开 sustain 设为 0，并关闭持续屋顶 Pin。

所有长度配置均显式使用 `_mm` 后缀；Blender 脚本内部按 `1 BU = 1 m` 换算。

## Sewing 命名

新数据使用 `Sewing ID + Panel`，例如：

```text
S001_TOP
S001_LEFT
S001_TOP_A
S001_TOP_B
S001_LEFT_A
S001_LEFT_B
```

同一 Sewing ID 必须恰好对应两个 Panel。`A`、`B` 标记用于强制 `A → A`、`B → B`，不再用空间距离猜测缝合方向。旧工程的 `SEAM_TOP_LEFT` 命名暂由 `simulation.json` 中的显式配对兼容。

## 耳位与充电口标记

### 当前标记代表什么

`100_mirror_marks.py` 不生成真实的后视镜耳袋或充电口结构，也不修改
Cloth 物理。它在已经落到车辆上的车罩三角面中查找版型坐标附近的面，给这些
完整三角面分配高对比材质：

- 橙红色：左右后视镜耳位中心；
- 蓝色：左侧充电口中心；
- 标记不增加顶点、面、质量、碰撞、缝线或约束。

画板 1 的二维坐标按厘米标注，脚本配置统一换算为毫米：

- 后视镜：以车头底部端点为原点，沿车身向后 `x = 1600 mm`，向上
  `y = 1020 mm`；左右两侧各一个标记；
- 充电口：以车尾底部端点为原点，沿车身向前 `x = 340 mm`，向上
  `y = 820 mm`；只标记车辆左侧。

Model X 场景中车辆长度方向是 Blender 的 Y 轴，车头朝 `-Y`，车辆横向是 X
轴。因此版型的二维 `x` 会映射到 Blender Y，版型的二维 `y` 会映射到
Blender Z。脚本不是直接把二维数值写入 Blender X/Y。

### 为什么红色是块状、不规则形状

当前标记采用“面材质”而不是贴图。脚本先在仿真后的评估网格上计算每个三角面
中心，再用椭圆距离判断该面是否落入标记范围。命中的三角面会整面变色，所以
标记边界只能沿现有三角形边界形成：

- 50 mm Cloth 网格只能得到近似轮廓，不会是 Illustrator 中光滑的耳朵外形；
- 三角形大小、方向和疏密不均时，红色会呈锯齿、多边形或不对称块；
- `width_mm`、`height_mm` 定义的是查找椭圆范围，不是最终生产耳袋轮廓；
- 开启 Wireframe/编辑网格叠加时，黑色三角边会进一步强化这种碎块视觉；
- 当前方法用于检查“中心位置是否正确”，不能用于检查耳袋形状或缝份。

旧版脚本在没有基础材质的对象上先把红色材质放入槽位 0，而 Blender 所有面
默认使用槽位 0，因此曾出现整个车罩变红。新版运行时会先建立/识别基础材质，
清除旧的耳位与充电口材质分配，再只给目标附近的少量面着色。重新运行新版即可
清理旧版造成的整罩红色。

### 配置版如何读取参数

项目内运行 [config_driven/100_mirror_marks.py](scripts/blender/config_driven/100_mirror_marks.py) 时，
读取 `config/simulation.json` 的 `mirror_markers` 段，然后把完整配置传给公共执行
函数。修改 JSON 后重新运行脚本即可生效：

```json
"mirror_markers": {
  "front_axis": "-Y",
  "mirror": {
    "distance_from_front_mm": 1600.0,
    "height_from_bottom_mm": 1020.0,
    "width_mm": 220.0,
    "height_mm": 180.0
  },
  "charge_port": {
    "side": "-LATERAL",
    "distance_from_rear_mm": 340.0,
    "height_from_bottom_mm": 820.0,
    "width_mm": 180.0,
    "height_mm": 160.0
  },
  "search_depth_mm": 300.0
}
```

参数含义：

- `front_axis`：车辆车头方向，允许 `+X`、`-X`、`+Y`、`-Y`；
- `distance_from_front_mm`：耳位中心距车头端点的纵向距离；
- `distance_from_rear_mm`：充电口中心距车尾端点的纵向距离；
- `height_from_bottom_mm`：中心距车辆包围盒底部的高度；
- `side`：充电口所在横向侧；Model X 当前使用 `-LATERAL`；
- `width_mm`、`height_mm`：可视标记的椭圆查找宽高；
- `search_depth_mm`：允许车罩表面相对车辆侧面的横向距离。

### 独立运行 版如何读取参数

[100_mirror_marks.py](scripts/blender/100_mirror_marks.py)
不读取 JSON，也不导入项目模块。它使用文件顶部内嵌的 `MARKER_CONFIG` 作为
交互窗口默认值，方便将整个脚本复制进 `.blend` 的 Text Editor。运行脚本会先
打开“车罩耳位 / 充电口标记”窗口；可在窗口中修改车头方向、两组中心坐标、
标记宽高、充电口侧别和搜索深度，按“确定”后才会写入材质标记。修改
`config/simulation.json` 不会自动改变 独立运行 版的窗口默认值；如需永久调整
默认值，必须同步修改 独立运行 文件顶部的 `MARKER_CONFIG`。

两个入口最终都调用 `apply_mirror_markers()`：

```text
config_driven/100_mirror_marks.py
  -> 读取 config/simulation.json
  -> apply_mirror_markers(config=CONFIG)

100_mirror_marks.py
  -> 使用内嵌 MARKER_CONFIG 生成交互窗口默认值
  -> 用户在窗口确认或修改参数
  -> apply_mirror_markers(config=交互参数)
```

### 正确运行方式

1. 切换到车罩已经完成落车的最终比较帧；
2. 选择与该车罩对应的车辆或 Collision 对象；
3. 最后选择 Cloth 对象，使 Cloth 成为活动对象；
4. 运行配置版或 独立运行 版，两者只运行一个；独立运行 版需在弹窗确认参数；
5. 使用 Material Preview，或在 Solid 模式把 Color 设置为 Material，查看颜色。

车辆参考选错、当前帧尚未落罩、车头轴配置错误或目标范围附近没有布料面时，
新版会停止并报错，不再随意选择距离最近的三角面作为标记。

## 验证

在项目根目录执行：

```powershell
python -m unittest discover -s tests/unit -v
python -m compileall scripts tests
```

Blender 检查（`--factory-startup`，不修改已保存的 Preferences 和场景）：

```powershell
blender --background --factory-startup --python-exit-code 1 --python tests/blender/check_script_directories.py
blender --background --factory-startup --python-exit-code 1 --python tests/blender/check_collision_exterior.py
```

完整目标、物理原则和开发优先级见 [PROJECT_STARTUP.md](PROJECT_STARTUP.md)。
