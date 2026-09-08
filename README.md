# Car Cover Cloth Simulation

基于 Illustrator 二维版型与 Blender 车辆模型的车罩适配验证项目。当前重点是几何、缝线和模拟流程的稳定性，不是渲染质量。

## 目录

```text
config/                 可版本化的布料、模拟和 Fit 阈值
illustrator/            AI 母版与 SVG/JSON 导出
blender/                车辆和模拟场景（不存放脚本）
scripts/blender/        Blender 自动化模块
scripts/illustrator/    Illustrator 自动化模块
output/                 模拟、报告和调试产物
tests/                  不依赖 Blender 的单元测试及测试资产
doc/AGENT.md            完整设计依据
```

## 当前 Blender 脚本

建议按以下顺序从 Blender 的 Scripting 工作区执行：

1. `repair_boundary.py`：修复 SVG 转 Mesh 后的开放边界。
2. `generate_cloth_mesh.py`：生成约 50 mm 的约束 Delaunay Cloth Mesh。
3. `generate_sewing.py`：按语义 Sewing ID 配对并生成 Loose Edge。
4. `setup_cloth.py`：应用 `Oxford_210D_SmoothDrape_V2` 配置。
5. `export_three_views.py`：导出真实尺寸三视图报告（辅助工具）。
6. `setup_mirror_markers.py`：在最终落罩帧添加后视镜耳位和充电口位置标记。

脚本位于 `scripts/blender/`。其中几何脚本会直接修改当前 Blender 场景；请在副本场景中先验证。

## 配置

- `config/cloth/oxford_210d.json`：布料、碰撞、自碰撞和 Pin 参数。
- `config/simulation.json`：网格、边界修复、Sewing 与分阶段模拟设置。
- `config/fit_thresholds.json`：Fit 指标定义和已校准阈值。

`SmoothDrape_V2` 针对 50 mm 三角网格减少细密碎褶：降低面内压缩/剪切刚度，提高弯曲阻尼，并启用仅影响显示法线的 Shade Smooth。重新应用预设后必须删除旧 Cloth Bake 再模拟。

如果需要把脚本直接保存在 `.blend` 的 Text block 中，请使用 `scripts/blender/setup_cloth_standalone.py`。该副本不读取 JSON，也不依赖项目内的其他 Python 模块。独立版 CollisionSafe 30F V11 使用 0.12 kg 顶点质量、1.5 Time Scale，并把 Sewing Max Force 从 2 渐增至 6；五个径向力场覆盖车头、车尾及四角，初期峰值 0.75，随后维持 0.10 的弱展开力。启用 `HEM_REAR` 时，其目标相对车罩中心向外 100 mm、向下 220 mm，有效 Pin 权重在第 13 帧完全释放；之后组合 Pin 只保留 `PIN_ROOF` 弱锚点，避免固定 X/Y 目标把下摆拉入碰撞凹槽。

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

`setup_mirror_markers.py` 不生成真实的后视镜耳袋或充电口结构，也不修改
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

项目内运行 [setup_mirror_markers.py](scripts/blender/setup_mirror_markers.py) 时，
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

### standalone 版如何读取参数

[setup_mirror_markers_standalone.py](scripts/blender/setup_mirror_markers_standalone.py)
不读取 JSON，也不导入项目模块。它使用文件顶部内嵌的 `MARKER_CONFIG` 作为
交互窗口默认值，方便将整个脚本复制进 `.blend` 的 Text Editor。运行脚本会先
打开“车罩耳位 / 充电口标记”窗口；可在窗口中修改车头方向、两组中心坐标、
标记宽高、充电口侧别和搜索深度，按“确定”后才会写入材质标记。修改
`config/simulation.json` 不会自动改变 standalone 版的窗口默认值；如需永久调整
默认值，必须同步修改 standalone 文件顶部的 `MARKER_CONFIG`。

两个入口最终都调用 `apply_mirror_markers()`：

```text
setup_mirror_markers.py
  -> 读取 config/simulation.json
  -> apply_mirror_markers(config=CONFIG)

setup_mirror_markers_standalone.py
  -> 使用内嵌 MARKER_CONFIG 生成交互窗口默认值
  -> 用户在窗口确认或修改参数
  -> apply_mirror_markers(config=交互参数)
```

### 正确运行方式

1. 切换到车罩已经完成落车的最终比较帧；
2. 选择与该车罩对应的车辆或 Collision 对象；
3. 最后选择 Cloth 对象，使 Cloth 成为活动对象；
4. 运行配置版或 standalone 版，两者只运行一个；standalone 版需在弹窗确认参数；
5. 使用 Material Preview，或在 Solid 模式把 Color 设置为 Material，查看颜色。

车辆参考选错、当前帧尚未落罩、车头轴配置错误或目标范围附近没有布料面时，
新版会停止并报错，不再随意选择距离最近的三角面作为标记。

## 验证

在项目根目录执行：

```powershell
python -m unittest discover -s tests/unit -v
python -m compileall scripts tests
```

完整目标、物理原则和开发优先级见 [PROJECT_STARTUP.md](PROJECT_STARTUP.md)。
