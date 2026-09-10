# Illustrator Automation

此目录预留给 AI 图层校验、命名规范化和 SVG/JSON 导出脚本。新增脚本应把 `01_PANEL`、`02_SEAM`、`03_MARK`、`04_PIN`、`05_HEM` 的语义原样写入中间数据，不得让 Blender 根据空间位置猜测。

## 从 PANEL 自动生成 sewing SVG

`generate_sewing_svg.py` 在 Illustrator 导出阶段识别三片式车罩轮廓，输出显式的
`PANEL`、`SEAM`、`HEM` 分组，供 Blender 的 `generate_sewing.py` 使用。
Python 端只依赖标准库；直接读取 `.ai` 需要 Windows 和已安装的 Adobe Illustrator，
通过 PowerShell COM 调用同目录的 `read_panel.jsx`。无参数运行会打开 AI/SVG 文件选择窗口。

```powershell
python scripts/illustrator/generate_sewing_svg.py "illustrator/皮卡/PK-L_0814.ai" -o "scripts/illustrator/SVG/PK-L_0814_sewing.svg"
```

AI 输入读取唯一的 `PANEL`（也接受 `01_PANEL`）图层下的 `PANEL_TOP`、
`PANEL_LEFT`、`PANEL_RIGHT` 命名路径、子图层或分组。每个语义节点必须包含且仅包含
一个闭合轮廓；支持单轮廓复合路径，拒绝裁剪、多轮廓和开放路径。名称决定版片身份。
即使 PANEL 隐藏、未写入 PDF 兼容预览，也通过 Illustrator 原生对象读取。
保留三次贝塞尔控制点，并将 Illustrator Y 轴转换为 SVG Y 轴；尺寸包含大画布
`scaleFactor`，以当前画板作为 viewBox。脚本打开磁盘 AI 的临时副本并无保存关闭，
不会读取当前打开文档尚未保存的改动。其他图层不会进入输出。

```powershell
python scripts/illustrator/generate_sewing_svg.py "scripts/illustrator/SVG/Dodge Challenger 495-125 (+12).svg" -o "scripts/illustrator/Dodge Challenger 495-125 (+12)_sewing.svg"
```

不指定 `-o` 时，在项目 `output/sewing_svg/` 下生成 `<原文件名>_sewing.svg`，
并保留输入相对于 `illustrator/` 的子目录（如 `皮卡/`）。目录自动创建。
原文件保持不变，已有输出也不会被覆盖；再次生成请使用新输出文件名。

支持多个文件或目录参数；目录递归处理所有 `.ai`，单个失败不影响后续文件。
批量结果写入 `output/sewing_svg/batch_report.json`，存在失败时退出码为 1。
`-o` 仅适用于单文件转换。

```powershell
python scripts/illustrator/generate_sewing_svg.py "illustrator/定制" "illustrator/皮卡" "illustrator/越野"
```

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
`scripts/blender/generate_sewing.py` 并选择同一个输出 SVG。
