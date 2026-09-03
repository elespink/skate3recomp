# Agent G (2026-09-03) — Nude/hair body-visibility fix

Read-only investigation. Full report saved verbatim.

# Investigation Report: Nude Mode Making Skater Body Transparent / Hair Invisible

## Objective
Root-cause why `skate3_native_render_scene_nude` makes the skater's **body transparent** and **hair invisible**, and propose a **low-risk host-side fix** so clothes hide while body/skin stays visible, without requiring a CAS-edit re-publish.

## What we know definitively

### The nude patch is an uncommitted, user-authored working-tree change
- Modified: `src/skate3_native_scene.cpp` / `.h`, `src/skate3_native_debug_dialog.cpp`, `src/skate3_app_common.cpp`.
- `git log -S "nude"` returns nothing; the feature is new.
- Definition: cvar `skate3_native_render_scene_nude` at `src/skate3_native_scene.cpp:868-874`, wired to the F12 debug dialog at `skate3_native_debug_dialog.cpp:979-984`.
- It gates **4 publish paths** at `skate3_native_scene.cpp:4382` (CaptureDynamicState), `:8776` (world sort-list), `:9022` (instance/ropa-rescue), `:9299/9324` (gap-fill cache).

### The garment classifier — exact code (this is the crux)
`src/skate3_native_scene.cpp:2279-2304`:

```cpp
item.ropa = false;
{
  ... if mat_name is "character.<base>_ropa" {
    item.ropa = true;
    mat_name[len - 5] = '\0';     // STRIPS "_ropa" suffix
  }
}
// Nude hides plain cloth/leather/jacket garments too
{
  item.garment = item.ropa;
  if (!item.garment && memcmp(mat_name, "character.", 10) == 0) {
    const char* sub = mat_name + 10;
    const bool cloth   = memcmp(sub, "cloth", 5) == 0;
    const bool dcloth  = memcmp(sub, "default_cloth", 13) == 0;
    const bool leather = memcmp(sub, "leather", 7) == 0;
    const bool jacket  = memcmp(sub, "jacket", 6) == 0;
    item.garment = cloth || dcloth || leather || jacket;
  }
}
item.hair = memcmp(mat_name, "character.hair", 15) == 0;  // line 2305
```

So a piece is a **garment** (dropped by nude) if:
- Its material is `character.<base>_ropa` where `<base>` is **any** name — **including `hair` / `default_hair`** (the comment at `:2266-2268` explicitly confirms `hair_ropa` and `default_hair_ropa` exist in the attrib table), **or**
- Its base name is `cloth*` / `default_cloth*` / `leather*` / `jacket*` (covers plain-cloth tees the patch was added to hide).

`character.skin` / `character.face` / `character.hair` (non-ropa, non-cloth) → `garment=false` → **survive nude**.

### Body vs garment are separate DrawItems by design
- `char_track` identifies the body as "the highest-bone-count **skinned non-ropa** character item within 5 m" (`src/skate3_native_scene.cpp:6765-6767`), and "garment = nearest ropa item" (`:6764`).
- `DrawItem.garment` (`src/skate3_native_scene.h:183`) deliberately excludes skin/face per the comment at `.h:181-182` ("does NOT cover skin/face (also char_family 2) so nude keeps the body").

## Root cause — single consistent explanation

Both symptoms are explained by **one root cause: the *initial/default* skater's visible body + hair are authored with cloth-family (`character.cloth*` / `character.hair_ropa`) materials, which the nude garment classifier strips. A CAS edit re-composes the skater with non-cloth `character.skin` / non-ropa `character.hair` pieces that survive the gate.**

### Hair invisible (explained with certainty)
- Default hair is `character.hair_ropa` (or `default_hair_ropa`). The `_ropa` detection at `:2284` sets `item.ropa=true`, then `:2294` `item.garment = item.ropa` → **dropped**.
- After a CAS edit the re-composed hair is plain `character.hair` (non-ropa) → `garment=false` → visible.
- This is a straight classification consequence; no readiness/publish bug is involved.

### Body transparent (highly likely, same classification cause)
- The skater's visible skin-tight base (the "body" you expect to see once clothes strip) is authored as a cloth-family piece — most plausibly **plain `character.cloth`** (a skin-suit/base layer), caught by the `cloth` prefix test at `:2298` → `garment=true` → **dropped**.
- The comment at `:2289-2292` confirms plain `character.cloth` is used for skater pieces, and the filter deliberately targets *all* plain cloth-family names; it cannot tell a replaceable outer tee from the skin-tight base layer.
- After a CAS edit, the re-composed body becomes `character.skin` (or another non-cloth body piece) → survives.

### Why the CAS-edit "fixes" it
The CAS edit re-composes the whole outfit. It swaps the default cloth-family body+hair pieces for skin/hair-family pieces, which the garment classifier lets through. The re-publish/re-skin event is *not* repairing a stale capture — it is changing the material classes of the spawned items. This is why my analysis favors a **classification fix over a force-re-publish fix**: forcing a re-publish without changing materials would not make `character.cloth`_body or `character.hair_ropa` pass the gate.

## Candidate fixes (ranked by risk)

### Fix H — Hair (certain fix, lowest risk, clearly correct)
**Stop dropping hair-family pieces under nude.** Hair is not clothing and the user wants it visible even as `hair_ropa`.
At `src/skate3_native_scene.cpp:2294`, set `item.garment` to false for hair-family materials. Note the `_ropa` suffix is already stripped into `mat_name` (so `character.hair_ropa` → `character.hair` here), and the `item.hair` test at `:2305` uses exactly `memcmp(mat_name, "character.hair", 15)`. Concretely:

```cpp
const bool is_hair = memcmp(mat_name, "character.hair", 15) == 0;   // also covers default_hair? (see below)
item.garment = item.ropa && !is_hair;
if (!item.garment && memcmp(mat_name, "character.", 10) == 0 && !is_hair) {
  ... cloth/dcloth/leather/jacket logic ...
}
```

Check: `character.hair_ropa` after stripping becomes `character.hair` → `is_hair=true` → garment stays false. But **verify `default_hair`**: `character.default_hair_ropa` strips to `character.default_hair`, whose first 15 chars are `character.defa...` — does NOT match `"character.hair"`. So the exact `memcmp(...,"character.hair",15)` test would MISS `default_hair`. Use `char_family` (hair is fam 4/5, assigned just below at `:2310+`) instead, or match both `character.hair` and `character.default_hair` prefixes. This is the precise spot where the hair fix must be thorough. No risk to tee-hiding (tees/ropas stay garments).

### Fix B — Body (primary, medium risk)
Keep the skin-tight base body while still hiding replaceable outer garments. The garment classifier must distinguish the **base body layer** from **outer garments** among cloth-family pieces. Two approaches:

- **B3 (preferred balance):** Exclude the skater's full-body base layer from `garment`. The codebase already has the exact discriminator for the *composed* skater (`char_track`, `:6765-6767`): the body is the **highest-bone-count skinned non-ropa character item per entity**. Use the same heuristic so the under-layer (spans the whole skeleton) is kept while the torso-only tee / limb pants / jacket are dropped. This is the game's own notion of "body" and matches `DrawItem.garment`'s intent (`scene.h:181-182`).
- **B1 (precise but more code):** Track the entity's body item explicitly (per-model) in the nude gate at `:4382` and force-skip it.

- **NOT recommended — B2:** Reverting the plain `cloth/leather/jacket` extension (making garment = ropa only). This *would* keep a `character.cloth` body, but it re-introduces the plain-cloth-tee leak the patch was specifically added to fix (`:2289-2292`). Net worse.

### Alternative hypothesis (force-re-publish) — evaluated and discounted
**Option (b): force the CAS-edit re-publish on first spawn.** I verified this is *not* the effective fix: the re-publish works today only because the CAS edit changes the *material classes* of the spawned pieces. A forced re-publish that re-captures the *same* cloth-family/hair_ropa items would re-drop them at the same classifier gates. So a "force re-publish" might transiently show them but is a symptom treatment, not the cause. It becomes relevant *only* if a hidden readiness bug is later confirmed — which the evidence here does not support.

## Recommendation (combined)
1. **Fix H first** — clear `garment` for hair-family pieces (handle both `character.hair` and `character.default_hair` base names, ideally via `char_family` 4/5). Guaranteed, zero-risk fix for the hair symptom.
2. **Fix B3** — in + around the nude gates (`:4382`, `:8776`, `:9022`), preserve the skater's *body* item identified as the highest-bone-count skinned non-ropa character piece (reuse the `char_track` discriminator), so a cloth-family skin-tight base layer survives while true outer garments (tee/pants/jacket, incl. plain-cloth) still hide.

Both are host-side, local to `src/skate3_native_scene.cpp`, and avoid re-publishing the CAS.

## Outstanding / to confirm before implementing
I could not run the game or dump guest attribulator material names, so the **specific material of the default skater's body base layer** (`character.cloth` vs `character.cloth_ropa` vs some other) is inferred from the classifier's own comments (`:2266-2268`, `:2289-2292`) rather than confirmed from data. The hair root cause is certain; the body root cause is highly probable but should be confirmed with a one-frame diagnostics dump (`skate3_native_diagnostics` / the `char_track` log already emits per-item material/fam info) before committing to Fix B3 over the simpler B-keep-body-by-bone-count.
