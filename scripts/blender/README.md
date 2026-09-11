# Blender Modules

| Module | Responsibility | Current status |
| --- | --- | --- |
| `config_driven/project_config.py` | Load and validate project JSON | Blender-independent |
| `config_driven/seam_naming.py` | Parse `S001_PANEL[_A\|_B]` names | Blender-independent |
| `config_driven/repair_boundary.py` | Endpoint weld, small-gap bridge, boundary validation | Migrated existing implementation |
| `config_driven/generate_cloth_mesh.py` | Uniform sampling and constrained Delaunay mesh | Migrated existing implementation |
| `config_driven/generate_sewing.py` | Select seam paths and create Sewing Springs | Semantic ID pairing, A/B direction and legacy fallback integrated |
| `generate_sewing.py` | Build Sewing directly from a semantic SVG | Creates PANEL/SEAM/HEM and automatic A/B vertex groups, then arc-length-matched loose edges without project imports |
| `config_driven/setup_cloth.py` | Apply Oxford cloth settings | Config-driven SmoothDrape V2 preset |
| `setup_cloth.py` | Apply the self-contained HemFeedback 75F V28 preset | Late per-vertex animated soft pin springs, object/self collision, and seam material |
| `config_driven/setup_mirror_markers.py` | Add left/right mirror-position comparison marks | Config-driven, non-physical face-material marks based on TESLA-MODELX.ai artboard 1 |
| `setup_mirror_markers.py` | Add the same mirror-position marks without project dependencies | Opens an interactive `MARKER_CONFIG` dialog before applying non-physical marks at the settled frame |
| `config_driven/generate_collision_proxy.py` | Generate a smooth vehicle Collision Proxy | Reads `config/simulation.json`; delegates geometry work to the matching self-contained implementation |
| `generate_collision_proxy.py` | Generate the same Collision Proxy without project dependencies | Embedded FastCollisionShell V5 settings; original evaluated topology, zero-or-one rear-wing support, optional voxel remesh, 18k-triangle collision budget, source-bounds correction, and Collision physics |
| `generate_collision_shell.py` | Test a two-stage collision-shell workflow | Creates a 35 mm inspection Outer Shell, extracts a 50 mm/6k-triangle Collision only from that shell, restores source bounds, and runs lightweight geometry/silhouette checks |
| `setup_cloth_fit_test.py` | Apply a lightweight Cloth preset | Quick car-cover fit test with embedded settings |
| `svg_cloth_workflow.py` | Import a semantic SVG and run the complete cloth pipeline | One file dialog; joins PANEL curves, remeshes, generates Sewing, and applies the embedded cloth preset |
| `export_three_views.py` | Real-size three-view SVG/PNG export | Auxiliary reporting tool |
| `export_six_views.py` | Four orthographic views and two perspective views | Six PNGs and an embedded SVG atlas; self-contained |

## Six-view atlas

Activate the vehicle Mesh at the desired frame and run
`export_six_views.py` in Blender's Text Editor. The script
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

The default Collision Proxy preserves the evaluated source topology and overall
X/Y/Z bounds. Whole-vehicle voxel remeshing and smoothing are disabled. When
the merged source exceeds the 24,000-triangle hard budget, Collapse targets
18,000 triangles and a 3-degree planar dissolve removes redundant coplanar
facets. Candidate scoring can select either one rear wing or none. Only that
single component receives a downward support volume, closing the gap where a
falling cover could become pinched by a thin trailing edge.
Because that support deliberately changes local clearance below the wing, use
the original vehicle rather than the collision proxy for local Fit measurements.
If a deliberately tapered drape-support shell is needed, enable
`lower_body_inset` and save it as a separate proxy; do not use that altered
shell for Fit metrics.

## Self-contained selection order

`generate_collision_proxy.py` leaves the generated proxy selected so
it can be inspected. Before running `setup_cloth.py`, select the
actual car-cover mesh; selecting the proxy as well is harmless because the cloth
script recognizes and skips meshes with Collision physics. Collider activation
no longer depends on `CC_COLLISION_PROXY` or any other collection name. Every
Mesh with a Collision modifier in the current scene participates, while objects
that belong only to another scene do not. This makes switching scenes sufficient
to switch vehicle colliders; collection names are free to describe each model.
If an older run already added Cloth to the proxy, remove that Cloth modifier.
Free the old Cloth bake before running V28. Setup samples a free trajectory;
then replay frames 1-75 to evaluate the late HEM spring guidance.

## Two-stage collision shell test

Use `generate_collision_shell.py` when a detailed vehicle consists
of many panels, wheels, glass and interior islands. Select only the original
vehicle meshes and run the script in Object Mode. It creates two objects in
与活动目标物体同名的集合（未激活有效源物体时使用首个有效源物体名）：
所选车体源对象也会链接到该集合；原有集合链接会保留。
高模源对象、Outer Shell 和低模代理都会配置 Collision。两个 voxel shell
在恢复源车体边界前执行向内半体素补偿，低模整体尺寸仍与源车体一致；碰撞体
外侧厚度仅保留 1 mm，以免代理局部外鼓或额外撑大车衣。

- `* Outer Shell TEST` is the retained fine shell for visual inspection only.
- `* Shell Collision TEST` is the selected, lightweight-checked Collision object to use
  with Cloth.

Stage one performs a 35 mm voxel union, removes every detached surface except
the main vehicle shell, smooths it, and restores the source AABB. It then probes
the upper silhouette against the evaluated source using a lightweight 128-ray
grid. In the default fast mode, excessive roof/hood loss produces a warning and
keeps the shell for manual correction. Set `ENABLE_THIN_SURFACE_REPAIR=True`
only when an automatic 250 mm Solidify rebuild is worth the potentially large
voxel cost. Stage two voxelizes the accepted shell again at 50 mm, removes
residual islands, smooths it, decimates it to 6,000 triangles, restores bounds,
and enables double-sided Collision with 1 mm thickness and friction 3. Both
stages reject empty or non-finite geometry, and the final stage enforces the
triangle budget and exact source bounds. Silhouette loss remains advisory while
`ENFORCE_TOP_SURFACE_ACCURACY=False`.

For high-detail vehicles, evaluated temporary copies are proportionally
pre-decimated to 180,000 triangles before they are joined and voxelized. The
stage-one voxel result is further capped at 30,000 triangles before smoothing.
Neither stage runs the expensive full BMesh topology/volume audit. Accuracy is
instead guarded by voxel remeshing, largest-component cleanup, source-bounds
restoration, finite-coordinate checks, and a final BVH upper-silhouette probe.
The original vehicle meshes are not modified. The generator prints progress
before each blocking stage and rejects an estimated stage-one voxel grid above
eight million cells, which usually indicates incorrect model units or distant
stray geometry. Adjust `PRE_VOXEL_MAX_TRIANGLES`,
`MAX_ESTIMATED_VOXEL_CELLS`, or the voxel sizes at the top of
`generate_collision_shell.py` when a deliberate exception is required.

In the `Lab.blend` Tesla test, the final shell was a single watertight component
with zero boundary/non-manifold edges and exact source dimensions. A frame
1-50 V25 Cloth bake completed without any tested cloth vertex inside the shell.

## Sewing and final seam closure

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

Both `generate_sewing.py` and the V28 setup preflight reject a vertex connected
to more than two loose sewing edges. Such a many-to-one hub is a topology error
that creates the tail "black-hole" effect; increasing Sewing force would make
it worse rather than correct it.

Planned modules from `doc/AGENT.md` that do not yet have production implementations are intentionally not represented by empty Python files. Add them with tests as the pipeline grows: `import_pattern`, `validate_pattern`, `parse_seams`, `arrange_panels`, `setup_pin`, `run_simulation`, `analyze_fit`, and `export_report`.

## Mirror-position comparison marks

Artboard 1 of `illustrator/TESLA-MODELX.ai` places the mirror-pocket center
1600 mm behind the front-bottom endpoint and 1020 mm above it. The left-side
charge-port center is 340 mm from the rear-bottom endpoint and 820 mm above it.
At the settled comparison frame, activate the Cloth mesh and run
`config_driven/setup_mirror_markers.py`. The evaluated `PANEL_LEFT` and `PANEL_RIGHT` vertex
groups provide separate side-panel coordinate references, so `PANEL_TOP` and
vehicle Collision bounds cannot shift the marks. The script paints
small left/right mirror marks orange-red and the left charge-port mark blue. It does not create a mirror-pocket
mesh or affect Cloth, Collision, mass, sewing, or Fit geometry. If the vehicle
front axis differs from the Model X scene's default -Y, change
`mirror_markers.front_axis` in `config/simulation.json`.

## Script organization

Scripts in `scripts/blender/` use embedded settings and run without project JSON.
`config_driven/` contains JSON-driven workflows and their helper modules.
Run configuration-driven scripts from their saved project paths. Their JSON
files remain in the repository's `config/` directory. Collision-proxy and
mirror-marker wrappers reuse the implementations in the parent directory.

## One-click SVG cloth workflow

Open `svg_cloth_workflow.py` in Blender's Text Editor and click **Run Script**.
Choose the semantic `_sewing.svg` file in the file dialog. The operator imports
and joins only the curves inside the SVG `PANEL` group, creates the cloth mesh
with `remesh.py`, generates semantic sewing from the same source file, and then
applies `setup_cloth.py`. Existing vehicle Collision objects remain in the scene
and are discovered by the cloth setup as usual. This is a single-file standalone
script: it can also be pasted into an unsaved Blender Text block and does not
need access to the repository or neighboring Python files. After changing one
of its three source scripts, run `build_svg_cloth_workflow_standalone.py` once
to refresh the embedded implementations.
