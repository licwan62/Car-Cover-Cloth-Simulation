# Illustrator Input

建议图层：`00_REFERENCE`、`01_PANEL`、`02_SEAM`、`03_MARK`、`04_PIN`、`05_HEM`、`99_NOTE`。

- 生产裁片放在 `01_PANEL`，每片是独立、无自交、无重复边的闭合 Path。
- Sewing 使用同一 ID 的两个 Panel 路径，并提供 A/B 方向标记。
- 导出文件放在 `export/`；推荐 SVG 保留对象名称、4 位小数、关闭 Responsive 与 Minify。
- 保留名为 `SCALE_1000MM` 的校准线，以便自动换算 `1000 mm = 1 Blender meter`。
