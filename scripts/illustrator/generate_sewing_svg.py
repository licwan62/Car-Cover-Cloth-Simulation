"""Convert horizontal TOP/LEFT/RIGHT panel patterns to a semantic sewing SVG.

Run with an input path and optional -o output.svg; without arguments opens a
file picker. Only Python's standard library is needed. Original inputs are
never overwritten. Geometry is split, not fitted to a different car template.
"""

import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET


SVG = "http://www.w3.org/2000/svg"
TOKEN = re.compile(r"[A-Za-z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
EPS = 1e-6


def near(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1])) < EPS


def parse_path(data):
    """Return closed contour segments (start, end, cubic-controls-or-None)."""
    if TOKEN.sub("", data).replace(",", "").strip():
        raise ValueError("Invalid SVG path data")
    tokens = TOKEN.findall(data)
    index = 0
    command = None
    cursor = (0.0, 0.0)
    start = None
    control = None
    previous = None
    segments = []
    closed = False

    def number():
        nonlocal index
        if index >= len(tokens) or tokens[index].isalpha():
            raise ValueError("Missing SVG path coordinate")
        value = float(tokens[index])
        index += 1
        return value

    def point(relative):
        x, y = number(), number()
        return (x + cursor[0], y + cursor[1]) if relative else (x, y)

    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
        if command is None or closed:
            raise ValueError("Expected one closed contour per PANEL")
        kind, relative = command.upper(), command.islower()
        if kind not in "MLHVCSQ TZ".replace(" ", ""):
            raise ValueError(f"Unsupported path command {command}; convert arcs to Bezier curves")
        if kind == "M":
            if start is not None:
                raise ValueError("Multiple contours in one PANEL are not supported")
            cursor = start = point(relative)
            command = "l" if relative else "L"
            previous = "M"
            continue
        if start is None:
            raise ValueError("PANEL path must start with M")
        controls = None
        if kind == "Z":
            end = start
            closed = True
            command = None
        elif kind == "L":
            end = point(relative)
        elif kind == "H":
            x = number()
            end = (x + cursor[0] if relative else x, cursor[1])
        elif kind == "V":
            y = number()
            end = (cursor[0], y + cursor[1] if relative else y)
        elif kind in {"C", "S"}:
            if kind == "C":
                first = point(relative)
            else:
                first = tuple(2 * a - b for a, b in zip(cursor, control)) if previous in {"C", "S"} else cursor
            second, end = point(relative), point(relative)
            controls = (first, second)
            control = second
        else:
            if kind == "Q":
                quadratic = point(relative)
            else:
                quadratic = tuple(2 * a - b for a, b in zip(cursor, control)) if previous in {"Q", "T"} else cursor
            end = point(relative)
            controls = (
                tuple(a + (b - a) * 2 / 3 for a, b in zip(cursor, quadratic)),
                tuple(a + (b - a) * 2 / 3 for a, b in zip(end, quadratic)),
            )
            control = quadratic
        if controls is not None or not near(cursor, end):
            segments.append((cursor, end, controls))
        cursor, previous = end, kind
    if not closed or len(segments) < 3:
        raise ValueError("Each PANEL must be a closed, non-degenerate contour")
    return segments


def contour(element):
    kind = element.tag.rsplit("}", 1)[-1]
    if kind == "path":
        return parse_path(element.get("d", ""))
    if kind == "rect":
        if float(element.get("rx", 0)) or float(element.get("ry", 0)):
            raise ValueError("Convert rounded rectangles to paths first")
        x, y, w, h = (float(element.get(k, 0)) for k in ("x", "y", "width", "height"))
        if min(w, h) <= 0:
            raise ValueError("PANEL rectangle has invalid dimensions")
        return parse_path(f"M{x},{y}h{w}v{h}h{-w}Z")
    raise ValueError(f"Unsupported PANEL geometry: {kind}")


def path_data(segments, closed=False):
    def point(p):
        return f"{p[0]:.10g},{p[1]:.10g}"
    result = ["M" + point(segments[0][0])]
    for _start, end, controls in segments:
        result.append("L" + point(end) if controls is None else
                      "C" + " ".join(point(p) for p in (*controls, end)))
    return " ".join(result) + (" Z" if closed else "")


def left_to_right(segments):
    if segments[0][0][0] <= segments[-1][1][0]:
        return segments
    return [(end, start, tuple(reversed(controls)) if controls else None)
            for start, end, controls in reversed(segments)]


def split_panel(segments, top=False):
    """Recognize the straight hem edges in the supplied horizontal layout."""
    xs = [p[0] for a, b, c in segments for p in (a, b, *(c or ()))]
    low, high = min(xs), max(xs)
    width = high - low
    if width <= EPS:
        raise ValueError("PANEL has no longitudinal extent")
    if not top:
        candidates = [i for i, (a, b, c) in enumerate(segments)
                      if c is None and abs(a[1] - b[1]) < EPS
                      and abs(a[0] - b[0]) >= width * 0.9]
        if len(candidates) != 1:
            raise ValueError("Side PANEL needs one unambiguous long horizontal HEM edge")
        i = candidates[0]
        return left_to_right(segments[i + 1:] + segments[:i]), [segments[i]]
    ends = [i for i, (a, b, c) in enumerate(segments)
            if c is None and abs(a[0] - b[0]) < EPS
            and (abs(a[0] - low) < EPS or abs(a[0] - high) < EPS)]
    if len(ends) != 2 or abs(segments[ends[0]][0][0] - segments[ends[1]][0][0]) < EPS:
        raise ValueError("TOP needs two vertical end HEM edges at opposite X extremes")
    i, j = sorted(ends)
    chains = [segments[i + 1:j], segments[j + 1:] + segments[:i]]
    if not all(chains):
        raise ValueError("TOP seam contours are empty")
    # In Illustrator coordinates, the upper TOP edge pairs with PANEL_LEFT.
    chains.sort(key=lambda chain: sum(a[1] + b[1] for a, b, _ in chain) / (2 * len(chain)))
    hems = sorted(([segments[i]], [segments[j]]), key=lambda chain: chain[0][0][0])
    return [left_to_right(chain) for chain in chains], hems


def convert_tree(root, front="right"):
    if front not in {"left", "right"}:
        raise ValueError("front must be left or right")
    panels = {}

    def visit(element, transformed=False):
        transformed = transformed or bool(element.get("transform"))
        name = element.get("id", "")
        if name.startswith("PANEL_"):
            if name not in {"PANEL_TOP", "PANEL_LEFT", "PANEL_RIGHT"}:
                raise ValueError(f"Unexpected panel {name}")
            if name in panels:
                raise ValueError(f"Duplicate {name}")
            if transformed:
                raise ValueError("Apply SVG transforms before conversion")
            panels[name] = contour(element)
        for child in element:
            visit(child, transformed)

    visit(root)
    if set(panels) != {"PANEL_TOP", "PANEL_LEFT", "PANEL_RIGHT"}:
        raise ValueError("Input requires PANEL_TOP, PANEL_LEFT and PANEL_RIGHT")
    output = ET.Element(f"{{{SVG}}}svg", {k: v for k, v in root.attrib.items()
                                        if k in {"width", "height", "viewBox", "version"}})
    groups = {name: ET.SubElement(output, f"{{{SVG}}}g", id=name)
              for name in ("PANEL", "SEAM", "HEM")}

    def add(layer, name, segments, closed=False):
        ET.SubElement(groups[layer], f"{{{SVG}}}path", {
            "id": name, "d": path_data(segments, closed), "fill": "none",
            "stroke": {"PANEL": "#39b54a", "SEAM": "#c1272d", "HEM": "blue"}[layer],
            "stroke-width": "3", "stroke-linecap": "square", "stroke-linejoin": "round",
        })

    for name, segments in panels.items():
        add("PANEL", name, segments, True)
    for side, seam_id in (("LEFT", "S001"), ("RIGHT", "S002")):
        seam, hem = split_panel(panels[f"PANEL_{side}"])
        add("SEAM", f"{seam_id}_{side}", seam)
        add("HEM", f"HEM_{side}", hem)
    seams, hems = split_panel(panels["PANEL_TOP"], top=True)
    for seam_id, seam in zip(("S001", "S002"), seams):
        add("SEAM", f"{seam_id}_TOP", seam)
    for name, hem in zip(("REAR", "FRONT") if front == "right" else ("FRONT", "REAR"), hems):
        add("HEM", f"HEM_TOP_{name}", hem)
    return output


def convert_file(source, destination=None, front="right"):
    source = Path(source)
    destination = Path(destination) if destination else source.with_name(source.stem + "_sewing.svg")
    if source.resolve() == destination.resolve():
        raise ValueError("Output must differ from the original input")
    output = convert_tree(ET.parse(source).getroot(), front)
    ET.register_namespace("", SVG)
    ET.indent(output, space="  ")
    # Exclusive creation prevents silently replacing an existing semantic file.
    with destination.open("xb") as stream:
        ET.ElementTree(output).write(stream, encoding="utf-8", xml_declaration=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="PANEL-only SVG")
    parser.add_argument("-o", "--output")
    parser.add_argument("--front", choices=("left", "right"), default="right",
                        help="Car front in the flat SVG (default: right, as in Tesla reference)")
    args = parser.parse_args()
    if not args.input:
        from tkinter import Tk, filedialog
        window = Tk()
        window.withdraw()
        args.input = filedialog.askopenfilename(title="选择仅含 PANEL 的 SVG", filetypes=[("SVG", "*.svg")])
        window.destroy()
        if not args.input:
            return
    try:
        output = convert_file(args.input, args.output, args.front)
    except (ValueError, OSError, ET.ParseError) as error:
        parser.exit(1, f"Conversion failed: {error}\n")
    print(f"Created {output}: 3 PANEL, 4 SEAM (2 pairs), 4 HEM")


if __name__ == "__main__":
    main()
