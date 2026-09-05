下面给你一份适合直接放进项目根目录、交给 Codex 继续优化的说明文档。建议文件名：

`PROJECT_STARTUP.md`

---

# Car Cover Cloth Simulation Project

## 1. 项目目标

本项目用于建立一套基于 **Illustrator 车罩二维版型 + Blender 汽车三维模型** 的车罩适配模拟系统。

核心目标不是制作视觉渲染，而是模拟真实车罩由二维裁片缝合后套在汽车上的状态，用于判断：

- 版型是否可以正常套上目标车型；
- 顶片、侧片长度是否充足；
- 前后保险杠包覆是否足够；
- A 柱、C 柱、轮眉等位置是否过紧；
- 是否存在局部余布过多；
- 是否存在左右不对称；
- 下摆位置是否合理；
- 版型是否存在明显张力集中；
- 某一套通用版型能够覆盖哪些车型；
- 为后续车罩 SIZE / SHAPE 分类提供实际几何验证依据。

长期目标是：

```text
Illustrator AI 版型
        +
汽车 3D 模型
        ↓
自动生成 Cloth Mesh
        ↓
自动 Sewing
        ↓
自动 Collision
        ↓
自动 Cloth Simulation
        ↓
Fit Analysis
        ↓
PASS / MARGINAL / FAIL
```

最终希望支持大量车型批量适配测试。

---

# 2. 当前技术路线

当前主要使用：

- Adobe Illustrator
- SVG
- Blender
- Blender Python API
- Cloth Simulation
- Collision
- Sewing Springs
- Constrained Delaunay Triangulation

当前流程：

```text
AI 版型
↓
规范化 PANEL / SEAM / MARK
↓
导出 SVG
↓
Blender 导入
↓
Convert to Mesh
↓
清理 / 自动闭合 Boundary
↓
生成均匀 Cloth Mesh
↓
排列裁片
↓
建立 Sewing
↓
生成汽车 Collision Proxy
↓
设置 Cloth 参数
↓
模拟套车
↓
分析结果
```

---

# 3. 当前车罩结构

目前主要测试的是三片式车罩：

```text
TOP
LEFT
RIGHT
```

即：

- 一块顶片；
- 一块左侧片；
- 一块右侧片。

后续可能增加：

```text
FRONT
REAR
MIRROR_LEFT
MIRROR_RIGHT
```

以及：

- 镜耳；
- 弹力下摆；
- 前后插片；
- 特殊车型局部裁片。

因此系统设计不能只针对三片式版型。

应该支持任意数量 PANEL。

---

# 4. Illustrator 工程规范

Illustrator 是整个自动化流程的数据源。

未来尽量避免让 Blender 根据几何位置“猜”哪个边应该缝合。

AI 文件需要保存明确的语义。

推荐图层结构：

```text
00_REFERENCE
01_PANEL
02_SEAM
03_MARK
04_PIN
05_HEM
99_NOTE
```

---

## 4.1 PANEL

真实生产裁片放在：

```text
01_PANEL
```

例如：

```text
PANEL_TOP
PANEL_LEFT
PANEL_RIGHT
```

要求：

- 每块 PANEL 为独立闭合 Path；
- 不允许自交；
- 不允许重复 Path；
- 不允许隐藏的重复边界；
- 不应 Expand Stroke；
- PANEL 几何来源必须与真实生产版型一致。

Blender 中 Cloth Mesh 必须根据 PANEL 生成。

---

# 5. Sewing 命名规范

缝合关系不得依赖 Blender 自动猜测。

推荐：

```text
S001_TOP
S001_LEFT

S002_TOP
S002_RIGHT
```

规则：

同一个 Sewing ID：

```text
S001
```

代表一组物理缝线。

因此：

```text
S001_TOP
↔
S001_LEFT
```

必须自动配对。

例如：

```text
S002_TOP
↔
S002_RIGHT
```

---

# 6. Sewing 方向

需要避免：

```text
TOP FRONT
→
SIDE REAR
```

这种反向 Sewing。

因此每条 Sewing 建议存在方向标记：

```text
S001_TOP_A
S001_TOP_B

S001_LEFT_A
S001_LEFT_B
```

强制：

```text
A → A
B → B
```

Blender 自动化时不应该再通过空间距离猜 SAME / REVERSE。

如果 AI 中存在方向定义，则 AI 数据优先级最高。

---

# 7. MARK 规范

推荐存在：

```text
FRONT_TOP
FRONT_LEFT
FRONT_RIGHT
```

用于告诉程序每块裁片：

- 哪一边是 FRONT；
- 哪一边是 REAR；
- 自动 Arrangement 时如何旋转。

还建议：

```text
CENTER_TOP
```

表示顶片中心区域。

该 MARK 可用于：

- 自动定位汽车中心；
- 自动创建临时 PIN；
- 检测车罩前后滑移。

---

# 8. PIN 设计

当前模拟发现，车罩完全自由状态下会出现：

```text
后部布料较重
↓
沿车顶向后滑
↓
前部看起来假性偏短
```

因此引入：

```text
PIN_ROOF
```

但 Pin 的作用仅用于：

**初始化定位。**

不应该把大面积车顶永久固定。

推荐：

- 车顶 B 柱附近；
- 小范围；
- 约 5～15 个 Cloth 顶点；
- 使用较低 Weight；
- 最终 Fit 判断阶段应释放或明显降低 Pin。

Pin 的目标：

```text
限制整罩前后漂移
```

而不是：

```text
支撑版型
```

---

# 9. HEM 规范

建议 Illustrator 中定义：

```text
HEM_LEFT
HEM_RIGHT
HEM_FRONT
HEM_REAR
```

用于后续：

- 下摆位置判断；
- 弹力带模拟；
- 下摆长度测量；
- Shrink / Elastic；
- 离地高度计算。

未来可增加：

```text
ELASTIC_HEM
```

参数。

---

# 10. SVG 导出

当前使用 SVG 作为：

```text
Illustrator
→
Blender
```

中间格式。

推荐：

```text
Object ID = Layer / Object Name
Decimals = 4
Responsive = OFF
Minify = OFF
```

同时保留：

```text
SCALE_1000MM
```

校准线。

理论上 Blender 可以自动：

```text
测量 SCALE_1000MM
↓
换算比例
↓
1000 mm = 1 Blender Meter
```

避免人工 Scale。

---

# 11. Cloth Mesh 生成

不采用：

- Grid Fill；
- QuadriFlow；
- 普通 N-gon Triangulate。

这些方法在复杂版型上容易产生：

```text
超长三角形
极小三角形
边缘尖刺
不均匀 Cloth Spring
```

当前推荐：

```text
Boundary
↓
均匀重新采样
↓
内部六角 / 均匀采样
↓
Constrained Delaunay Triangulation
↓
Uniform Triangle Cloth Mesh
```

当前测试目标网格尺寸：

```text
约 50 mm
```

推荐标准：

```text
快速测试：
60～70 mm

正式 Fit：
40～50 mm

高精度：
25～35 mm
```

目前建议整个项目固定：

```text
50 mm
```

作为标准 Fit Simulation 网格。

这样不同车型之间的模拟结果具有可比性。

---

# 12. Cloth Mesh 要求

生成后的 Cloth Mesh 必须：

- 单层；
- 法线一致；
- 无重复面；
- 无重叠面；
- 无孤立 Edge；
- 无 Degenerate Face；
- 无异常极细三角形；
- Boundary 清晰；
- 平均网格尺寸稳定。

Sewing 之前：

```text
Loose Edge = 0
```

Sewing 之后：

Loose Edge 应仅包含：

```text
Sewing Springs
```

---

# 13. Sewing Springs

Blender Cloth Sewing 使用：

```text
Loose Edge
```

连接两个 Cloth Boundary Vertex。

正确结构：

```text
TOP
A1 ●────● B1
A2 ●────● B2
A3 ●────● B3
A4 ●────● B4
```

这些 Edge：

```text
有 Edge
无 Face
```

用于 Sewing Springs。

---

# 14. Sewing 安全规则

之前测试中，最大的不稳定来源之一是错误 Sewing。

因此以后自动 Sewing 必须采用严格 Fail-Safe。

必须检查：

### 缝边长度

例如：

```text
TOP = 4860 mm
SIDE = 4830 mm
```

正常。

如果差距过大：

```text
> 10～15%
```

应给出警告或拒绝模拟。

---

## Sewing Spring 初始距离

不应让 Sewing Spring 跨越很大的空间。

推荐：

```text
30～100 mm
```

可接受：

```text
< 200～300 mm
```

如果出现：

```text
500～1000 mm+
```

优先重新 Arrangement。

不要依靠极大 Sewing Force 强行缝。

---

# 15. Arrangement

当前较稳定的初始布局：

```text
             TOP
        ─────────────
             ↓
          CAR ROOF

LEFT                     RIGHT
  │                         │
  │          CAR            │
  │                         │
```

裁片距离汽车：

```text
约 50～150 mm
```

Sewing 边之间：

```text
约 30～100 mm
```

尽量让对应缝边：

```text
位置接近
方向近似平行
```

避免 Sewing Spring 初始长度过长。

---

# 16. Sewing Force

不要使用：

```text
Max Sewing Force = 0
```

因为 0 表示：

```text
Unlimited
```

容易导致模拟开始瞬间爆炸。

当前推荐从：

```text
5～10
```

开始。

目标是：

```text
20～60 Frame
```

逐渐完成 Sewing。

而不是 3～5 Frame 瞬间拉死。

---

# 17. 汽车 Collision

不建议直接使用高模车辆做 Cloth Collision。

完整车辆通常包含：

- 车灯；
- 格栅；
- 门缝；
- 内饰；
- 轮毂；
- 底盘；
- 多层玻璃；
- 雨刷；
- Logo；
- 复杂小凹槽。

这些会产生大量 Cloth Trap。

---

# 18. Collision Proxy

当前策略：

```text
CAR_RENDER
↓
复制
↓
合并
↓
Voxel Remesh
↓
Smooth
↓
Decimate
↓
CAR Collision Proxy
```

目标：

生成光滑连续的：

```text
车辆外壳
```

而不是漂亮的低模车。

推荐命名：

如果原车：

```text
Tesla Model X 2020
```

则：

```text
Tesla Model X 2020 Collision
```

Mesh：

```text
Tesla Model X 2020 Collision Mesh
```

---

# 19. Collision Proxy 推荐参数

当前建议：

```text
Voxel Size
≈ 30 mm
```

范围：

```text
20 mm
精细

30 mm
推荐

40 mm
更稳定

50 mm
快速测试
```

目标 Faces：

```text
20,000～50,000
```

当前：

```text
约 30,000
```

---

# 20. Collision Thickness

当前推荐：

```text
5～10 mm
```

通常：

```text
7 mm
```

作为默认值。

过大：

```text
会产生明显悬空
```

过小：

```text
容易穿模
```

---

# 21. Collision Friction

车罩容易沿车顶向后滑。

因此需要：

```text
CAR Collision Friction
```

而不是单纯依靠 Pin。

建议测试：

```text
5
10
15
20
```

目标：

```text
允许局部布料重新分配
+
限制整罩持续向后滑移
```

不能过大，否则会出现：

```text
布碰到车身后被锁死
```

导致假张力。

---

# 22. Cloth 材料目标

当前目标材料：

```text
210D Oxford Fabric
```

不是：

- Silk；
- Cotton；
- Rubber；
- Leather。

其力学行为应表现为：

```text
比 Cotton 硬挺
比 Denim 更轻
比 Leather 更柔
低拉伸
较强抗剪
中高抗弯
```

视觉上：

错误：

```text
/\/\/\/\/\/\/\/\
大量非常细碎褶皱
```

目标：

```text
_____/¯¯\________/¯\____
较少、更大的自然褶皱
```

---

# 23. Cloth 参数原则

当前调参优先级：

```text
Bending
>
Shear
>
Compression
>
Tension
```

Bending 是减少小碎褶皱的关键。

但版型验证时：

```text
Tension
```

不能过软。

否则版型偏小也会被 Blender 拉伸后“假装适配”。

---

# 24. Mass

Blender Cloth Mass 与：

```text
Mesh Vertex Count
```

相关。

因此不能简单把现实克重直接转换成 Blender Mass。

项目应该固定：

```text
Cloth Mesh Edge ≈ 50 mm
```

然后校准一套：

```text
Oxford_210D_V1
```

后续所有车型统一使用。

不能每台车型使用不同 Cloth 参数。

---

# 25. Self Collision

Self Collision 用于防止：

```text
Cloth
穿过
Cloth
```

不是用来增加硬度。

当前推荐距离：

```text
约 5 mm
```

不要相对于 50 mm Cloth Mesh 设置得太大。

否则容易出现：

```text
布料像带巨大气垫
```

以及：

```text
Fold Explosion
```

---

# 26. Simulation 推荐流程

不要一开始同时启用：

```text
Sewing
Gravity
Collision
Self Collision
Pin
```

推荐分阶段。

---

## Stage 1：Sewing

```text
Gravity = 0
Self Collision = OFF
Car Collision = OFF

Sewing ON
```

目标：

```text
先把裁片缝成正确罩体
```

---

## Stage 2：落车

```text
Gravity = ON
Car Collision = ON
Self Collision = OFF
```

目标：

```text
让车罩自然落在车辆上
```

---

## Stage 3：真实褶皱

```text
Self Collision = ON
```

目标：

```text
处理布料自身接触
```

---

## Stage 4：Fit 判断

最终：

```text
Pin 降低 / 释放
```

让整个系统达到自然平衡。

Fit 判断应该基于最终自由状态。

---

# 27. 当前已发现问题

### 27.1 SVG 多段 Path

Ctrl+J：

```text
只 Join Object
```

不会：

```text
自动 Weld Boundary
```

因此需要自动：

- Endpoint Detection；
- Remove Doubles；
- Small Gap Bridge；
- Boundary Validation。

---

### 27.2 Sewing Group 误选

Vertex Group 中可能存在：

- 孤点；
- 内部点；
- 多段边；
- Branch；
- 错误 Segment。

长期应该通过 AI 的：

```text
S001_*
```

定义消除这个问题。

不要依靠 Blender 猜。

---

### 27.3 后滑

后半部分车罩面积较大时会：

```text
Gravity
↓
沿车顶向后滑
```

从而产生：

```text
前部假性偏短
```

解决：

- Collision Friction；
- 小范围弱 PIN_ROOF；
- 合理 Mass；
- 最终释放 Pin 后判断。

---

### 27.4 局部穿模

常见于：

- 高模 Collision；
- Sewing Force 过高；
- Self Collision 太早启用；
- Cloth 起始位置穿入车身。

解决：

- Collision Proxy；
- 降低 Sewing Force；
- 分阶段 Simulation；
- 增加 Quality；
- 合理 Collision Thickness。

---

# 28. Fit 判断原则

不能仅凭：

```text
最终图片看起来套不上
```

就判断 FAIL。

必须排除：

- 整体滑移；
- Collision 卡住；
- Cloth 穿模；
- Sewing 错位；
- Pin 约束；
- 模拟尚未稳定。

---

# 29. 未来需要计算的 Fit Metrics

建议逐步实现：

```text
MAX_STRETCH
P95_STRETCH

HEM_CLEARANCE_FRONT
HEM_CLEARANCE_REAR
HEM_CLEARANCE_LEFT
HEM_CLEARANCE_RIGHT

SEAM_STRAIN

COLLISION_PENETRATION

PIN_DISPLACEMENT

COVER_CENTER_OFFSET

FRONT_COVERAGE
REAR_COVERAGE

LEFT_COVERAGE
RIGHT_COVERAGE
```

---

# 30. Fit Result

最终分类：

```text
PASS
MARGINAL
FAIL
```

例如：

```text
PASS
最大 Stretch < 3%
关键下摆覆盖正常
无持续穿模
```

```text
MARGINAL
局部高张力
局部覆盖不足
但可能仍可实际使用
```

```text
FAIL
无法覆盖保险杠
持续高张力
版型明显不足
```

阈值后续通过实际车罩测试校准。

---

# 31. 推荐项目结构

建议 Codex 后续逐渐整理成：

```text
car-cover-simulation/

README.md
PROJECT_STARTUP.md

config/
    cloth/
        oxford_210d.json

    simulation.json

    fit_thresholds.json

illustrator/
    MASTER.ai

    export/
        pattern.svg
        pattern.json

blender/
    vehicle.blend

scripts/
    illustrator/
    blender/

output/
    simulation/

    reports/

    debug/

tests/
    patterns/

    vehicles/
```

---

# 32. 推荐模块化结构

未来 Blender 自动化不要继续堆一个超长脚本。

建议拆成：

```text
import_pattern

validate_pattern

repair_boundary

generate_cloth_mesh

parse_seams

arrange_panels

generate_sewing

generate_collision_proxy

setup_cloth

setup_pin

run_simulation

analyze_fit

export_report
```

每个模块应该可以独立测试。

---

# 33. 自动化目标

最终希望 CLI / Blender Operator 类似：

```text
Input:

pattern.svg
vehicle.blend
cloth_config

↓
Run

Output:

simulation.blend
fit_report.json
fit_report.csv
preview.png
```

---

# 34. 自动化优先级

推荐 Codex 按以下优先级优化。

### P0

稳定数据管道：

```text
AI
→ SVG
→ PANEL识别
→ Cloth Mesh
```

---

### P1

可靠 Sewing：

```text
S001
A→A
B→B
```

彻底取消空间猜测。

---

### P2

Collision Proxy：

```text
复杂车辆
→
稳定 Collision 外壳
```

---

### P3

Simulation Setup：

统一：

- Oxford Cloth；
- Collision；
- Friction；
- Pin；
- Sewing Force；
- Quality。

---

### P4

Fit Metrics：

从“肉眼判断”升级成：

```text
数值判断
```

---

### P5

Batch Processing：

例如：

```text
一个车罩版型
↓
100 台汽车
↓
批量模拟
↓
Fit Matrix
```

---

# 35. 当前阶段不要做的事情

暂时避免：

### 不要追求高质量渲染

当前系统目标：

```text
Geometry Validation
```

不是：

```text
Advertising Render
```

---

### 不要把 Cloth Mesh 做得过密

当前：

```text
50 mm
```

已经足够验证版型。

---

### 不要在 Sewing 错误时调材质参数

如果 Sewing：

```text
A → B
```

连接错了，任何 Cloth 参数都救不了。

---

### 不要用高模汽车直接 Collision

应该统一：

```text
Collision Proxy
```

---

### 不要让 Pin 影响最终 Fit 判断

Pin 仅用于：

```text
初始化定位
```

---

# 36. 项目最终价值

该系统最终不是一个单纯的 Blender Cloth Demo。

它应该成为：

> **车罩版型与车型三维几何之间的数字化 Fit Validation 工具。**

核心输入：

```text
车罩二维纸样
+
车辆三维几何
```

核心输出：

```text
这套车罩版型
是否适用于
这台车型
```

并进一步支持：

```text
版型优化
↓
车型分组
↓
SKU SIZE 分组
↓
车型适配数据库
↓
生产版型决策
```

因此后续开发优先考虑：

**稳定性、可重复性、批处理能力、可量化结果**

而不是单次模拟画面是否漂亮。