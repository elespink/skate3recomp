# Agent H (2026-09-03) — Optimization round #2 + full function-list coverage

Read-only investigation. Full report saved verbatim.

# Investigation Report: Optimization / dead-code round #2 + full guest function-list coverage

## Goal 1: New per-frame host-side inefficiencies

I focused on the hot paths the prior work had already narrowed (`skate3_native_scene_gpu.cpp`, `skate3_native_scene.cpp`, `skate3_native_render.cpp`, `skate3_fov.cpp`, `skate3_draw_distance.cpp`). F3 and F4 remain the dominant flagged items; the genuinely new observations beyond those are below. I did **not** re-report any of the items you cleared, and separated these from F3/F4.

### NEW-1 — Duplicate per-frame skin-consistency validation (second, unconditional site)
- **Where:** `src/skate3_native_scene.cpp:8853-8860` (the publish-time `PublishedPaletteSane` coherence gate), distinct from the draw-time stretch veto (F4, line 10384).
- **What:** For every skinned item in the scene, EVERY frame during gameplay, this runs `PublishedPaletteSane` (line 3895), which does a 32-sample **guarded guest-VB read** (`ReadSkinSamplesGuest` → 32× `REX_LOAD_U32/U16`) plus a full `SkinnedSpreadHostRows` over the item's bones. It is gated only by the default-on `skate3_native_render_scene_dynamic_items` (defined line 865, `true`), so it is unconditional in normal play.
- **Redundancy:** The draw-time stretch veto (F4) then runs a nearly identical `SkinnedSpreadHostRows` over the **same** items' bones a second time each frame. That is two passes of essentially the same skin-consistency computation on the same data, and the publish gate is the one that also pays a 32-sample guest-memory read per skinned item per frame.
- **Risk:** Medium-Low. The two gates serve slightly different timing roles (publish heals/re-publishes the rescue caches before they are refreshed; the draw-time veto is the final blink catch after all merges). But the raw `SkinnedSpreadHostRows` computation is duplicated, and it is a separate call site not covered by the F4 flag. Worth judging whether the draw-time pass can be made to cover the publish gate's job, or the publish gate can skip items the draw veto already validated.

### NEW-2 — `water_time` recomputes the clock twice (minor)
- **Where:** `src/skate3_native_scene_gpu.cpp:8187-8192`.
- **What:** The per-frame water scroll time calls `std::chrono::steady_clock::now()` twice — once for the value and once inside the `floor(...)` term — so it does a redundant clock read each frame and the two terms can disagree by a tick. Compute `now() - water_t0` into one `double` and derive both the value and the `%3600` wrap from it.
- **Risk:** Very Low (micro). Real but tiny; only applies when the water branch executes per frame.

Everything else I traced in the hot paths is either (a) amortized (the tex/mesh/cube LRU `ages.reserve` scans park for 120 frames when idle), (b) budgeted/periodic (the `recheck_frame + 16` texture/mesh revalidation cadence), (c) gated by off-by-default debug/trace cvars, or (d) essential correctness gates (palette-base refinement, capture acceptance) — none of which are new findings, and most of which your cleared list already covers. The per-frame work is dominated by F3 (shadow+main double bone-palette memcpy into the ring) and F4 (stretch_guard), both already flagged.

## Goal 2: Does a complete function/symbol list of the Xbox 360 game exist?

**No.** The repo contains **no complete, named, full function/symbol list**. Evidence:
- No `.map` files anywhere (`find / -name '*.map'` → none).
- The generated code is 100% anonymous PPC goto-blocks (`DEFINE_REX_FUNC(sub_XXXXXXXX) { ... }`) — no C++ names, no class roles, no symbol table (confirmed in code and by `docs/agent-reports/2026-09-03-agentA-physics-menu.md:14`).

**Artifacts that DO exist (address-level / partial):**

| Artifact | Count/Scope | Format |
|---|---|---|
| `generated/skate3_init.cpp` (`skate3_PPCFuncMappings[]`) | 48,175 rows | address → `sub_XXXXXXXX` |
| `generated/skate3_register.cpp` (`skate3_RegisterFunctions`) | 48,175 `SetFunction` | address → fn ptr |
| `generated/skate3_init.h` (`DECLARE_REX_FUNC`) | 47,652 distinct | decls |
| `generated/skate3_recomp.*.cpp` (111 files) | 47,652 distinct | anonymous `DEFINE_REX_FUNC` bodies |
| `config/skate3_functions.toml` | ~1,776 lines | address → `{end, parent}` boundary overrides |
| `config/skate3_tu_functions.toml` | ~1,741 lines | TU overrides + setjmp/longjmp addrs |
| `config/eawebkit_functions.toml` | ~145 lines | EAWebkit (`0x88xxxxxx`) overrides |
| `generated/eawebkit/` (34 files) | 19,971 registered | separate EAWebkit set |

**Coverage gaps:**
- The TOML `[functions]` tables only list **boundary overrides** (address → end/parent), not named symbols; they are anonymous.
- `REX_CODE_BASE 0x82380000`, `REX_CODE_SIZE 0xC1E16C`; `REX_IMAGE_BASE 0x82000000`, `REX_THUNK_RESERVE_SIZE 0x10000`. Some `sub_` entries are glue/thunks (e.g. `__restgprlr_19`), so 48K rows ≠ 48K real game functions; the true function count is `47,652` distinct native bodies + `19,971` EAWebkit.

**Native hook surface:** 57 `REX_FUNC(sub_...)` hooks in `src/` plus a handful of named REX_FUNC hooks (`Skate3DemoPath_*`, `SKATE3_EXCEPTION_GUARD_*`, `__restgprlr_19`). **All target render/D3D/menu/exception glue — none are physics/sim/CAS/gene.** Confirmed by the agent reports (no physics symbols, no CAS gene structures).

**NT-kernel vs game layering:** There is **no NT-kernel code** in the repo. Nothing references xboxkrnl/ntoskrnl/XexGet. The recomp covers only the game's own `0x82xxxxxx` image plus EAWebkit `0x88xxxxxx` — not the Xbox 360 kernel. So a "full list" here can only ever cover game + EAWebkit, never NT kernel.

**Recommendation:** To obtain a genuinely complete/named function list, disassemble the retail `skate3.xex` (plus the title-update XEX) from the user's DVD/ISO and load it into Ghidra (or recover the PDB/symbols if available), then reconcile the resulting .text symbol table against the 47,652 anonymous `sub_` addresses already enumerated here. No repo artifact provides 100% named game-function coverage.
