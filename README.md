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
- 标记：`100_marks.py` 一个窗口设置耳位（半椭圆）、充电口、车门线、车牌开口，
  每项可单独开关。
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

## 车罩标记（100_marks.py）

### 标记内容

`100_marks.py` 合并了原 `100_mirror_marks.py`、`101_door_marks.py`、
`102_plate_marks.py`。运行后弹出一个“车罩标记”窗口，四类标记各有开关；
关闭的标记会在确定时被移除，其余标记重新生成：

| 标记 | 形状 | 默认值 |
| --- | --- | --- |
| 后视镜耳位（左右各一） | 半椭圆，直边在下 | 外接矩形中心距车头 1600 mm、距底部 1020 mm；宽 430 mm（直边长）、高 300 mm（直边到顶点） |
| 充电口（单侧） | 矩形 | 中心距车尾 340 mm、距底部 820 mm；180 × 160 mm |
| 车门线（左右） | 竖线 | 距车头 1800 mm，线宽 30 mm |
| 车牌开孔（`PANEL_TOP`） | 矩形 | 前后端净距 300 mm；440 × 140 mm |

后视镜耳位下方会生成 Text 对象 `<Cloth 名> Mirror Label L/R`（集合 `CC Mark Labels`），
内容如 `MIRROR L  X 1600  Y 1020 / W 430 x H 300 mm`，用于记录定位；窗口中耳位
设置下方也实时显示同样的信息。定位信息同时写入 Cloth 对象的自定义属性
`cc_mirror_marker_*`，完整窗口参数保存在 `cc_marks_config`，下次打开窗口时
自动读回。

标记是叠加在材质上的逐像素形状（面角属性 `cc_mark_<kind>` + 共享 CC mark
overlay 代码块），边缘精确并随布料变形，Solid 视图（Color = Texture）也可见；
不增加顶点、面、质量、碰撞、缝线或约束。标签是在当前帧放置的独立物体，
不随布料变形。Solid 视图中一个面只显示一种标记，标记重叠处以渲染结果为准。

Model X 场景中车辆长度方向是 Blender 的 Y 轴，车头朝 `-Y`，车辆横向是 X
轴。版型的二维 `x` 映射到 Blender Y，`y` 映射到 Blender Z。

### 配置版

[config_driven/100_mirror_marks.py](scripts/blender/config_driven/100_mirror_marks.py)
读取 `config/simulation.json` 的 `mirror_markers` 段，只更新耳位与充电口，
不改动车门线和车牌标记：

```text
config_driven/100_mirror_marks.py
  -> 读取 config/simulation.json
  -> apply_mirror_markers(config=CONFIG)

100_marks.py
  -> 使用内嵌 MARKS_CONFIG（或上次保存在 Cloth 上的参数）生成窗口默认值
  -> apply_marks(config=窗口参数)
```

`mirror_markers.mirror` 可选 `flat_edge`（`BOTTOM`/`TOP`）和 `label`
（是否生成定位标签）。修改 `simulation.json` 不会改变独立版窗口默认值，
永久默认值在 `100_marks.py` 顶部的 `MARKS_CONFIG`。

### 正确运行方式

1. 切换到车罩已经完成落车的最终比较帧；
2. 选择一个或多个 Cloth 对象（可批量：所有选中的 Cloth 使用同一组参数，
   窗口默认值读自活动对象）；
3. 运行配置版或独立版；独立版需在弹窗确认参数；
4. 使用 Material Preview，或在 Solid 模式把 Color 设置为 Texture 查看。

当前帧尚未落罩、车头轴配置错误或目标范围内没有布料面时，脚本会停止并报错，
且不会只更新一部分标记；批量时出错的物体保持不变并给出警告，其余物体照常标记。

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
