# Agent A (2026-09-03) — Scope: F12 Physics menu (gravity/velocity/etc)

Read-only investigation. Full report saved verbatim.

## Investigation Report: Feasibility of a "Physics" F12 Debug Menu Section

I read the F12 debug dialog (`skate3_native_debug_dialog.cpp`, 1455 lines), the render/scene/entity hook layers, the draw-distance host-rewrite engine, the ultrawide guest-memory patcher, the FOV override, and the ReXGlue hook mechanism. Here are the findings.

### 1. Existing guest physics symbols

**NONE exist.** This is the crux, and the prior agent's assessment was correct.

- Searched all of `generated/skate3_recomp.*.cpp` and generated/ overall for `gravity`, `Physics`, `PhysicsObject`, `velocity`, `Velocity`, `max_speed`, `MaxVel`, `jump` (physics sense), `fall` (physics sense). Zero named matches.
- The generated code is 100% anonymous goto-blocks of form `DEFINE_REX_FUNC(sub_823E12C0) { REX_FUNC_PROLOGUE(); ... }` — pure PPC recompilations with **no C++ names, no symbol table, no class roles** attached. There is no `Sk8::PhysicsObject::...` anything.
- All physical-content comments in `src/` are incidental: "the physics drop" (spawn settle alpha ramp, `skate3_native_scene.cpp:858`/`:3746`), "physics-animated props (dumpsters)" (`:4278`), "a physics prop's one-tick rotation" (`:6899`). These are render-side observations of moving objects, **not** physics-system entry points.

**No ReXGlue REX_FUNC hooks are physics-related.** All 70+ `REX_FUNC(sub_...)` hooks in `src/` target **render/D3D** systems (draw lists, palette packing, 2D phases, swap, movie decode, photo grab, stream culling). None target the simulation/physics tick. The one per-tick-adjacent hook that exists is `Sk8::Challenge::PhotoReplayController::Update` (`skate3_native_render.cpp:638`, `sub_825623F0`) — but that's a photo-editor UI heartbeat, not a physics tick.

**Verdict:** There are **zero confident** guest physics addresses/EAs. Any candidate would be pure speculative discovery work: you'd have to find `sub_XXXXXXXX` bodies that multiply a stored float by a frame-time constant, or locate a global gravity/velocity float in guest memory by value-capture at runtime (see section 4). None are currently identified in the repo.

### 2. Already-exposed physics-ish cvars/fields

- **There is no Physics section in the F12 menu.** Confirmed: `OnDraw()` in `skate3_native_debug_dialog.cpp:1340-1416` wires exactly these CollapsingHeaders: Showcase & capture, Image quality, Lighting & post, Weather, Shadows, World shading, Scene content & overlays, Smoothness & pacing, Diagnostics, Caches. **No physics, gravity, velocity, or speed section.**
- The only "speed"/"velocity" cvars that exist are **camera/drone**, not gameplay physics:
  - `skate3_native_render_scene_freecam_speed` (`skate3_native_scene.cpp:366`, dialog `:431`)
  - `skate3_native_render_scene_freecam_look_speed` (`:371`, dialog `:437`)
  - `skate3_draw_distance_scale` / `skate3_lod_distance_scale` / `skate3_draw_distance_stream_probe` (`skate3_draw_distance.cpp:59/66/72`) — **render culling/streaming only**.
  - `skate3_guest_fps_cap` (`skate3_native_render.cpp:38`) — **frame pacing**, not game-world time.
- `skate3_fov.cpp` is a projection FOV override applied to the host-computed projection (`Skate3MaybeOverrideProjectionFovRadians`, `:65`) — a camera projection change, not a physics/gameplay modifier, and it does **not** touch guest memory.

**Type (A) items that would be "trivial to add a slider" are essentially none.** There is no existing cvar/field the renderer already touches that constitutes powertrain/physics. The only already-controllable gameplay-adjacent scalar is the **guest frame-time / fps cap** (a time-scale of sorts), already in the "Smoothness & pacing" section.

### 3. Recomputation hook points (host-writes-to-guest-field pattern)

The **pattern is proven and is the single strongest precedent** — but crucially it is the *render/cull/camera* systems that get host-overridden, never the physics engine:

- **Draw distance (best template)** — `skate3_draw_distance.cpp`:
  - `sub_8288DC58` (`:297`) + `RecordCullThreshold`/`EnsureCullThresholdScaled` (`:193`/`:158`): reads a guest float at `[cullObject+6064]`, rescales it to `1/k²`, and writes it back with `StoreGuestF32` (`:119`). This is literally "host overrides a guest float field each config-apply."
  - `sub_827E1AD8` (`:723`): **per-frame** hook — after the guest writes its six LOD distances it re-reads and rescales them in place (`StoreGuestF32`, `:735`). This is the clean per-frame re-write model any gravity/velocity slider would copy.
  - `sub_82792900` (`:311`): per-frame optimesh reference-vector rewrite (also carries the freecam GPS recenter via `StoreGuestF32`, `:332`).
- **Freecam guest camera rewrite (proven guest-write)** — `skate3_native_scene.cpp:10607` `REX_FUNC(sub_82802A00)`: intercepts the game's `ViewCamera::SetViewMatrix`, memcpy's a host-computed 4x4 into guest memory (`base + mtx + i*4`), then calls through. This and the cull/LOD hooks above are the canonical "host overrides guest field each frame" proofs.
- **Wide-guest frustum** — `skate3_ultrawide_guest.h:30-91`: a RAII scope reads guest cull-plane floats and rewrites them (`StoreFloat`→`REX_STORE_U32`, `:120-124`) every cull call.
- Guest reads are guarded by `GuestTryCopy` (`src/native/skate3_native_guest_read.cpp:55/100`) + `GuestReadRecoveryScope` (`:197`); gameplay gating uses `rex::kernel::guest_presence::GameplayContextValue()` (`skate3_native_scene.cpp:6436`, `skate3_draw_distance.cpp:521`).
- **`OnRopaDoubleBuffer`** (`skate3_native_render.cpp:503`) is a per-cloth-sim-tick heartbeat but only used for freshness/identity — it proves a per-tick hook exists (cloth sim), not that it touches physics state.

**What this means for a "gravity multiplier / time-scale" without discovery:** You can *only* apply such an override if you already know the guest address of the gravity/velocity storage. The infrastructure (per-frame `REX_FUNC` hooks + `StoreGuestF32`/`REX_STORE_U32` into guest memory + gameplay-context gating) is **fully available and battle-tested**. The missing piece is entirely the **address discovery** — you need to find where the physics engine keeps its gravity/speed/velocity floats before you can use the proven rewrite pattern on them. There is no existing hook that hands you that value.

### 4. New relevant helper scripts

- `tests/check_deadcode.py` — static dead-code/reference triage tool. Not a memory/address discovery helper; completely unrelated to locating physics floats.
- `tools/symbolize_crash.py` — runs `addr2line -f -C` on crash backtraces; maps guest `sub_XXXXXXXX` addresses to C++ symbols in the non-stripped build. **Not** a runtime value-capture tool.
- **No runtime memory-scan / value-capture / float-locator helper exists** anywhere in `tests/`, `tools/`, `src/`, or the ReXGlue SDK. There is no "scan memory for a float value" utility, no guest RAM dump+search tool, no AOB-finder. The only guest-memory *capture* facilities (`skate3_native_diagnostics.cpp` F9/F10 gsnap, `OnCaptureFrameEnd` `:616`) dump draw/geometry buffers for render debugging — they do **not** search for physics constants.
- The F12/render diagnostic "records" (camera `:1205`, bone `:1218`) capture **poses/camera**, not physics state.
- ReXGlue SDK has a guest address→host resolver (`ppc/context.h` `ResolveIndirectFunction`, `:41`) and the hook macro `REX_FUNC(x)` = `void x(PPCContext&, uint8_t* base)` (`:51`) — these are building blocks for *writing* a discovery helper, but none exists yet.

**So a runtime value-capture discovery helper would itself have to be built** (e.g. a new REX_FUNC on a per-tick hook that scrapes candidate memory ranges for a float, or dumping guest RAM to disk for offline AOB search). This is significant new infrastructure, not something to reuse.

## (a) Concrete feasible scope for a "Physics" F12 section

**Implementable now (Type A — truly trivial):**
1. **Guest time-scale / frame pacing** — already fully controllable via `skate3_guest_fps_cap`; already exposed in "Smoothness & pacing." Adding it under a Physics section would be cosmetic duplication, not new capability.
2. **Nothing else.** There is no currently-known physics field the renderer touches. Every other gravity/velocity/max-speed/jump/fall editor is Type (B) and requires address discovery first.

**Requires discovery first (Type B — hard):**
- **Gravity multiplier** slider — needs the guest gravity float address.
- **Velocity override** / horizontal speed / max-speed — needs the velocity or max-speed storage.
- **Jump height / fall rate** — needs sim constants.
- **"Live physics editor"** generally — prior agent correctly flagged as NOT started. Confirmed: there is no scaffolding for it.

For a **time-scale without a gravity address**, the cleanest zero-discovery approach is *not* a guest-memory write but a **host clock manipulation** — but the codebase has no such global time source hook either; all per-frame host time is consumed render-side. Even a "slow-motion" would need either (a) the fps-cap/pacing path (already there, affects rendering not sim), or (b) locating the guest sim delta-time. Neither is a drop-in.

## (b) file:line reference map

| Item | Location |
|---|---|
| F12 menu sections wiring (where a Physics CollapsingHeader would go) | `src/skate3_native_debug_dialog.cpp:1376-1407` |
| F12 menu builder / helpers (CvarCheckbox/Slider/ValueCombo) | `:131`, `:142`, `:158` |
| Menu section pattern example (add new `DrawPhysicsSection`) | `:1052` (DrawPacingSection) — closest analog |
| REXCVAR_DECLARE block (add physics cvars here) | `:26-126` |
| REXCVAR_DEFINE examples (double/bool) | `skate3_native_scene.cpp:366-377` |
| Per-frame guest-float rewrite template | `skate3_draw_distance.cpp:723-739` (sub_827E1AD8) + `StoreGuestF32 :119` |
| Config-apply guest rewrites | `skate3_draw_distance.cpp:297, 158-191` |
| Host-writes-guest-matrix template | `skate3_native_scene.cpp:10607-10628` (sub_82802A00) |
| Host-writes-guest-plane template | `skate3_ultrawide_guest.h:30,84,120-124` |
| Guest read guard + recovery | `src/native/skate3_native_guest_read.cpp:55,100,197`; `GuestTryCopy` usages `src/skate3_native_scene.cpp:1834+` |
| Gameplay-context gate (only apply in gameplay) | `skate3_draw_distance.cpp:521`, `skate3_native_scene.cpp:6436` |
| REX hook macro / resolver | `third_party/rexglue-sdk/include/rex/ppc/context.h:51,41` |
| Only "speed" cvars (freecam, not physics) | `skate3_native_scene.cpp:366,371` |
| Frame-pacing (only existing gameplay scalar) | `skate3_native_render.cpp:38` |
| No physics discovery helper exists | tests/ and tools/ contain only `check_deadcode.py`, `symbolize_crash.py` |

## (c) Honest effort estimates

- **Gravity slider / velocity override / jump / max-speed / live physics editor:** **Not implementable without discovery.** Effort: **high (multiple days to weeks)**. Requires (1) building a runtime float-value discovery tool or manual disassembly of generated `sub_*` functions to find the gravity/velocity storage, (2) validating the address (find a per-tick or per-frame sim hook to hang the write on), (3) adding the `REXCVAR` + `DrawPhysicsSection` + the `StoreGuestF32` per-frame rewrite. The rewrite/hook *mechanics* are proven and cheap (~a day); the **discovery is the dominant unknown and risk**, and there is currently **no tooling for it**.
- **Guest time-scale / slow-motion:** **Low-medium (~half a day to a day)** *if* you accept the existing fps-cap/pacing approach and call it "time scale" — but it will not actually slow the *simulation*, only guest frame pacing. True sim slow-motion is Type (B).

**Bottom line:** A "Physics" F12 **section scaffold** (cvars + collapsed header + sliders) can be added in well under a day, but every *real* physics control it hosts is gated behind guest address discovery that does not yet exist — the prior agent's "NOT started / needs discovery" flag is fully confirmed.
