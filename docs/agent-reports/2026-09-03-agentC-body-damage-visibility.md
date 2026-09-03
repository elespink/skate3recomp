# Agent C (2026-09-03) — Broken bones / blood / scratches visibility

Read-only investigation. Full report saved verbatim.

# Investigation Report: Broken Bones, Blood & Scratches Not Rendering in Native Mode

## Ranking: P1 (high priority, user-visible break during an iconic gameplay moment)

When the skater takes a serious bail, the game applies persistent body-damage visuals (broken bones X-ray, blood, scratches/cuts on the limbs). These render only under **emulated** mode (F5 → native off). Under the **native** Vulkan renderer they are absent.

## Root cause (confirmed)

The native renderer is **architecturally incapable of drawing body-damage decals** — it has no capture path, no DrawItem channel, and no shader pass for them. They do not even reach the suppression stage; they never become native draw items, so nothing is emitted to the frame at all.

The chain of evidence:

### 1. Zero awareness of body-damage anywhere in the recomp
There are **no strings** matching `wound`, `blood`, `broken`, `scratch`, `bruise`, `injury`, or `body damage` in either `src/` (native renderer) or `generated/` (guest code). The native code is structurally blind to these effects by construction.

### 2. The native capture pipeline is material-channel-driven and has no wound channel
`CaptureSkinnedState` / `BuildItemGeometry` resolve a fixed set of material channels — diffuse, lightmap, macro (normal), decal_art, hair_alpha, spec, water_normal — but **no wound/decal-burnt-into-skin channel**:
- `src/skate3_native_scene.cpp:2676` (`BuildItemGeometry`) reads the guest mesh context's draw list and material channels.
- `src/skate3_native_scene.h:56` `diffuse_fetch[6]` and `decal_art` (line 135) are the only fetched-overlay slots, and both are for **environmental** artwork.
- `AdoptDrawFetchOverrides` (`src/skate3_native_scene.cpp:2489`) is gated on `item.env_family != 0` (line 2490) — **environment items only** (posters, event ads) and **never** applies to a skater's skinned skin mesh. So even the draw-fetch mechanism — the one "live texture override" the renderer has — is explicitly restricted to environment surfaces and cannot carry a wound texture onto the body.

### 3. Even if a wound pass were captured, the character shader has no overlay path
`src/native/shaders/scene_char.hlsli` (`ShadeCharacter`, line 6) shades albedo + spec + rim + a spec *mask* map sampled from `decal_art` (lines 74, 85, 170-171, 191) — but that `decal_art` slot in the skin family is the **spec-mask map** (`overlay.w == 3`, per comment at `scene_char.hlsli:156`), *not* a wound/albedo-replacement texture. There is no blending pass to composite an injury decal over the skin.

### 4. The guest's own wound passes are suppressed by the same frame it can't render
The guest game *does* draw the injury decals over the body via its normal per-frame D3D passes into the framebuffer-sized main-scene surface. But with native output active:
- `ShouldSuppressEmulatedDraws()` returns true at `third_party/rexglue-sdk/src/graphics/native_guest_renderer.cpp:153-156` (both `native_render_suppress_emulated_draws` default `true` and `g_native_output_active`).
- With the default `native_render_suppress_mode=2`, `ShouldSuppressPassAtPitch` (`native_guest_renderer.cpp:162-183`) **suppresses any emulated pass whose surface pitch is not `1024` or `<=512`** (`:181`) — which includes every framebuffer-sized main-scene pass where the body-damage decals are composited.
- The Vulkan command processor applies this at `third_party/rexglue-sdk/src/graphics/vulkan/command_processor.cpp:4269-4273`.

The net effect (double-confirmed): in native mode, the wound decals are (a) never captured as native items *and* (b) their emulated draws are suppressed. In emulated mode (F5), they execute and are visible. **Both halves of the mechanism must be handled to restore them natively.**

## Classification: which kind of draw carries body-damage (and why it's invisible)

All three hooked guest draw functions route through `OnDrawDone` (`src/skate3_native_scene.cpp:4546`), which only acts on a draw if it can **match a pre-staged pending DrawItem by `(ib,vb)`** via `g_frame_pending_by_buffers` (`:5600`). Unmatched draws simply `return` at `:5601-5603` and are never rendered natively (`OnDrawDone` was shown dropping unmatched draws). Because body-damage overlays arrive as either:
- a **second effect pass over the same skin mesh** with a wound texture bound at draw-time (which the fixed material-channel capture never records a texture for), or
- a **separate overlay/quad pass** (particle-style blood spatter, e.g. the `CaptureClothDraw` quad path at `src/skate3_native_scene.cpp:4406`, gated off by default via `skate3_native_render_scene_quadlists` = false at `:396` and `:4411`),

…they are never captured, never rendered, and their emulated source is suppressed. The renderer has no mechanism at all for a "live-drawn mesh with a transient wound texture."

## Feasibility & recommended path (prioritized)

The surgical, lowest-risk fix is to **add a native decal-on-character channel** using machinery that already exists:

1. **Capture the wound texture at draw-time and route it through the existing `diffuse_fetch`/`decal_fetch` override, but relax the `env_family != 0` gate** (`src/skate3_native_scene.cpp:2490`) so a skinned character draw whose draw-time fetch binds a wound texture can adopt it. This reuses the entire existing "adopt live fetch state" path (`AdoptDrawFetchOverrides`, `:2489`) and the `DrawItem::diffuse_fetch[6]` field (`skate3_native_scene.h:56`).
   - Feasibility: **Medium.** Requires distinguishing a wound rebind from the normal skin spec-mask binding, and verifying the wound texture stays resident (the `guest_read_recovery` scope in `OnDrawDone:4568` already guards reads).
   - Must be verified against a real `.draws.bin` F11 record to identify the wound pass's exact fetch-slot/PS and texture object.

2. **Add a wound/overlay blending sub-pass to `scene_char.hlsli`** keyed off the captured wound texture (a translucent alpha blend over the skin albedo — analogous to how `decal` env composites work). Feasibility: **Low-Medium**; the char shader already has an unused alpha slot (`out_a = ch_misc.x`) available for a body-damage mask.

3. **Alternatively (quickest interim), allow the injury passes to execute emulated over the native frame.** Because the wound decals are model-aligned and use the same camera/depth as the native scene, carving the specific wound passes out of the suppression filter (pitch-based, `command_processor.cpp:4269`) would composite them on top. Feasibility: **High** but hacky — depends on the native frame fully replacing/overlaying the guest surfaces, and risks depth/compositing artifacts.

4. **Verify with tooling first:** use the F11 draw-record system (`src/native/skate3_native_diagnostics.cpp`, format at `:130-138`) during a forced bail in *emulated* mode to capture the wound pass's `(ib,vb)`, PS object hash, and fetch-slot texture. This single record disambiguates whether the wound is a second pass on the skin mesh versus a separate quad/overlay, which determines whether path 1 vs 3 is correct.

The definitive blocker is *diagnosis-first*: the fix cannot be fully specified until we confirm from a recorded F11 `.draws.bin` whether body-damage is (a) a re-bound fetch on the existing skinned mesh or (b) a standalone overlay/quad pass. That record is the next required step.
