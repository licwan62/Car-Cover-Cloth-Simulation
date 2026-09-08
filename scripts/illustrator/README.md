# Illustrator Automation

此目录预留给 AI 图层校验、命名规范化和 SVG/JSON 导出脚本。新增脚本应把 `01_PANEL`、`02_SEAM`、`03_MARK`、`04_PIN`、`05_HEM` 的语义原样写入中间数据，不得让 Blender 根据空间位置猜测。

## 从 PANEL 自动生成 sewing SVG

`generate_sewing_svg.py` 在 Illustrator 导出阶段识别三片式车罩轮廓，输出显式的
`PANEL`、`SEAM`、`HEM` 分组，供 Blender 的 `generate_sewing_standalone.py` 使用。
只依赖 Python 标准库；无参数运行会打开 SVG 文件选择窗口。

```powershell
python scripts/illustrator/generate_sewing_svg.py "scripts/illustrator/SVG/Dodge Challenger 495-125 (+12).svg" -o "scripts/illustrator/Dodge Challenger 495-125 (+12)_sewing.svg"
```

不指定 `-o` 时，在输入旁生成 `<原文件名>_sewing.svg`。原文件保持不变，已有输出也不会被覆盖；再次生成请使用新输出文件名。

输入要求与 Tesla 参考文件的排版相同：

- 包含命名几何 `PANEL_TOP`、`PANEL_LEFT`、`PANEL_RIGHT`，可位于根节点或图层中。
- 版片长轴沿 SVG X 轴，LEFT 对应 TOP 上边，RIGHT 对应下边。
- 侧片各有一条横跨至少 90% 长度的水平直线下摆，其余连续轮廓为缝线。
- TOP 两端各有一条竖直直线下摆，长边允许收腰、曲线。
- 默认 SVG 右端是车头；反向版型加 `--front left`。车头方向无法仅凭三片轮廓可靠推断。
- 支持闭合 `path`（M/L/H/V/C/S/Q/T/Z）及普通 `rect`。请先应用 transform，将圆弧转换为贝塞尔路径；歧义轮廓会明确报错。

输出命名与参考文件一致：`S001_LEFT` ↔ `S001_TOP`、`S002_RIGHT` ↔ `S002_TOP`，
以及 `HEM_LEFT`、`HEM_RIGHT`、`HEM_TOP_FRONT`、`HEM_TOP_REAR`。
曲线保留原始几何，平滑/二次曲线转换为 sewing 读取器支持的三次贝塞尔 C 命令。
这是专用于上述三片式布局的识别器，输出重建这三个语义分组，不复制输入的其他辅助图层。

在 Blender 中导入输出 SVG 的 PANEL 制作布料网格，再运行
`scripts/blender/generate_sewing_standalone.py` 并选择同一个输出 SVG。
