# Blender Scripts

## Naming

Scripts are numbered by workflow stage, matching the Text block names used in
the lab `.blend` files (`000_clothing_from_svg`, `001_remesh`, ...), so Blender's
**Text > Open** dialog lists them in working order:

| Range | Stage |
| --- | --- |
| `0xx` | Main pipeline: SVG → cloth mesh → sewing → cloth setup |
| `1xx` | Non-physical comparison marks on a settled cover |
| `2xx` | Vehicle collision objects |
| `3xx` | Reports and exports |

A `config_driven/` script reuses the number of its standalone counterpart for
the same stage. Numbered files are run, not imported; `project_config.load_blender_script()`
loads one by path when a config-driven wrapper needs its implementation.

## Script index

| Script | Responsibility | Notes |
| --- | --- | --- |
| `000_svg_to_cloth.py` | Import a semantic SVG and run the complete cloth pipeline | One file dialog; embeds `001`–`003` (generated, see below) |
| `001_remesh.py` | Uniform sampling and constrained Delaunay cloth mesh | Embedded settings |
| `002_sew_from_svg.py` | Build Sewing directly from a semantic SVG | Creates PANEL/SEAM/HEM and automatic A/B vertex groups, then arc-length-matched loose edges |
| `003_cloth_setup.py` | Apply the self-contained cloth preset | Animated soft pin springs, object/self collision, and seam material |
| `100_mirror_marks.py` | Mirror-pocket and charge-port position marks | Opens an interactive `MARKER_CONFIG` dialog |
| `101_door_marks.py` | Vertical door-position line on both sides | Interactive distance from the vehicle front |
| `102_plate_marks.py` | Plate-opening mockups on `PANEL_TOP` | Material marks only, not cutouts |
| `200_collision_exterior.py` | Exterior-only drape collider | Six-direction first-hit envelope, gap closing, cavity/island removal, closed-manifold validation |
| `300_export_three_views.py` | Real-size three-view SVG/PNG export | Auxiliary reporting tool |
| `301_export_six_views.py` | Four orthographic and two perspective views | Six PNGs and an embedded SVG atlas |
| `config_driven/000_repair_boundary.py` | Endpoint weld, small-gap bridge, boundary validation | Reads `boundary_repair` |
| `config_driven/001_remesh.py` | Same meshing stage as `001_remesh.py` | Reads `cloth_mesh` |
| `config_driven/002_sew_from_groups.py` | Create Sewing Springs from existing seam vertex groups | Semantic ID pairing, A/B direction, legacy pairs from `sewing` |
| `config_driven/003_cloth_setup.py` | Apply Oxford cloth settings | `config/cloth/oxford_210d.json` (SmoothDrape V2) |
| `config_driven/100_mirror_marks.py` | Same marks as `100_mirror_marks.py` | Reads `mirror_markers`; no dialog |
| `../modules/project_config.py` | Load project JSON; load numbered scripts | Blender-independent shared module |
| `../modules/seam_naming.py` | Parse `S001_PANEL[_A\|_B]` names | Blender-independent shared module |
| `../tools/build_svg_to_cloth.py` | Refresh the payloads embedded in `000_svg_to_cloth.py` | Regular Python, not Blender |

Planned modules from `doc/AGENT.md` that do not yet have production
implementations are intentionally not represented by empty Python files. Add
them with tests as the pipeline grows: `import_pattern`, `validate_pattern`,
`parse_seams`, `arrange_panels`, `setup_pin`, `run_simulation`, `analyze_fit`,
and `export_report`.

## Script organization

Add the project's `scripts` folder (not `scripts/blender`) to Blender
**Preferences > File Paths > Script Directories** once per Blender version
(3.6 or newer), save preferences and restart. Blender then searches only
`scripts/modules` (added to `sys.path`), `scripts/addons` (registered add-ons)
and `scripts/startup` (run at startup). It does not register or run the plain
scripts in `scripts/blender/`; open those in the Text Editor and click
**Run Script**. This project has no `addons` or `startup` content.

- `scripts/blender/*.py` use embedded settings and run without project files,
  including when pasted into an unsaved Text block.
- `scripts/blender/config_driven/*.py` read `config/*.json`. Open the saved file
  from the project path, then Run Script. They import `project_config` and
  `seam_naming` from `scripts/modules`; they do not rely on `__file__`, which
  Blender sets to `<blend path>/<text name>` for Text blocks. Without the Script
  Directory they stop with `project_config not found`.
- `blender --python scripts/blender/config_driven/<name>.py` also works with
  `--factory-startup`: the scripts fall back to `../../modules` beside their
  real file path.
- `config_driven/100_mirror_marks.py` calls
  `project_config.load_blender_script("100_mirror_marks.py")`, which loads a
  fresh copy on every run so edits are never masked by a stale module.

Blender checks (factory settings; saved preferences and scenes are not changed):

```powershell
blender --background --factory-startup --python-exit-code 1 --python tests/blender/check_script_directories.py
blender --background --factory-startup --python-exit-code 1 --python tests/blender/check_collision_exterior.py
```

## 000: One-click SVG cloth workflow

Open `000_svg_to_cloth.py` in Blender's Text Editor and click **Run Script**.
Choose the semantic `_sewing.svg` file in the file dialog. The operator imports
and joins only the curves inside the SVG `PANEL` group, creates the cloth mesh
with `001_remesh.py`, generates semantic sewing from the same source file, and
then applies `003_cloth_setup.py`. Existing vehicle Collision objects remain in
the scene and are discovered by the cloth setup as usual. This is a single-file
standalone script: it can also be pasted into an unsaved Blender Text block and
does not need access to the repository or neighboring Python files.

`000_svg_to_cloth.py` is partly generated. Its sources of truth are
`001_remesh.py`, `002_sew_from_svg.py` and `003_cloth_setup.py`; the operator
code around `_EMBEDDED_SCRIPTS` is edited by hand. After changing any of the
three sources, regenerate from the project root with a regular Python
interpreter (not inside Blender) and commit both files:

```powershell
python scripts/tools/build_svg_to_cloth.py
```

`tests/unit/test_blender_script_paths.py` fails while the embedded copies are
stale.

## 002/003: Sewing and cloth setup

Select the car-cover mesh before running `003_cloth_setup.py`. Selecting a
collider as well is harmless because the cloth script recognizes and skips
meshes with Collision physics. Collider activation does not depend on any
collection name: every Mesh with a Collision modifier in the current scene
participates, while objects that belong only to another scene do not. This
makes switching scenes sufficient to switch vehicle colliders. If an older run
added Cloth to a collider, remove that Cloth modifier.

The self-contained V28 cloth preset first samples a 75-frame free drape during
setup, then returns to Scene Start for the guided replay. Frames 45-65 ramp
soft pin spring forces on every semantic `HEM` / `HEM_*` vertex; frames 65-75
hold the targets at one world-Z height. This corrects both left/right and
front/rear target differences rather than just shifting two group averages.
The default target is the global HEM mean at frame 45. Override
`HEM_FEEDBACK_TARGET_Z` in metres to choose a specific plane.

Each vertex target retains its sampled free-drape X/Y trajectory while Z moves
smoothly toward the common plane. Soft pins can exert horizontal forces if the
guided cloth departs from that trajectory; they are not Z-only constraints.
`HEM_LEVEL_PIN_WEIGHT` defaults to 0.8. The setup rejects a target more than
350 mm from any sampled HEM vertex at frame 45. Tiny initial HEM weights keep
spring constraints available before the late acquisition. Roof pins retain
their early hold/release schedule. Dynamic rest-mesh correction stays disabled.
Vehicle collisions remain enabled, but exact final leveling depends on contact,
pin weight and available cloth length. Inspect the final result before baking.

Free the old Cloth bake before setup and replay sequentially from Scene Start.
Setup runs a full free simulation and stores one trajectory key per frame, so
it costs time and memory on large meshes. Fixed Shape Keys and frame drivers
avoid modifying geometry from simulation handlers. Weld and subdivision are
only disabled temporarily while sampling, then their visibility is restored.
Rerun setup after changing geometry or physical parameters.

Both `002_sew_from_svg.py` and the cloth setup preflight reject a vertex
connected to more than two loose sewing edges. Such a many-to-one hub is a
topology error that creates the tail "black-hole" effect; increasing Sewing
force would make it worse rather than correct it.

## 100: Mirror-position comparison marks

Artboard 1 of `illustrator/TESLA-MODELX.ai` places the mirror-pocket center
1600 mm behind the front-bottom endpoint and 1020 mm above it. The left-side
charge-port center is 340 mm from the rear-bottom endpoint and 820 mm above it.
At the settled comparison frame, activate the Cloth mesh and run
`config_driven/100_mirror_marks.py`. The evaluated `PANEL_LEFT` and
`PANEL_RIGHT` vertex groups provide separate side-panel coordinate references,
so `PANEL_TOP` and vehicle Collision bounds cannot shift the marks. The script
paints small left/right mirror marks orange-red and the left charge-port mark
blue. It does not create a mirror-pocket mesh or affect Cloth, Collision, mass,
sewing, or Fit geometry. If the vehicle front axis differs from the Model X
scene's default -Y, change `mirror_markers.front_axis` in
`config/simulation.json`.

## 200: Exterior-only collision envelope

Run `200_collision_exterior.py` in Blender's Text Editor in Object Mode,
with the original vehicle meshes selected. The new `* Exterior Collision` mesh
is selected on completion. Sources and their modifiers remain unchanged. If
sources or older proxies already have Collision enabled, disable those colliders
before simulating so the cloth only contacts the new shell.

The script samples the closest evaluated surface from both ends of world X/Y/Z
rays. It fills the spans between opposing exterior hits, closes small gaps, and
extracts/remeshes that envelope instead of remeshing or decimating the source
parts. Hidden interior surfaces do not change the first hits. Single-sided
panels are sampled too. Only the largest spatial component is retained;
enclosed cavity surfaces and detached islands are removed. Output must pass
closed-manifold and nonzero-volume checks before Collision is added.

Defaults: `VOXEL_SIZE_MM=40`, `GAP_CLOSE_CELLS=1`, `TARGET_TRIANGLES=12000`,
1 mm collision margin, double-sided collision. Millimetres respect the scene
unit scale. High-poly input is used for BVH queries without pre-decimation;
grid and evaluated-triangle budgets reject excessive allocations. Reduce voxel
size for finer features at greater processing/memory cost. The triangle target
is approximate, not a hard cap. Progress is printed to Blender's console.

The envelope deliberately bridges concavities, wheel wells and under-wing gaps.
Open bodywork can expose interior parts to the rays; this is geometric exterior
sampling, not semantic part classification. Features thinner than the sampling
spacing may be missed, and detached mirrors can be discarded. Voxelization and
smoothing can shift dimensions by roughly the sampling scale; source bounds
are not forcibly restored. Inspect the result before baking, and use original
geometry for fit measurements.

## 301: Six-view atlas

Activate the vehicle Mesh at the desired frame and run
`301_export_six_views.py` in Blender's Text Editor. The script
exports LEFT, FRONT, TOP, REAR, LEFT_FRONT and LEFT_REAR PNGs plus a three-row,
two-column SVG atlas into `SIX_VIEWS/<object name>/` beside the saved blend file
(Desktop for an unsaved file). Reruns overwrite the matching export files.
Only the active Mesh is rendered, including its evaluated modifiers.

The four orthographic images retain millimetre dimensions in the SVG;
perspective images are visual references without a measurement scale. The
canvas grows as needed. Z is height and the longer world X/Y extent is length.
Adjust `LEFT_SIGN` and `FRONT_SIGN` for the model orientation; the perspective
views follow these same settings. Sampling density, perspective focal length
and elevation are configurable at the top of the script. Render settings and
object render visibility are restored after export, including render failures.
