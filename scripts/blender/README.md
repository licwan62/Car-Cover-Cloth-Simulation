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
| `100_marks.py` | Mirror-pocket (half ellipse + position label), charge-port, door-line and plate-opening marks | One `MARKS_CONFIG` dialog; each mark can be switched off |
| `101_reflective_strips.py` | Front and rear reflective-strip rectangles on PANEL_LEFT / PANEL_RIGHT | One `REFLECTIVE_CONFIG` dialog; each strip has its own settings and color; height measured from the local HEM |
| `200_collision_exterior.py` | Exterior-only drape collider | Six-direction first-hit envelope, gap closing, cavity/island removal, closed-manifold validation |
| `300_export_three_views.py` | Real-size three-view SVG/PNG export | Auxiliary reporting tool |
| `301_export_six_views.py` | Four orthographic and four perspective views | Eight PNGs and an embedded SVG atlas |
| `config_driven/000_repair_boundary.py` | Endpoint weld, small-gap bridge, boundary validation | Reads `boundary_repair` |
| `config_driven/001_remesh.py` | Same meshing stage as `001_remesh.py` | Reads `cloth_mesh` |
| `config_driven/002_sew_from_groups.py` | Create Sewing Springs from existing seam vertex groups | Semantic ID pairing, A/B direction, legacy pairs from `sewing` |
| `config_driven/003_cloth_setup.py` | Apply Oxford cloth settings | `config/cloth/oxford_210d.json` (SmoothDrape V2) |
| `config_driven/100_mirror_marks.py` | Mirror and charge-port marks of `100_marks.py` | Reads `mirror_markers`; no dialog |
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
  `project_config.load_blender_script("100_marks.py")`, which loads a
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

## 100: Comparison marks

`100_marks.py` sets every mark from one dialog (mirror pocket, charge port,
door line, plate openings) on every selected Cloth mesh; a switched-off mark
is removed. The mirror pocket
is a half ellipse, 430 mm along its straight bottom edge and 300 mm high, with
a `<cloth> Mirror Label L/R` Text object below it recording its position and size.

Artboard 1 of `illustrator/TESLA-MODELX.ai` places the center of the
rectangle enclosing the mirror-pocket half ellipse 1600 mm behind the front-bottom endpoint and 1020 mm
above it. The left-side
charge-port center is 340 mm from the rear-bottom endpoint and 820 mm above it.
At the settled comparison frame, activate the Cloth mesh and run
`config_driven/100_mirror_marks.py`. The evaluated `PANEL_LEFT` and
`PANEL_RIGHT` vertex groups provide separate side-panel coordinate references,
so `PANEL_TOP` and vehicle Collision bounds cannot shift the marks. The script
paints small left/right mirror marks orange-red and the left charge-port mark
blue; door and plate marks are left as they are. It does not create a mirror-pocket mesh or affect Cloth, Collision, mass,
sewing, or Fit geometry. If the vehicle front axis differs from the Model X
scene's default -Y, change `mirror_markers.front_axis` in
`config/simulation.json`.

## 101: Reflective strips

`101_reflective_strips.py` draws up to two reflective-strip rectangles on every
selected Cloth mesh: a front strip positioned from the front end of the side
panel and a rear strip positioned from the rear end. Each can be switched on
or off and has its own settings: `PANEL_LEFT`, `PANEL_RIGHT` or both;
orientation (HORIZONTAL: long side along the car; VERTICAL: upright); the
center's distance from its panel end; the center's height above the hem;
length and width (250 x 50 mm by default); and color (orange by default). The
hem height is the mean settled Z of that panel's `HEM` / `HEM_*` vertices next
to the strip, so a sloping hem moves the strip with it; a panel without HEM
vertices uses its lowest point. The strips are the overlay mark kinds
`reflective_front` and `reflective_rear`, so they survive reruns of
`100_marks.py` and `003_cloth_setup.py` (and the reverse); the single
`reflective` mark of the first version is removed on the next run. Settings
are stored in `cc_reflective_config`, positioning records in
`cc_reflective_marker_front_*` / `cc_reflective_marker_rear_*`. A strip that
leaves the panel's length, drops below the hem or reaches the panel top is
rejected, and the cloth is left unchanged.

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

## 301: Eight-view atlas

In Object Mode, activate the cloth Mesh to highlight at the desired frame and run
`301_export_six_views.py` in Blender's Text Editor. The script
exports LEFT, FRONT, TOP, REAR, LEFT_FRONT, LEFT_REAR, RIGHT_FRONT and RIGHT_REAR
PNGs plus a four-row, two-column SVG atlas named `<object>_EIGHT_VIEWS.svg`
into `EIGHT_VIEWS/<object name>/` beside the saved blend file
(Desktop for an unsaved file). Reruns overwrite the matching export files.
The active Mesh (including evaluated modifiers) defines the dimensions and
framing. Export uses the largest ordinary 3D Viewport in the same window, or
the current viewport when run from one. Keep that viewport open beside the
Text Editor; leave editor maximization and Quad View before running. Blender's
GUI and a working GPU context are required; `--background` is not supported.

All objects visible in that viewport's view layer/local view are exported,
including separate Text labels and markers, even if disabled for final
renders. Hide unrelated objects in the viewport before running. The active
Mesh must be visible there. Orthographic framing includes `ORTHO_MARGIN_MM`
(100 mm per edge by default) without changing the millimetre scale, so the
outline is not clipped at the image boundary. Framing remains based on the
active Mesh; increase the margin or reposition labels extending beyond it.

LEFT and TOP shading follows the reference preset: Solid, Studio lighting,
Texture color, theme background, green object outlines, specular highlights,
X-Ray enabled at 0.600, backface culling and shadows disabled. The viewport's
specific studio light and lighting parameters are retained. Cavity is set to
Screen but Blender disables this effect while X-Ray is active. PNG backgrounds
are opaque to preserve X-Ray's appearance against the theme background.
`VIEWPORT_XRAY_ALPHA` and `VIEWPORT_OUTLINE_COLOR` configure the preset.
FRONT, REAR and all four perspective images use Wireframe shading: only the active
cloth Mesh is selected, so its edges use the Blender theme's active selection
color (orange in the default theme). Other visible meshes remain unselected
wireframes. The wireframe preset matches the reference: theme wire colors,
theme background, object outlines disabled, and wireframe X-Ray disabled.
Unselected mesh wires retain the original theme color, while the cloth
retains its theme selection highlight. Theme wire colors are not modified.
The LEFT/TOP solid X-Ray remains 0.600; perspective camera angles are retained.
Selection overlays are enabled for these six images, while grids,
axes, cursor, text information, object extras and relationship lines are
hidden. Original selection and active object are restored after success or
failure. Only LEFT and TOP retain the textured X-Ray appearance and green
outlines. LEFT_FRONT and LEFT_REAR look down from +20 degrees; the final row's
RIGHT_FRONT and RIGHT_REAR look up from -20 degrees on the opposite side,
showing the underside. `PERSPECTIVE_ELEVATION_DEG` sets the angle magnitude.
`KEEP_VIEWPORT_OVERLAYS = False` suppresses LEFT/TOP grid, selection highlights and
other overlays, while real Mesh/Text markers remain visible; enable it to
retain the viewport's overlays instead.

The four orthographic images retain millimetre dimensions in the SVG;
perspective images are visual references without a measurement scale. The
canvas grows as needed. Z is height and the longer world X/Y extent is length.
Adjust `LEFT_SIGN` and `FRONT_SIGN` for the model orientation; the perspective
views follow these same settings. Sampling density, perspective focal length
and elevation are configurable at the top of the script. Sampling defaults
to 0.5 px/mm (four times the previous width and height, sixteen times the pixel
count); a 5000 mm wide image is 2500 px wide. `VIEWPORT_AA = '32'` requests
32-sample anti-aliasing for viewport and viewport-render paths. These quality
settings apply to all eight PNGs and the PNGs embedded in the SVG; the SVG's
physical dimensions and measurement scale remain unchanged. Higher quality
increases export time and memory use. Viewport shading,
camera, view orientation, overlays and render settings are restored after
export, including render failures. Anti-aliasing preferences are temporarily
changed in memory and restored without saving user preferences. Object
visibility is left untouched.

The disposable GUI integration check is
`blender --factory-startup --python tests/blender/check_six_views.py`.
It creates a synthetic scene, exports eight PNGs and the SVG atlas, verifies
viewport-only objects and state restoration on success/failure, then quits
its Blender instance. Run this command in a separate instance, not from a
working scene. Its console prints the temporary output folder and PASS or
the failure traceback. With `--background` it checks only the context guard.
