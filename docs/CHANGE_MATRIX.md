# Change Matrix — Skate 3 Native Recomp

**Last updated:** 2026-09-04 (session 3). Committed: `58f8618` (key binding). Uncommitted: none.
**Base:** upstream `f6e0ae8` / v2.0.2. HEAD = `58f8618`.
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

## NOT IMPLEMENTED — needs action

| Item | Feasibility | Next step |
|------|-------------|-----------|
| **Fix B3 (nude body preservation)** | FEASIBLE (research confirmed). `item.bones.size()/12` degenerate (always 84); real bone count at `mesh+0x48`. Per-entity grouping via `LookupCtx`. | One-frame `char_track` diagnostic dump to confirm body material, then implement per-entity max-real-bone prune in `BuildFrameScene`. |
| **Scratch/blood body damage** | **FEASIBLE** — Path A recommended (agent C confirmed). Add wound slot to `DrawItem`, relax `AdoptDrawFetchOverrides` gate for `char_family==2`, add `overlay.w==5` wound branch in `scene_char.hlsli`. Three code paths suppress wounds but all are addressable. | F11 `.draws.bin` capture in emulated mode to confirm Path A (mesh decal) vs Path B (standalone overlay). Once confirmed, implement wound slot + shader branch (~medium effort). |
| **Character-size shadow matching** | FEASIBLE. CSM shadow pass never applies the cvar (dead code removed). | Add bone-palette scaling to CSM shadow pass (same pattern as main pass). |
| **Physics editor — clamp override** | FEASIBLE. Gravity constants at `0x821ae344`/`0x821a6c84` known. | `StoreGuestF32` to those addresses to override clamp range (needs runtime test). |
| **Perf menu refinement** | IN PROGRESS. v2 Performance dashboard merged (consolidated all perf into one window, RHI graphs + fullscreen trace + scene stats + pacing). | Build was blocked at P0; once the tree compiles, verify visually. |
| **Physics editor (reverted)** | NOT in repo (reverted — `sub_82c67f10` is NOT a registered recomp entry, it's mid-function code in a fat aggregated body). | Find the actual recomp entry wrapping that code region, or hook a real entry; verify against `PPCFuncMappings[]`. |
| **Rigid-piece scale pivot divergence** | MAJOR (audit, NOT fixed). Non-skinned char_family 1/2 rigid pieces scale the full world transform (`constants[0..11] *= cs`) about the WORLD ORIGIN (`gpu.cpp:8983` main, `:6792` shadow) while skinned items scale bone translations about the ROOT BONE (`:6702`/`:9045`). Away from origin the pivots diverge by `(1-cs)*P` → hats/jewellery/rigid ropa drift off the scaled body. | Fix: scale rigid-piece translation row about item origin (world-space root) instead of the literal origin, mirroring the skinned path. Needs care — logged, not blindly changed. |
| **Dead blend-index range check** | MINOR (audit). `palette_bones = item.bones.size()/12` is always 84, so the "blend index exceeds palette" warning never fires (`gpu.cpp:1163`). | Use real bone count from `mesh+0x48` (same source needed for Fix B3). Ties into Fix B3. |
| **Constant-bank overread** | MINOR (audit). `kPaletteFloats = 84*12` reads 4092+ bytes from a 4096-byte bank; for `palette_base >= 5` the last 1–4 bone rows read past the boundary (`scene.cpp:4224`). Harmless (defensive reads, unreferenced by vertices) but non-deterministic. | Cap to `min(84, (256 - palette_base)/4) * 12`. Low-priority. |
| **Dead `submission` param** | NIT (audit). `EvictTexStore`/`EvictCubeStore` take a `submission` argument never used; callers still compute `CurrentSubmission()` (`gpu.cpp:8001/8003`). | Remove param + drop the `CurrentSubmission()` calls. Cosmetic. |
| **F3 shadow-bone reuse re-validation** | MINOR (audit). Shadow pass publishes only a ring offset (`:6721`) that the main pass reuses (`:9021`) without re-validating the `cs`/bones it was computed under. | Re-validate or include cs/bones in the publish. Logged. |

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
 src/skate3_native_scene_gpu.cpp        | 151 ++-     (drain fix + character-size + cast fix)
 src/skate3_native_scene_gpu_internal.h |  23 +      (OutputViewEntry for drain cache)
 src/skate3_native_scene_post.cpp       |  15 +-     (EnsureMenuBlurStandalone cache)
 src/skate3_native_scene_state.h        |   1 +      (#include <fstream> build fix)
 tests/check_deadcode.py                |  35 ++-     (false-positive elim + crash fix)
```
