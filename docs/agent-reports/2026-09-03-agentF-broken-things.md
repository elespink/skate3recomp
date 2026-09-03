# Agent F (2026-09-03) — Broken-things audit

Read-only investigation. Full report saved verbatim. To be reviewed and fixed FIRST (per user).

## Audit of "broken things" in the Skate 3 native renderer + F12 debug menu

I cross-checked every `REXCVAR_SET` in `src/skate3_native_debug_dialog.cpp` against its consumers across `src/`, plus scanned the scene GPU/post/build files for gated/inert reads and hot-path waste. **Every cvar exposed in the F12 menu has at least one real reader** — there are no entirely "dead knobs" (declared+SET but never read). The problems that exist are mis-gating, misleading metadata, and redundant hot-path work. Ranked below.

## Priority 1 — User-visible "I toggled this and nothing happened"

### 1. Sun azimuth/elevation sliders in "Lighting & post" are unanchored (inert by default)
- **File:** `src/skate3_native_debug_dialog.cpp:761-770`
- **Why broken:** These two sliders (`sun azimuth`, `sun elevation`) are drawn **unconditionally** at the bottom of the Lighting & post section. Their values only take effect when `skate3_native_render_scene_sun_override` is ON, which **defaults to false** (`skate3_native_scene.cpp:267`). The checkbox that would make them matter sits above (line 739), but the sliders are not gated on it, so a user dragging them sees no scene change unless they've already hunted down and enabled the override checkbox.
- **Confirms the "unanchored control" pattern:** the *Weather* section's copies of the same two sliders *are* correctly wrapped in `if (REXCVAR_GET(...sun_override))` (`skate3_native_debug_dialog.cpp:856-863`). The Lighting & post copies are the odd ones out.
- **One-line fix:** wrap lines 761-770 in `if (REXCVAR_GET(skate3_native_render_scene_sun_override)) { ... }`, or `BeginDisabled` when the override is off (the Weather section already shows the intended gating).

## Priority 2 — Misleading / misfiled metadata

### 2. `skate3_native_render_scene_refl_mode` range (0–6) contradicts the 10-option F12 combo and shader
- **File:** `src/skate3_native_scene.cpp:795-801` (REXCVAR_DEFINE `.range(0, 6)` and help text describing only modes 0–6) vs `src/skate3_native_debug_dialog.cpp:1116-1128` (combo offers modes 0–9, with tooltips at 1131-1138 describing modes 7/8/9).
- **Why misleading:** The define's `.range(0,6)` and its description omit the lightmap-visualization modes 7–9 (`7: visualize lightmap sample`, `8: visualize lightmap UV`, `9: lightmap resolve status`), which the F12 dialog offers and the shader genuinely handles (`src/native/shaders/scene.hlsl:362-370`). Since `REXCVAR_SET` is a direct assignment with **no range clamp** (`third_party/rexglue-sdk/include/rex/cvar.h:311`), modes 7–9 *do* work — but the define's metadata/help and the dialog are out of sync. Range metadata is also used by config parsing, so a hand-entered value of 7–9 in a config could be flagged/rejected inconsistently.
- **One-line fix:** extend the define's `.range(0, 9)` and add the three lightmap-debug modes to its help text, or trim the F12 combo back to 0–6.

## Priority 3 — Unnecessary / redundant operations on the hot render path

### 3. Skinned bone palettes are `memcpy`'d into the per-frame bone ring twice (shadow pass + main pass)
- **File:** `src/skate3_native_scene_gpu.cpp:6567-6572` (shadow-atlas caster upload) and `src/skate3_native_scene_gpu.cpp:8835-8841` (main scene pass).
- **Why wasteful:** `g_r.bone_ring_offset` is reset to 0 at the start of the frame (`skate3_native_scene_gpu.cpp:7700`, and the comment at 7695 explicitly says "the shadow pass allocates first, the main pass appends"). When a skinned item casts a dynamic shadow (shadows on by default), its identical `item.bones` buffer (the final interpolated palette, unchanged between the two passes) is `std::memcpy`'d into the ring twice per frame — once for the shadow-atlas caster copy, once for the main-pass copy — doubling the CPU copy and the per-region GPU footprint for those casters.
- **One-line fix:** cache the ring offset assigned in the shadow pass per item (e.g., `item.bone_offset`), reuse it in the main pass instead of re-copying; or skip the shadow-pass copy and let the main pass's upload serve both (the shadow pass can reference the main-pass offset).

### 4. Stretch-guard skin-sample veto runs on every skinned item every frame (default-on diagnostic)
- **File:** `src/skate3_native_scene.cpp:10382-10425`
- **Why wasteful:** `skate3_native_render_scene_stretch_guard` defaults **true** (`skate3_native_scene.cpp:1027`), and when on this loop iterates every skinned `scene.items` entry and calls `SkinnedSpreadHostRows` — a host-side skin of the cached sample verts against the full final bone palette — each frame, purely as an artifact-safety veto. It's a per-frame CPU cost on the build thread proportional to skinned-item count that exists only to catch a class of 1-frame corruption.
- **One-line fix:** keep the veto on by default only in debug/config builds, gate the default on non-release, or throttle it (e.g., only every Nth frame per item, matching the every-4th-frame rebuild cadence used elsewhere).

## Notes: suspected items that checked out (not bugs)

- `hdr_packed`, `bloom*`, `shafts*`, `haze*`, `ssao*`, `shadow_pcss*`, `shadow_static_strength`, `tex_mips`, `2d_sharp`, `world_v2` / `dynobj_v2`, `occlusion_cull`, `perf_log`, `perf_items`, `sort_opaque`, draw-distance cvars, freecam cvars, and the weather-preset writes all have live, correctly-gated readers. No dead knobs.
- The `deb` mode combos (`debug`, `hdr_debug`) match their define ranges exactly.
- `native_render_suppress_emulated_draws` (F12 header) is consumed by the SDK suppression path and does change behavior.
- The double `sun_brightness` scaling loop (`skate3_native_scene.cpp:8359-8370`) is short-circuited by `|br-1.0| > 1e-4` at 8338, so at the default 1.0 it costs nothing.
