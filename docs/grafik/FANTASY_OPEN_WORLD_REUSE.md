# Wiederverwendung aus „Fantasy open world" für Violet Reach

Stand: 23.11.2026 · Ergänzung für die aktive Bau-Session auf Zweig `grafik/next-level` (nach `GRAFIK_PLAN.md` und `docs/grafik/STATE.md`).

> **Hinweis für die Bau-Session:** Dieses Dokument ist eine additive Planungsgrundlage. Bestehende Pläne (`PLAN.md`, `GRAFIK_PLAN.md`, `docs/grafik/STATE.md`) und `queue.json` bleiben bis zur Übernahme durch die laufende Session unverändert. Alle aus `C:\Users\Mark Waldeis\Desktop\Fantasy open world` übernommenen Binärdateien liegen streng außerhalb des Repos im Staging-Ordner.

---

## 1. Ablageort & Integrationsprinzip

Alle vorausgewählten Dateien aus `C:\Users\Mark Waldeis\Desktop\Fantasy open world` wurden (nur als Kopie) bereitgestellt unter:

`C:\Users\Mark Waldeis\Desktop\Violet Reach Meshy\fantasy_open_world_import\`

Inhalt des Staging-Ordners:

- `manifest.json` — Inventar mit Dateigrößen und SHA-256-Prüfsummen für alle 7 Dateien in `trees_raw/` sowie `blender_reference/tripo_trees.blend`.
- `trees_raw/` (7 GLBs) — Tripo-Rohmodelle für Laub- und Uferbäume sowie Busch/Farn (`tree_meadow_oak.glb`, `tree_meadow_beech.glb`, `tree_meadow_ancient.glb`, `tree_meadow_willow.glb`, `tree_meadow_birch.glb`, `bush_meadow_lush.glb`, `bush_lush_fern.glb`).
- `leaf_textures/` (48 PNGs, je `1024 × 1024`) — Albedo (RGBA), Normal und ORM für Rinde und Laub/Wedel der Meadow-Bäume und -Büsche (`V3_img_bark_*`, `V3_img_foliage_*`).
- `blender_reference/` (6 Dateien) — `tripo_trees.blend` (fertige Template-Sammlung `V3_TRIPO_TEMPLATES`), `build_tripo_trees.py`, `generate_leaf_atlases.py`, `tripo_trees_manifest.json` sowie die Prüfblätter `tripo_trees_sheet.png` und `tripo_trees_meadow_closeup.png`.
- `shader_reference/` (9 Dateien) — Godot-Referenzshader und -Skripte als Portierungsvorlage für Three.js WebGPU/TSL (`foliage_leaves.gdshader`, `foliage.gdshader`, `grass_blade.gdshader`, `grass_system.gd`, `water.gdshader`, `river_water.gdshader`, `ocean.gdshader`, `waterfall.gdshader`, `water_fx.gd`).

**Verbindliche Regeln beim Einbau in Violet Reach:**
1. **Keine Rohdateien ins Git-Repo einchecken** (`GRAFIK_PLAN.md` Regel 6). Referenzierung in `build.py` erfolgt deterministisch über `VR_MESHY_DIR` (`fantasy_open_world_import\...`) mit SHA-256-Abgleich gegen `manifest.json`.
2. **Kein Vorbeischmuggeln am Qualitäts-Tor:** Jedes übernommene/abgeleitete 3D-Asset durchläuft weiterhin `build.py` → `tools/vr.py` Prüfblatt & unabhängige Bewertung (`>= 8/10`) → KTX2-Kompression & Meshopt-Export.

---

## 2. Bäume, Büsche & Farne (Phase 3 & Phase 4 — Direkter Asset- & Pipeline-Gewinn)

### 2.1 Was direkt übernommen werden kann

In `blender_reference/tripo_trees.blend` (Kollektion `V3_TRIPO_TEMPLATES`, exakt beschrieben in `tripo_trees_manifest.json`) liegen fertig ausgearbeitete botanische Bäume mit echtem Tripo-Holzstamm (inkl. Wurzelanlauf und unterirdischem Eingrabe-Sockel `z_min = -0.65 m` bzw. `-0.35 m` bei Büschen) und separatem Foliage-Slot aus **gebogenen, gekreuzten 3D-Blattkarten mit geglätteten Kronen-Normalen**:

| Template in `tripo_trees.blend` / `trees_raw/` | Maße (B × T × H) | Dreiecke (Rinde + Laub) | Nutzen in Violet Reach |
|---|---:|---:|---|
| `V3_TPL_tree_meadow_oak` | 10,9 × 12,2 × 11,1 m | 3.820 (1.948 + 1.872) | Großer Laubbaum (Ersatz/Basis für Phase 4 Laubbäume) |
| `V3_TPL_tree_meadow_beech` | 11,3 × 11,9 × 10,9 m | 2.700 (828 + 1.872) | Zweiter Laubbaum-Typ / schlankere Silhouette |
| `V3_TPL_tree_meadow_ancient` | 12,5 × 12,8 × 11,1 m | 5.290 (3.418 + 1.872) | Knorriger alter Laubbaum → **spart `trunk_broadleaf_d` komplett** |
| `V3_TPL_tree_meadow_small` *(Variante aus Beech)* | 6,5 × 6,7 × 6,7 m | 2.484 (828 + 1.656) | Jungbaum / Übergang zur Waldkante |
| `V3_TPL_tree_meadow_willow` | 9,2 × 9,2 × 8,3 m | 2.596 (1.348 + 1.248) | Uferweide mit hängenden Zweigen (See- und Flussufer) |
| `V3_TPL_tree_meadow_birch` | 9,3 × 9,5 × 9,9 m | 3.036 (1.628 + 1.408) | Optionale Variante (nur falls Birke zum Biom passt) |
| `V3_TPL_bush_meadow_lush` | 3,3 × 3,1 × 1,9 m | 1.688 (920 + 768) | Dichter Unterwuchs-Strauch (Ersatz/Upgrade für `shrub_round_a`) |
| `V3_TPL_bush_lush_fern` | 2,0 × 1,8 × 0,5 m | 448 (136 + 312) | Bodennaher Farn (Ersatz/Upgrade für `fern_cluster_a`) |

**Polycount- und Speicher-Vorteil:** Statt 6–11 MB pro Alt-Baum und >30k Tris beim Rohstamm liegen die fertigen botanischen Vorlagen bei **2.500–5.300 Dreiecken** (inkl. Laubkarten) und verwenden bereits saubere 2-Slot-Materialien (`bark` + `foliage`).

### 2.2 Meshy-Budget-Ersparnis (Phase 3)

- **Einsparbar:** `trunk_broadleaf_d` aus `queue.json` (und zusätzliche Laubbaum-/Strauch-Variationen) muss nicht über Meshy `image-to-3d` bezahlt werden — `tree_meadow_ancient` / `oak` / `beech` liefern bereits fertige knorrige Stämme. (Hinweis: In `Violet Reach Meshy\trunk_broadleaf_d\` liegt bisher nur das Referenzbild, noch kein bezahltes 3D-Modell.)
- **Weiterhin über Meshy bauen:** `trunk_acacia_b` und `trunk_baobab_a` (ergänzend zum bereits fertigen Pilot-Stamm `trunk_acacia_a`). Grund: Schirmakazien mit flachem Kronendach und Flaschenstämme prägen laut `GRAFIK_PLAN.md` Abschnitt 4 (Bodenfahrt-Referenz) maßgeblich die Silhouette von Violet Reach und fehlen in *Fantasy open world*. (`snag_dead_a`, `log_fallen_a`, `stump_roots_a` je nach Rest-Budget oder teilweise aus `build_tripo_trees.py`-Technik.)

### 2.3 Kronen- & Foliage-Pipeline übernehmen (Phase 4.3)

`blender_reference/build_tripo_trees.py` und `blender_reference/generate_leaf_atlases.py` lösen genau das Problem aus `GRAFIK_PLAN.md` 9.2 (Kronen in Blender auf Meshy-Stämme setzen):
1. **Stamm-Extraktion & Kronenaufbau (`build_tripo_trees.py`):**
   - Zeigt, wie man Tripo/Meshy-Holzstämme wasserdicht kappt, Sekundäräste verjüngt in die Krone verlängert und 180–320 gekrümmte, gekreuzte 3D-Blattkarten auf die Astenden verteilt.
   - **Smooth Canopy Split Normals:** Auf Slot 1 (`foliage`) werden benutzerdefinierte weiche Kronennormalen geschrieben, während Slot 0 (`bark`) scharfe Rindennormalen behält → keine harten Kartenknicke bei Sonnenlicht.
2. **Blatt- & Wedel-Atlanten (`generate_leaf_atlases.py`):**
   - Erzeugt prozedural supersampelte (`2048 → 1024`) RGBA-Atlanten mit Albedo, Normal und ORM inkl. Zweig-AO. Lässt sich direkt für den geforderten **gemeinsamen `2048²`-KTX2-Laubatlas** (inkl. Schirmakazien- und Baobab-Zweigen) adaptieren.
3. **Shader-Blueprint (`shader_reference/foliage_leaves.gdshader` → Three.js TSL):**
   - **Early Alpha-Scissor + Mip-Alpha-Boost:** `mip_alpha_boost = 1.0 + smoothstep(20.0, 140.0, v_cam_dist) * 0.28` verhindert, dass entfernte Baumkronen durch Mipmapping ausdünnen.
   - **Subsurface/Backlight im Gegenlicht:** Warmer Gelbgrün-Tint (`vec3(1.12, 1.18, 0.74)`) außen an der Krone (`radial_out`) — perfekt für Lesezeichen `G2`.
   - **Canopy AO & weiche Kronen-Normalen:** `soft_n = mix(n_w, crown_n, 0.36)` + `canopy_ao` dunkelt das Kroneninnere und die Unterseite ab.
   - **3-Ebenen-Wind:** Böenfront (`gust_front`/`gust_cross`), Hauptschwanken ab `wind_height_start` und hochfrequentes Blattflattern (`leaf_flutter`).

### 2.4 Pflicht-Stilanpassung an `art/STYLE.md` & `art/palette.json`

Die `leaf_textures/` aus *Fantasy open world* sind als sattes mittel-/dunkelgrünes Waldgrün abgestimmt. Für Violet Reach gilt laut `art/STYLE.md`:
- **Kein sattes Standard-Grün/Giftgrün**, sondern wärmeres **Oliv-/Gelbgrün** mit deutlich dunklen Kronenunterseiten:
  - `leaf_green`: `#313C1D` · `leaf_shadow`: `#050E06` · `grass_green`: `#696F44` · `grass_dry`: `#635C30` · `bark`: `#41321D`.
- Vor dem Export in Blender die übernommenen Albedo-Texturen (bzw. den gemeinsamen `2048²`-Atlas) per `vrmeshy.grade_basecolor` / Shader-Color-Grading auf die Zielpalette verschieben und die Rinde Richtung `bark` (`#41321D`) angleichen.

---

## 3. Gras & Bodenflora (Phase 4.1 & 4.2 — TSL-Blueprint statt 1:1-Kopie)

Godot-`.gdshader`-Dateien sind nicht direkt im Browser ausführbar, aber `shader_reference/grass_system.gd` und `shader_reference/grass_blade.gdshader` liefern eine erprobte technische Architektur für das GPU-Gras-System in `web/explore`:

1. **Dichte bis zum Horizont ohne Vertex-Explosion (`Mid-Range Fullness Boost`):**
   - In `grass_blade.gdshader`: `mid_boost = mix(1.0, boost_max, smoothstep(18.0, 90.0, v_cam_dist)) * dist_fade` (mit `boost_max = 1.28` für Gras, `1.12` für Schilf/Farne) streckt nur `VERTEX.xz`, während `VERTEX.y` mit `dist_fade` ausläuft. Damit schließt Gras auf mittlere Distanz (40–140 m) optisch lückenlos, bevor es in `macro_grass.webp` / die Makrokarte übergeht.
2. **Nahtlose Bodenfarb-Kopplung im Vertex-Shader:**
   - Statt pro Fragment mehrere Biome/Noise-Texturen zu lesen, berechnet `grass_blade.gdshader` die Grundfarbe einmal im Vertex-Shader (`v_base_ground`) aus einer Makro-Variation und mischt sie zur Halmspitze hin heller/wärmer. In Violet Reach kann direkt `macro_color_ao.webp` + `macro_grass.webp` im Vertex-Shader gesampelt werden.
3. **Dunkle Halmfüße statt Schattenwurf:**
   - Root-to-Tip-Farbverlauf (`root_col` dunkler am Boden `h = 0`, `tip_col` heller + Backlight/Fresnel an der Spitze `h = 1`) plus `mix(0.86, 0.54, h)` Roughness erzeugt Bodentiefe komplett ohne `castShadow` (spart die Schatten-Budgetgrenze aus `GRAFIK_PLAN.md` 11).
4. **Natürlicher 3-Komponenten-Wind mit Längen-Erhalt:**
   - Hauptwelle + Quer-Böe + hochfrequentes Einzelflattern pro Instanz-Hash, gekoppelt an `h_fac = UV.y²` und leichter Y-Absenkung (`VERTEX.y -= (abs(dx) + abs(dz)) * 0.22 * h_fac`), damit gebogene Halme nicht länger wirken.
5. **Bodenflora-Varianten (`flora_mode` 0–5):**
   - Ein gemeinsames System deckt Gras + Wildblumen (Mode 0), Uferschilf/Rohrkolben (Mode 1), Mikro-Scatter (Kiesel/Moossteine/Zweige, Mode 2), Klee/Bodenfarne (Mode 3) und Trocken-/Steppengrasbüschel (Mode 4) ab; LOD-Umschaltung bei ~44 m (`GRASS_LOD_DIST`) und Ausblendung bis 90–148 m.

---

## 4. Wasser (Phase 2 Feinschliff / Phase 5 — Gezielte Ergänzungen für `web/explore/src/water.ts`)

### Einordnung gegenüber aktuellem Stand (`p2-r12`)

`web/explore/src/water.ts` ist in Violet Reach für eine helle Tages-Szene **bereits weiter fortgeschritten** als `water.gdshader` aus *Fantasy open world*:
- Violet Reach nutzt bereits echten planaren `reflector({ resolutionScale: 0.25 })` auf Layer 1, zweischichtige Ocean-Normalmaps (`water_normal_a/b.webp`), `water_foam.webp`, Beer-Lambert-Tiefenfärbung (`#3CB2A8` → `#1B6E78` → `#0F4254`) und direktes Sonnen-Glitzern.
- `water.gdshader` aus *Fantasy open world* war für eine **Nacht-/Dämmerungslagune** geschrieben (dunkle Tiefenfarben, künstliches Aurora-/Mondlicht-Sky-Reflection und selbstleuchtende Cyan-Emission). **Farben, Nacht-Himmel-Spiegelung und Aurora-Glow dürfen NICHT übernommen werden.**

### Drei konkrete Techniken zum gezielten Portieren nach TSL

1. **Unterwasser-Kaustiken im Flachwasser (`caustics_lod` aus `water.gdshader` L. 102–131 & 275–280):**
   - Im flachen Bereich (0,08–1,5 m Tiefe, z. B. am Sandstrand von `G5` und um das Inselmonument in `F2`) erzeugt `caustics_lod` über zwei gegeneinander rotierte Voronoi-Netze ein dezentes, entfernungsgedämpftes Lichtnetz auf dem sichtbaren Seegrund. (Aktuell fehlt in `water.ts` noch jede Kaustik auf dem durchscheinenden Grund.)
2. **Schleifenfreie Fluss-Strömung (`sample_flow_normal` aus `water.gdshader` L. 133–140 & `river_water.gdshader` L. 83–92):**
   - Statt einfacher UV-Verschiebung blendet `sample_flow_normal` zwei um `0.5` phasenverschobene Normal-Samples entlang des `flow`-Vektors per Dreieckswelle (`abs(2.0 * p0 - 1.0)`). Das verhindert sichtbares Mitwandern/Verzerren entlang von Flüssen und beim Ausrollen auf die 8×8-km-Flussläufe in Phase 7.
3. **Distanz-gestaffelte Nah-Wellen & Kontakt-Schaum (`water.gdshader` L. 213–220 & 289–299):**
   - Feinere Mikro-Normalen nur unter `< 24 m` (für Strand-Nahansicht `G5`), die sauber vor der Nyquist-Grenze ausfaden, sowie tiefenabhängiges `contact_foam_depth` (0,15 m) an Steinen/Brückenpfeilern neben Ufer-Wellen.
   - *(Für Phase 7/Wasserfälle)*: `waterfall.gdshader` und `river_water.gdshader` liegen als komplette Flow-/Disp-Vorlage im Ordner `shader_reference/`.

---

## 5. Bewusst NICHT übernommen (Stil- & Qualitätsschutz)

Folgende Assets aus *Fantasy open world* passen **nicht** zu Violet Reach (`art/STYLE.md`) und wurden bewusst **nicht** importiert:
- **Mittelalter-RPG-/Dorf-Props** (`lantern_post`, `camp_tent`, `merchant_cart`, `campfire_pot`, `wooden_dock`, `stone_brazier`, grauer `mossy_boulder` aus `tripo_library.blend`): Violet Reach ist eine monumentale kalkweiß-olivgrüne Fantasy-/Sci-Fantasy-Wildnis ohne RPG-Dorf-Requisiten.
- **Low-Poly-Altsets** (`map/assets_3d_new/`, `map/assets_lowpoly/`, `map.glb`): Stilistisch und geometrisch unter dem Zielniveau von `GRAFIK_PLAN.md`.
- **Herbst-, Schnee- und Palmen-Bäume** (`tree_autumn_*`, `tree_snow_*`, `tree_coast_palm*`): Nicht Teil des M1-Spiegelsee-Bioms (können bei Bedarf später für M2-Randbiome separat gesichtet werden).

---

## 6. Bonus-Fund für spätere Audio-Phase (unberührt an Originalort)

Im Ordner `C:\Users\Mark Waldeis\Desktop\Fantasy open world\godot\assets\audio\` liegen 40 fertige `.ogg`-Dateien (keine Kopie im Staging-Ordner, da erst nach M1/M2 relevant):
- **Ambience:** `amb_meadow.ogg`, `amb_canyon.ogg`, `amb_sky_wind.ogg`, `amb_ocean.ogg`, `amb_underwater.ogg`, `amb_tunnel_stone.ogg`
- **SFX:** `sfx_river_stream.ogg`, `sfx_waterfall_gentle.ogg`, `sfx_waterfall_heavy.ogg`, `sfx_fly_wind.ogg`, `sfx_crystal_amethyst.ogg`, `sfx_step_grass.ogg`, `sfx_step_sand.ogg`, `sfx_step_stone.ogg`, `sfx_step_water.ogg`, `sfx_step_wood.ogg`, `sfx_water_splash_in/out.ogg`

---

## 7. Checkliste für die laufende Bau-Session (`grafik/next-level`)

1. **Zuerst Phase 2 (`p2-r12`) wie in `STATE.md` geplant abschließen** (Sichtung, `bench.mjs --run p2-r12`, 3 blinde Prüfer). Optional für Wasser-Nachbesserung (wenn Ufer/Flachwasser in `G5`/`F2` noch etwas Lebendigkeit brauchen): Dual-Voronoi-Kaustiken (`caustics_lod`) und `sample_flow_normal` aus `shader_reference/water.gdshader` in `web/explore/src/water.ts` ergänzen.
2. **In Phase 3 (Meshy-Vollproduktion):** `trunk_broadleaf_d` aus `queue.json` auf `tree_meadow_ancient.glb` / `tripo_trees.blend` umstellen (spart Meshy-Credits); Budget auf `trunk_acacia_b`, `trunk_baobab_a`, Klippen, Monumente, Kristalle und Himmelskörper konzentrieren.
3. **In Phase 4 (Vegetation):**
   - Bäume/Büsche/Farne aus `fantasy_open_world_import\trees_raw\` + `tripo_trees.blend` per eigenem `build.py` in Blender importieren, Laub/Rinde auf `art/palette.json` (`leaf_green` `#313C1D`, `leaf_shadow` `#050E06`, `bark` `#41321D`) graden, Kronen-Rezept aus `build_tripo_trees.py` + `generate_leaf_atlases.py` auf `trunk_acacia_a/b` und `trunk_baobab_a` anwenden und alles durch `vr.py` Gate (`>= 8/10`) + KTX2 exportieren.
   - `foliage_leaves.gdshader` (Backlight, Canopy-Normalen, Mip-Alpha-Boost, 3-Ebenen-Wind) und `grass_blade.gdshader` / `grass_system.gd` (Mid-Range Fullness Boost bis 1,28×, Vertex-Farbkopplung an `macro_color_ao`/`macro_grass`, dunkle Halmfüße, 3-Komponenten-Wind) als TSL-Architekturvorlage für das WebGPU-Vegetationssystem in `web/explore` verwenden.
