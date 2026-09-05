# Project Startup

本文件是项目入口。完整的业务目标、Illustrator 规范、网格与 Sewing 安全规则、Collision Proxy、分阶段模拟和 Fit Metrics 定义见 [`doc/AGENT.md`](doc/AGENT.md)。

## 当前约束

- 标准 Cloth Mesh 目标边长：50 mm。
- 单位约定：1 Blender Unit = 1 m；配置中的生产尺寸使用 mm。
- 版片数量不得写死为 TOP/LEFT/RIGHT 三片。
- 新 Sewing 数据必须以 `S001` 形式的 ID 显式配对，并使用 A/B 方向标记。
- Pin 只用于初始化定位，最终 Fit 判断前必须降低或释放。
- 高模车辆不得直接用于 Cloth Collision，应生成光滑连续的 Collision Proxy。
- Fit 结论必须排除滑移、卡住、穿模、错缝、Pin 约束和未收敛等模拟故障。

## 开发顺序

1. P0：稳定 AI → SVG → PANEL → Cloth Mesh 数据管道。
2. P1：可靠且方向明确的 Sewing。
3. P2：Collision Proxy。
4. P3：统一 Oxford Cloth、Collision、Friction、Pin、Sewing Force 和 Quality。
5. P4：数值化 Fit Metrics。
6. P5：批量车型处理与 Fit Matrix。

## 当前实现状态

- 已完成现有脚本的职责化命名和目录迁移。
- 已建立版本化 JSON 配置。
- 已提供可脱离 Blender 测试的 Sewing 命名解析与项目配置模块。
- Blender 算法仍以独立脚本执行；统一 Operator/CLI 和完整 Fit 分析尚待实现。
