# Agent E (2026-09-03) — Scope: Character-mod exaggeration (size/obesity)

Read-only investigation. Full report saved verbatim.

## Summary of investigation state

Here is the complete read-only scoping report for the character SIZE / OBESITY morph feature.

### What I confirmed (with file:line)

**Feature precedence — nude mode is the model to follow.** A host-only feature that drops guest content at scene-build time, driven by a cvar exposed in the F12 dialog:
- `skate3_native_scene.cpp:4380` — `if (item.garment && REXCVAR_GET(skate3_native_render_scene_nude)) return 0;` (drops garment items)
- `skate3_native_scene.cpp:866, 879-885` — cvar declarations (pattern for new morph cvars)
- `src/skate3_native_debug_dialog.cpp` — the F12 ImgUI menu where a "Characters" section + sliders would go

**The exact injection points for a host-side whole-body scale / exaggeration**, all confirmed:

1. **World-matrix scale (cleanest whole-body path)** — the skater's rigid/world matrix is applied at two GPU constant-build sites:
   - `skate3_native_scene_gpu.cpp:6876` — `std::memcpy(constants, item.world, ...)` (world-shadow atlas pass)
   - `skate3_native_scene_gpu.cpp:8808` — `std::memcpy(constants, item.world, ...)` (main pass, then MVP at 8821-8830)
   - `item.world[16]` is the per-item row-vector matrix (translation in row 3, `world[12..14]`), defined at `skate3_native_scene.h:303`.
   - Scaling the linear 3x3 (rows 0-2) about the feet (recompose translation row) multiplies body size uniformly. This is purely host-side, needs no CAS genes, works for every skinned skater/NPC.

2. **Per-bone / region scale (for HEAD, BELLY, TORSO, LIMB exaggeration)** — the bone palette is the right layer, because the shader already skinning via it:
   - Shader: `scene.hlsl:78-82` (StructuredBuffer `bones` = 3 float4 rows per bone, affine `[R|t]`, column-vector); skinning at `scene.hlsl:101-127` (guest bones index rows `3k..3k+2`).
   - Palette captured once per item at `skate3_native_scene.cpp:4145` (`item.bones.resize(kPaletteFloats)`, rows sanitized at 4148).
   - Palette interpolated per-entity in `InterpolateDynamicItems` (`skate3_native_scene.cpp:6704`; final write `item.bones = latest.b` at 7170, boxcar accumulate `std::copy(acc, acc, item.bones.begin())` at 7578).
   - Palette uploaded to GPU at `skate3_native_scene_gpu.cpp:8837` (main pass) and `:6571` (shadow-caster pass) — both `memcpy(item.bones.data(), ...)`.
   - A per-bone scale keyed by bone index (e.g. "head bones" vs "spine/wasit" vs "limb") would multiply the affine rows at whichever of these layers is desired. The `DynPose.b` ring (pose/palette history, `skate3_native_scene.cpp:6717`) is the natural per-entity home for a per-bone region scale that must survive interpolation.

**Critical constraint (relevant to the request's caution):**
- The CAS editor yields native rendering entirely: `skate3_native_scene_gpu.cpp:5920-5952` (`YieldForCasEditor`). The in-editor character uses non-modeled CAC shader variants and the FE path. So a morph that must LIVE-PREVIEW inside the CAS editor is **not** reachable via the native render path. The honest recommendation: implement the morph as a render-time transform applied OUTSIDE the editor (free-skate, replays, gameplay), i.e. host-side, not a guest CAS-gene RE.
- Guest CAS gene discovery remains blocked: generated code is disassembly without descriptive symbols (grep for cas/morph/gene/slider/nutrition returned only auto-generated headers, e.g. `skate3_functions.toml`). There is no named CAS gene structure to hook. Effort for guest-gene RE is high and uncertain; host-side transform avoids it entirely.

**DrawItem struct fully confirmed** (`skate3_native_scene.h:23-307`): it has `world[16]` (line 303) and `std::vector<float> bones` (line 298), plus `skinned` (96), `char_family` (116), `garment` (183), `ropa` (176), `lw_entity` (37 — **per-entity identity, already used to key pose rings so clones never mispair**), and `lw_alpha` (36). Crucially: **no existing per-character/per-bone scale field exists** — any morph feature must add one (a new cvar-driven value applied at the injection points above, or a new field on the ring/DrawItem). `lw_entity` already gives us clean per-skater identity to key an "apply to player only" gate if desired.

### Feasibility verdict

- **Recommended: host-side render transform, whole-body + region scale**, applied at the two world-matrix sites (uniform body size / character scale) and optionally at the bone-palette serve/upload for head/belly/limb regional exaggeration. Precedent (nude mode) proves host-only works.
- **Not recommended as scope: guest CAS gene RE.** Blocked on disassembly, and the CAS editor yields native rendering so live in-editor preview isn't reachable through the native renderer.
- **CAUTION repeated:** the feature will not show inside the CAS editor via this path; it applies to the rendered skater in gameplay/replay/free-skate.

### Effort estimate (honest, for the recommended host-side path)

- **Small (size/whole-body scale only):** ~0.5-1 day. Add 1 cvar + F12 slider, apply a uniform scale to `item.world` 3x3 at `skate3_native_scene_gpu.cpp:8808` (and 6876 for shadows). No new struct fields.
- **Medium (regional exaggeration: head/belly/torso):** ~2-4 days. Requires: (a) a region→bone-index mapping (reverse-engineer which guest bone numbers map to head/spine/waist from the captured palette structure — `item.bones` rows are the raw guest bone order, so bone indices are discoverable at runtime), (b) a per-item scale vector threaded through `InterpolateDynamicItems`/ring so the pose history and interpolation stay consistent, (c) applying the per-bone multiply before the GPU uploads at 6571/8837. The wheel-centroid code (`DynHist::cen`, lines 6735-6745) is a precedent for per-bone geometry analysis available here.
- **Large/unbounded: true CAS-gene morph** (guest genotype read + run through the game's own skeleton/morph evaluation) — blocked, do not scope.

The cleanest first deliverable that matches the request's "sliders for character SIZE" is the **whole-body world-matrix scale** (uniform + per-axis stretchable to a "taller/wider" look), implemented exactly like nude mode: cvar + F12 slider driving a transform at the two world-matrix application sites, keyed to `lw_entity` / `char_family` so it only touches characters. Regional obesity/head exaggeration builds on the same foundation via the bone palette.
