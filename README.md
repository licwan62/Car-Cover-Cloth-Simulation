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

## 验证

在项目根目录执行：

```powershell
python -m unittest discover -s tests/unit -v
python -m compileall scripts tests
```

完整目标、物理原则和开发优先级见 [PROJECT_STARTUP.md](PROJECT_STARTUP.md)。
