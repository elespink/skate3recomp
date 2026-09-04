# Change Matrix — Skate 3 Native Recomp

**Last updated:** 2026-09-04 (session 3). Committed: `ff389a4`. Uncommitted: none.
**Base:** upstream `f6e0ae8` / v2.0.2. HEAD = `ff389a4`.
**Note:** I do NOT build in the VM — the build tree is host-keyed to `lespink`. Build fixes are log-only; user verifies by compiling on the host (clang++-21).

---

## IMPLEMENTED (uncommitted, user building)

| # | Feature | Files | Risk | Status |
|---|---------|-------|------|--------|
| 1 | **Drain fix — output SRV cache** | `scene_gpu.cpp`, `_gpu_internal.h`, `_scene_post.cpp` | Low | Reuses VkImageView across 3-image mailbox rotation instead of recreate every frame. Root cause of recurring 4-5ms drain stalls. |
| 2 | **Character-size bone-palette fix** | `scene_gpu.cpp` | Medium | Scales bone-palette translation around character root instead of world matrix. Fixes mesh flying off + camera/perspective breakage. Removed dead world-shadow code. |
| 3 | **Deadcode tool fix** | `tests/check_deadcode.py` | None | Eliminated ~200 false-positive "unreferenced" entries from intra-TU static calls and function pointers. |
| 4 | **Perf menu refactor (v2)** | `debug_dialog.cpp` | Low | MangoHUD-style consolidated "Performance" dashboard: big colored FPS, frame-time graph w/ 1%/0.1% lows, GPU resource bars, RHI drain/view graphs, fullscreen view trace, scene stats, pacing controls. Moved RHI diag out of Diagnostics, fps-cap out of Pacing. Sun/haze dedup verified clean. |

## REVERTED (do not re-add as-is)

| Feature | Why reverted | Next step |
|---------|--------------|-----------|
| **Physics editor** (`skate3_physics_editor.cpp`) | `sub_82c67f10` is NOT a registered recomp function entry — the address is mid-function code inside a larger aggregated body. `REX_FUNC` can only hook registered function entries. The GHIDRA `.pdata` boundary (Function_82C57F10) is real, but rexglue merges it into a fat function. | Find the ACTUAL recomp entry wrapping this code, or hook a different address. Verify against `PPCFuncMappings[]`. |
| **Perf menu overhaul (v1)** | Was accidentally bundled with the physics editor in the reverted `debug_dialog.cpp`. | Being re-implemented cleanly by the perf/debug sub-agent. |

## PREVIOUSLY COMMITTED (since upstream f6e0ae8)

| Commit | Description |
|--------|-------------|
| `6c66d6c` | Cross-platform drone/freecam input for Linux |
| `5e7c5b8` | Crash-log, nude mode (Fix H hair), night brightness, F12 controls, AZERTY fly F7, F11 2D toggle |
| `ebb73dd` | Character-size slider, crash-log user-primary, stretch_guard default OFF |
| `765cd70` | Static cvar-consistency + deadcode test suite |
| `c798e58` | Park-char adaptive smoothing, palette memo, tex-retire + dialog/sun cleanups |
| `00ed5ff` | Dedupe sun/haze sliders, park-char kRing 24→32, F3 bone-ring reuse |
| `21aec37` | Reuse texture+SRV on staged content swaps (PrewarmCommit churn fix) |
| `f7cf9d5` | Change matrix + milestone verification docs |
| `d20d0cc` | Live F12 RHI diagnostics — drain/view-churn perf ring, fullscreen view trace, resource ledger |
| `e81ad7a` | Docs: change matrix through d20d0cc |
| `479af5f` | feat: drain/output-SRV cache, character-size root-pivot scaling, F12 perf v2, build + deadcode fixes |
| `58f8618` | fix: move 2D toggle to Ctrl+F10, freeing F11 for draw capture |
| `ff389a4` | fix: constant-bank overread cap, dead submission param, F3 shadow-bone cs validation |

## NOT IMPLEMENTED — needs action

| Item | Feasibility | Next step |
|------|-------------|-----------|
| **Fix B3 (nude body preservation)** | FEASIBLE (research confirmed). `item.bones.size()/12` degenerate (always 84); real bone count at `mesh+0x48`. Per-entity grouping via `LookupCtx`. | One-frame `char_track` diagnostic dump to confirm body material, then implement per-entity max-real-bone prune in `BuildFrameScene`. |
| **Scratch/blood body damage** | **FEASIBLE** — Path A recommended (agent C confirmed). Add wound slot to `DrawItem`, relax `AdoptDrawFetchOverrides` gate for `char_family==2`, add `overlay.w==5` wound branch in `scene_char.hlsli`. Three code paths suppress wounds but all are addressable. | F11 `.draws.bin` capture in emulated mode to confirm Path A (mesh decal) vs Path B (standalone overlay). Once confirmed, implement wound slot + shader branch (~medium effort). |
| **Rigid-piece scale pivot divergence** | MAJOR (investigated). Rigid pieces (hats/jewellery/rigid ropa) have `constants[0..11] *= cs` which scales rotation/scale but NOT translation (`constants[12],[13],[14]`). Skinned items DO scale translations about root bone. Net: accessories stay fixed in world space while body scales → visible drift. Fix needs root-bone position for rigid pieces (not currently in `DrawItem`). | Read `docs/agent-reports/investigate-rigid-pivot.md` for full analysis + pseudo-code. Options: (a) look up sibling skinned item's root bone, (b) add `root_pos[3]` to `DrawItem`. Needs careful transform-math review. |
| **Physics editor** | BLOCKED. `sub_82c67f10` is NOT a registered recomp function entry (mid-function code in fat aggregated body). | Find actual recomp entry via `PPCFuncMappings[]` or hook a different address. Research needed. |

## TEST SUITE STATUS

| Check | Status | Notes |
|-------|--------|-------|
| `check_cvars.py` | PASS | Cvar visibility/duplication/undefined — clean |
| `check_deadcode.py` | PASS | FIXED crash: `.count()` on a `set` tokenizer (deduped) at line 170. Added `token_counts_in()` occurrence counter. Now clean EXIT=0. |
| `run_tests.sh` | BROKEN | Bash syntax error when invoked via `python3`. Run with `bash tests/run_tests.sh` or run Python scripts directly. |

## FILES CHANGED (all committed)

```
 src/skate3_app_common.cpp              |   1 +-     (Ctrl+F10 key binding)
 src/skate3_native_debug_dialog.cpp     | 396 ++-     (perf v2 + build-fix cast)
 src/skate3_native_scene.cpp            |   3 +-     (bank overread cap)
 src/skate3_native_scene_gpu.cpp        | 170 ++-     (drain fix + char-size + dead param + F3 cs)
 src/skate3_native_scene_gpu_internal.h |  23 +      (OutputViewEntry for drain cache)
 src/skate3_native_scene_post.cpp       |  15 +-     (EnsureMenuBlurStandalone cache)
 src/skate3_native_scene_state.h        |   1 +      (#include <fstream> build fix)
 tests/check_deadcode.py                |  35 ++-     (false-positive elim + crash fix)
```
