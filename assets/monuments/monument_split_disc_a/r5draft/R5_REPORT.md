# monument_split_disc_a — R5 repair report

## Starting-state audit

The interrupted run had a compilable, substantially rewritten `build.py`, but its validation and renders were partially stale:

- the first socket implementation (12 separate blocks) had already been superseded in code by 4 continuous socket lips, but the then-current `scene_report.json`, texture extracts and draft render still described the obsolete intermediate state;
- the final patched build had not yet been inspected or rendered;
- the large analysis files (`polygon_spatial.json`, raw/extracted textures, mesh `.npz` dumps) were still present.

This continuation rebuilt the asset from the raw local GLB, inspected the resulting blend, iterated the socket lips and material/fracture settings, rendered final diagnostics, and removed the large temporary files.

## Implemented repairs

All changes are deterministic and credit-free in `../build.py`; no Meshy API/credits were used.

1. **Split/fracture geometry**
   - topology-preserving displacement of 30,709 fracture-region vertices;
   - layered, hash-indexed breakage bands plus low-frequency coarse relief;
   - mean absolute lateral displacement 0.115 m, maximum 0.52 m;
   - asymmetry keeps protrusion into the empty split smaller than recession, preserving the open air wedge;
   - transition width and band scale were sharpened to reduce the previous broad, planar/crumpled look.

2. **Socket / anchorage**
   - 4 closed continuous stone lip meshes (`socket_lip_0/1_front/back`) replace the earlier 12-block interpretation;
   - tapered/chamfered prisms intersect the plinth and monolith, with raised inner cheeks and broader bearing width;
   - UVs are projected into a calm region of the existing stone atlas;
   - objects remain separate intersecting support/anchor geometry rather than boolean-fused topology.

3. **Albedo crackle and black pores**
   - low-pass separation with asymmetric retention of negative/positive high-frequency luminance;
   - chroma residual reduced to 4.5%;
   - two black-top-hat/inpainting passes suppress circular dark pores;
   - replacement grain uses three granular noise octaves and coarse spatial modulation, rather than worm-like linear crackle.

4. **Warm split stripe**
   - geometrically rasterized UV mask, not a rectangular UV box;
   - broader normal-independent mask now covers 70,975 rasterized triangles / about 17.28% of UV-mask samples;
   - saturation reduction 0.68, red cooling 0.018, blue compensation 0.006.

5. **Normal texture**
   - tangent-space normal vectors low-passed (`keep=0.10`, `xy_compress=0.72`);
   - Blender normal-map strength reduced to 0.16.

6. **QA scale marker**
   - figure moved away from the plinth to `(7.0, 12.2, 0.0)`;
   - diagnostic copies are annotated as `QA scale 1.8 m (not asset)`.

## Validation measurements

- `py_compile`: OK for final `build.py` (27,221 bytes)
- final build log: `r5draft/build_r5.log`
- objects: 5 (main mesh + 4 socket lips)
- triangles: 219,726 total (main 218,926 + 4 × 200 socket lips)
- dimensions: 30.952 × 19.209 × 40.375 m
- bounds: x −15.476..15.476 m, y −9.605..9.605 m, z −1.500..38.875 m
- boundary edges: 0 total; every object individually 0
- non-manifold edges: 0 total; every object individually 0
- split openness estimate from vertices near the centre: minimum positive air gap about 1.03–2.53 m across tested z bands 10–35 m (1.498 m at z10–15, 1.395 m at z15–20, 1.028 m at z20–25, 2.138 m at z25–30, 2.532 m at z30–35)

Texture comparison, raw Meshy albedo vs final R5 albedo (consistent 8-bit offline measurement):

- high-frequency luminance std, radius 3: 0.032288 → 0.003707 (−88.5%)
- high-frequency luminance std, radius 7: 0.040000 → 0.007356 (−81.6%)
- dark-pit fraction `support−luminance > .02`: 23.07% → 0.91% (−96.1%)
- dark-pit fraction `support−luminance > .035`: 15.32% → 0.038% (−99.75%)
- Blender build metric additionally reported 48,875 pore-candidate texels treated by the two correction passes

Final hashes:

- `build.py` sha256 `70269de8c005e8acd389bea3142750c81c4d9fee14181b62da57e3e20425bb75`
- `monument_split_disc_a.blend` sha256 `4ac58c695fa7ee58746a0e65839f7a270c4508072dbaf5e5db73cae80d448f1d`

## Diagnostic renders

All are 16 samples and live outside formal `review/` outputs:

- `render/sheet_r5.jpg` — full 12-tile sheet
- `render/sheet_r5_annotated.jpg` — same sheet with QA scale figure annotation
- `render/hero_r5.jpg`
- `render/hero_r5_annotated.jpg`
- `render/closeup_r5.jpg` — upper split closeup
- `render/closeup_base_r5.jpg` — socket/contact closeup
- `render/draft_r5.jpg` — fast 3-tile diagnostic sheet
- `render/sheet_r5.json` — renderer metadata

Render stats: Blender 5.2.2 LTS, 16 samples, 107.2 s, 12 tiles.

## Files intentionally kept in `r5draft`

Small validation/rollback/documentation files only (about 1.5 MB including renders):

- `R5_REPORT.md`
- `build_v4_backup.py`
- `patch_build_r5.py` (historical patch record)
- `inspect_blend.py`
- `extract_textures.py`
- `render_r5.py`
- `annotate_scale.py`
- `build_r5.log`
- `render_r5.log`
- `scene_report.json`
- `render/` diagnostic files listed above

Removed temporary bulk data: `polygon_spatial.json`, extracted texture PNGs, raw GLB texture dumps, mesh `.npz` dumps, UV/analysis crops, iteration contact sheets, stale `.blend1`, and generated `__pycache__` (about 140.6 MB total).

## Residual risks / honest limitations

- The socket lips are separate closed intersecting meshes, not boolean-fused with the monument. This preserves clean topology and export independence, but very close inspection may reveal intersections.
- The support is visually much more explicit than v4, yet the exact central tangent line cannot be fully eliminated without remodeling the plinth/disc contact or boolean-cutting a true curved groove. The raised side cheeks/wedges now provide the visible anchoring cue.
- The fracture relief is much less planar, but its broad facets remain stylized and may still read as smooth/crumpled in the most extreme closeup.
- Strong micro-crackle suppression intentionally favors calm monumental stone. Fine grain remains, but the surface is smoother than the raw Meshy texture; if a reviewer expects rougher sandstone, grain amplitude can be raised slightly.
- Warm stripe pixels are strongly neutralized, though a thin warm edge can still appear in direct sun because part of the effect is geometric illumination rather than albedo.
- Scene QA figure is diagnostic only and annotated in the annotated copies; it is not part of the monument mesh/material.

## Non-mutations

No export was run. No Meshy requests/credits were used. No git commit was made. `asset.json` content is unchanged in git diff. Formal `review/sheet.jpg`, `review/hero.jpg`, `review/closeup.jpg`, and `review/sheet.json` were not overwritten by this continuation; R5 outputs are only under `r5draft/render/`.
