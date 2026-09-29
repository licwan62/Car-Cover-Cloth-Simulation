"""Blender check: project scripts resolve through Preferences > Script Directories.

Run from the project root with the Blender version under test:

    blender --background --factory-startup --python-exit-code 1 --python tests/blender/check_script_directories.py

``--factory-startup`` keeps the user's saved preferences untouched; the script
adds ``<project>/scripts`` as a Script Directory in memory only. Each
config-driven entry point is then loaded as a saved-file Text block and run
like the Text Editor's Run Script button, whose ``__file__`` is
``<blend path>/<text name>`` rather than the file on disk.
"""

from pathlib import Path
import sys
import tempfile

import bpy


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT_ROOT / "scripts"
CONFIG_DRIVEN = SCRIPTS / "blender" / "config_driven"
SAMPLE_SVG = SCRIPTS / "illustrator" / "SVG" / "PK-L_0814_sewing.svg"

failures = []
last_error = []


def check(condition, message):
    print(f"[{'PASS' if condition else 'FAIL'}] {message}")
    if not condition:
        failures.append(message)


def capture_excepthook(exc_type, exc, tb):
    # Blender reports Text block errors through PyErr_Print -> sys.excepthook.
    last_error.append(exc)
    sys.__excepthook__(exc_type, exc, tb)


def add_script_directory():
    directories = bpy.context.preferences.filepaths.script_directories
    entry = directories.new()
    entry.name = "car_cover_project"
    entry.directory = str(SCRIPTS)
    bpy.utils.refresh_script_paths()


def reset_scene():
    bpy.ops.wm.read_homefile(use_empty=True)
    for name in list(sys.modules):
        if name in {"project_config", "seam_naming"} or name.startswith("_cc_"):
            del sys.modules[name]


def select_only(obj):
    for other in bpy.context.view_layer.objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def run_text_block(path):
    """Run a saved script exactly as Text Editor > Run Script does."""

    text = bpy.data.texts.load(str(path))
    last_error.clear()
    try:
        with bpy.context.temp_override(edit_text=text):
            bpy.ops.text.run_script()
    except RuntimeError as error:
        return last_error[-1] if last_error else error
    return None


def check_module_search_path():
    modules = str(SCRIPTS / "modules")
    check(
        any(Path(p) == Path(modules) for p in sys.path),
        "scripts/modules is on sys.path after adding the Script Directory",
    )
    import project_config
    import seam_naming  # noqa: F401

    check(project_config.PROJECT_ROOT == PROJECT_ROOT, "project_config finds project root")
    marks = project_config.load_blender_script("100_mirror_marks.py")
    check(
        callable(getattr(marks, "apply_mirror_markers", None)),
        "load_blender_script loads numbered scripts/blender files",
    )


def check_imports_only(name):
    """Scene-dependent scripts: only module resolution is under test."""

    reset_scene()
    error = run_text_block(CONFIG_DRIVEN / name)
    check(
        not isinstance(error, ImportError),
        f"{name} resolves imports from Text Editor ({type(error).__name__ if error else 'ran'})",
    )


def check_config_cloth():
    reset_scene()
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=10, y_subdivisions=10, size=1.0)
    cloth = bpy.context.active_object
    select_only(cloth)
    error = run_text_block(CONFIG_DRIVEN / "003_cloth_setup.py")
    has_cloth = any(m.type == "CLOTH" for m in cloth.modifiers)
    check(error is None and has_cloth, f"config_driven/003_cloth_setup.py runs ({error!r})")


def check_pasted_standalone_workflow():
    """000_svg_to_cloth.py must work as an unsaved, pasted Text block."""

    reset_scene()
    source = (SCRIPTS / "blender" / "000_svg_to_cloth.py").read_text(encoding="utf-8")
    text = bpy.data.texts.new("pasted_workflow.py")
    text.write(source)
    module = text.as_module()
    try:
        cloth = module.run_workflow(str(SAMPLE_SVG))
    except Exception as error:  # noqa: BLE001 - report any Blender/API failure
        check(False, f"standalone 000_svg_to_cloth.py runs ({error!r})")
        return
    check(
        any(m.type == "CLOTH" for m in cloth.modifiers),
        f"standalone 000_svg_to_cloth.py builds {cloth.name}",
    )


def main():
    print(f"Blender {bpy.app.version_string}, Python {sys.version.split()[0]}")
    sys.excepthook = capture_excepthook
    add_script_directory()
    # Save to a temporary blend so Text blocks get a real "<blend>/<text>" __file__.
    with tempfile.TemporaryDirectory() as tmp:
        blend = Path(tmp) / "script_directory_check.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        check_module_search_path()
        for name in ("000_repair_boundary.py", "001_remesh.py",
                     "002_sew_from_groups.py", "100_mirror_marks.py"):
            check_imports_only(name)
        check_config_cloth()
        check_pasted_standalone_workflow()
    sys.excepthook = sys.__excepthook__
    if failures:
        raise SystemExit(f"{len(failures)} check(s) failed: {failures}")
    print("All Script Directory checks passed.")


main()
