# Grafik-Stand (GRAFIK_PLAN.md)

Diese Datei reicht, damit eine neue Session nahtlos weitermacht. Nach jedem Arbeitspaket aktualisieren.

## Aktuell

- Zweig: `main` (synchron mit `grafik/next-level`) — UTF-8-Gate-Fix, CI (`gate.yml` inkl. `web/explore`), Start-Skript (`VR_GATE_CACHE_MS=30000`), `high`-Gras-Sichtweite `>= 90 m`, Alt-Asset-/2K-Cleanup, Phase-4-Vegetation/Monument & Phase-5-Klippen/Himmelsschiffe vollständig umgesetzt und verifiziert.
- Phase: **Phasen 1–5 abgeschlossen & verifiziert (`35 / 35` Assets durch das Gate, alle exportiert und in `web/public/assets/` synchronisiert; `1.274` Einträge in `world/placements.json`).**
- Abgeschlossener Stand der aktuellen Runde (12/12 Assets abgenommen & exportiert):
  - **Trees R9.6–R9.8 (4 Arten):** `tree_oak_a` (`9.87 MB`), `tree_beech_a` (R9.6 `8/8/9/9/9/8`, `8.95 MB`), `tree_ancient_a` (R9.6 `8/8/9/9/9/8`, `9.85 MB`), `tree_willow_a` (R9.8 `8/8/8/9/9/8`, `9.86 MB`) — konsistentes `#41321D`-Holzalbedo, glatte Pro-Komponenten-Normalen ohne schwarze `clay`-Terminatoren, entfernte Stümpfe/Speerspitzen/Stängelhalos und volle `transparent_max_bounces = 32`.
  - **Monumente:** `monument_split_disc_a` (R13 `9/8/8/9/8/9`, `3.55 MB`, 3D-Bogenplinthe + Keilsteine + Bruchkern, platziert im See bei `(680, 1561)`, `y_offset -1.6`) und `monument_rib_crown_a` (`8/8/8/9/9/9`, `3.07 MB`, platziert bei `(150, 1830)`, `y_offset -5.8`); beide in `REFLECTED_HERO_ASSETS` eingetragen.
  - **Phase 5 Kreideklippen & Himmelskörper:** `cliff_chalk_wall_a` (`4.87 MB`), `cliff_chalk_wall_b` (`4.88 MB`), 0-Credit-Kitbash `cliff_chalk_corner_a` (R4 `9/8/9/9/9/9`, `4.90 MB`), 0-Credit-Kitbash `rock_pillar_chalk_a` (R4 `8/8/9/9/9/9`, `4.93 MB`) am Klippenkamm `(682..688, 1170..1278)` sowie `skyship_pod_a` (`3.18 MB`) und `skyship_pod_b` (`1.52 MB`, 2×) am Himmel platziert (`world/slice.json` & `world-content.test.ts` synchronisiert).
- Verifikation (unbeladene Maschine, nach letztem Edit):
  - `python tools/vr.py check`: `gate ok: 35 assets checked`; `test_gate.py`, `test_world.py`, `test_tree_rollout_apply.py` grün; Blender-Unit-Tests `test_canopy_lod.py` & `test_export_asset.py` grün.
  - `web` Build, `web/explore` `tsc --noEmit`, `web/explore` Vite-Build & `web/explore` Test-Suite (`142 / 142` Tests grün, `0` failed, `0` skipped) bestanden.
  - Live-WebGPU-Bench `phase5-full` (`high`, 0 Budgetverletzungen): `ground` **59.86 FPS Mittel** (`1 % Low 52.95`, max `33.4 ms`, CPU `5.79 ms`, max `3.123.990` Dreiecke, max `294` Draws, `1227 MiB` Textur), `flight` **59.94 FPS Mittel** (`1 % Low 59.49`, max `16.9 ms`, CPU `4.45 ms`, max `1.709.834` Dreiecke, max `226` Draws).
  - Live-Captures `G1..G7`, `F1..F4`, `H1..H2` in `C:\Users\Mark Waldeis\devin-screenshots\violet-reach\phase5-full` gesichtet (Luftschiffe, Rippenkrone, See-Spaltscheibe, Kreideklippen, Bäume sauber verankert).
- Meshy-Kostenbuch & Queue: **873 / 2000 Credits** verbraucht (`rework 285 / 320`, Kontostand `2287`, keine neuen Meshy-Credits verbraucht); `Violet Reach Meshy/queue.json` auf `in_game` synchronisiert.

### Offene Arbeiten (Phase 6 / M1–M2 Backlog)

1. **Code-Deduplizierung der Baum-Skripte:** Wiederkehrende Post-Build-Helper (`_match_oak_bark_albedo`, `_plug_root_gap`, `_fix_foliage_and_bark_normals`, `_remove_disconnected_bark_stubs`) mittelfristig aus den einzelnen `tree_*_a/build.py` in ein gemeinsames Helper-Modul unter `tools/blender/` konsolidieren.
2. **Phase 6 & M1/M2 Welt-Ausbau:** Weitere Ruinenfelder, Pfad-/Küstendetails und atmosphärisches Polishing gemäß Zielbild `M1`/`M2` sowie abschließende blinde Gesamt-Qualitätsabnahme der Landmark-Kameraansichten (`G1–G7`, `F1–F4`, `H1–H2`).

### GRAS-DURCHBRUCH 2025 — three.js Instancing-Semantik (WICHTIGSTES Wissen dieser Phase)

**Root cause des unsichtbaren Grases:** In `NodeMaterial.setupPosition` (three.js source) läuft `instancedMesh(object)` ZUERST (positionLocal = instanceMatrix * positionLocal), danach `if (material.positionNode) positionLocal.assign(positionNode)` — ein custom positionNode **überschreibt die Instanzierung vollständig**. Alle 38.750 Halme renderten gestapelt am Zell-Ursprung (Weltnullpunkt). Diagnose-Kette: Rot-Test mit MeshBasicMaterial (kein positionNode) → Gras sichtbar an korrekten Positionen; positionNode=null-Klon des TSL-Materials → sichtbar; also positionNode der Übeltäter; three.js-Source bestätigte die Overwrite-Semantik.

**Fix-Architektur (committed f7bb548):** komplette Instanz-Transformation manuell im positionNode — Yaw deterministisch aus `aInfo.w` (instance-hash) abgeleitet (`yaw = hash * 6.2831`, Rotation in xz), Width/Height-Skalierung aus aShade, Weltposition aus `aInfo.xyz` addiert, Wind danach. Attribute MÜSSEN per `instancedBufferAttribute(attr, 'vec4')` mit dem echten Attribut-Objekt gebunden werden (nicht namensbasiertes `attribute()`) → pro Zelle eigenes Material (`grassMaterial({aInfo, aShade}, …)` in grass-system.ts). Instanzmatrizen bleiben reine Translationen und sind nur noch für Frustum-Culling relevant.

**Frustum-Culling-Falle (zweiter Bug davor):** `InstancedMesh.computeBoundingSphere` transformiert die Geometry-Sphäre mit den Instanzmatrizen — manuell in Weltkoordinaten gebaute boundingSphere wurde dadurch doppelt verschoben und alles gecullt. Fix: korrekte lokale Geometry-Bounds, keine manuelle Welt-Sphäre.

**Gras-Farb-Pipeline-Fallen (a413710):** (1) three.js r186 multipliziert diffuse automatisch mit instanceColor sobald mesh.instanceColor gesetzt — colorNode darf den Tint NICHT nochmal enthalten (sonst tint²). (2) Makro-Bytes sind sRGB-kodiert — CPU-Sampler muss srgbToLinear() anwenden bevor Werte in lineare Renderpipeline gehen (GPU-Texturen mit SRGBColorSpace linearisieren automatisch, Buffer-Attribute nicht). (3) material.normalNode wird als VIEW-Space interpretiert — vec3(0,1,0) ist Bildschirm-oben nicht Welt-oben; für Welt-Normalen transformieren. Finale Gras-Farbwerte: hueK lush (0.82,1.38,0.60)/straw (1.12,1.02,0.45) × Wurzel→Mitte 0.34→1.0 × Spitzen-Wärmung (1.48,1.30,0.82). Memory-Repo hat Details.

**Weitere Fallen:** aInfo/aShade müssen `InstancedBufferAttribute` sein (nicht BufferAttribute). Debug-Hooks noch im Code: `window.__grass` in main.ts:110, `__gdbg` in main.ts:273ff, `debugBasicMaterial()` in grass-system.ts:92, div. `*.tmp.mjs` in web/explore — vor finalem Capture aufräumen. Test-Runner ist `node --test` (npm test), NICHT vitest.

**Visueller Stand nach Fix:** Gras rendert und bedeckt die Wiese. **Farbtuning fertig (grass-tune7.png, Vergleich grass-before-after.png):** saftiges Frühlingswiesen-Grün mit gelbgrünen Spitzen, dunklen Wurzeln, pro-Halm-Variation — harmonisch zum olivfarbenen Boden, aber erkennbar frischer/heller. Perf-Grobmessung bei G3: +180-230k Tris, +15-24 Draws durch Gras.

**GRAS-FARBEN — drei versteckte Fallen (Root causes des schlammig-braunen Bildes):**
1. **Doppelter Tint:** three.js `NodeMaterial.setupDiffuseColor` multipliziert diffuseColor AUTOMATISCH mit `instanceColor`, sobald `mesh.instanceColor` gesetzt ist — das Material multiplizierte den Tint zusätzlich manuell → tint², extrem dunkel. colorNode darf den Tint daher NIE selbst enthalten (nur Hue-Korrektur/Gradient/Variation); Emissive wird dagegen NICHT auto-getintet und braucht den manuellen Faktor.
2. **sRGB vs. linear:** die Makro-Tint-Bytes sind sRGB-kodiert; der Terrain-Shader bekommt sie per SRGBColorSpace-Textur auto-linearisiert, der CPU-Sampler aber reichte Rohwerte durch → entsättigtes Oliv. Fix: `srgbToLinear()` beim Befüllen des tint-Arrays in grass-system.ts.
3. **normalNode ist VIEW-Space:** eine Konstante vec3(0,1,0) bedeutet Bildschirm-oben, nicht Welt-oben (Beleuchtung hing von der Kamera!). Fix: Welt-up + yaw-rotierte Geometrie-Normalen (10-28% Höhenanteil) per `transformNormalToView` — gibt zusätzlich plastische Tiefenwirkung pro Halm.
Empirischer Nachweis für 1: colorNode=reines Weiß → Halme rendern im blassen Tint (grass-tune2-diagwhite.png). Hue-Pipeline: hueK (lush→oliv-frisch (0.82,1.38,0.60), straw bei dry) × Wurzel-zu-Spitze-Gradient (0.34→1.0) × Spitzen-Wärmung (1.48,1.30,0.82) × Quer-Schattierung × Hash-Variation — Konstanten modulweit in grass-material.ts, Probe grassPaletteProbe spiegelt Ist-Farben.

### Placement-Bestand (world/placements.json, 1243 Einträge) — WICHTIG für Optimierung

Instanz-Zahlen nach der grass_tuft-Entfernung: reed_cluster_a 12.384, fern_cluster_a 2.075, shrub_round_a 1.148, tree_broadleaf a/b/c 122/120/118, shore_rocks_wet_a 7, scree_pile_a 6, boulder_chalk_a 5, boulder_chalk_c 3, bush_lush_a 15; deklarierte Gesamtinstanzen 16.019. **Alle 13 grass_tuft_a-Scatter (64.120 expandierte Instanzen) sind entfernt; GPU-Gras ist jetzt alleinige Grasdarstellung.** Capture G1/G3/G4/G6 zeigt keine Baldness/Lücken und freie Wege. Bench-Effekt war jedoch klein: 1%-lows +1.2/+1.9 FPS, Textur -1.33 MiB, Dreieckspeak praktisch unverändert. Der Altbestand war also Integrations-/Speicher-/CPU-Ballast, aber nicht der Haupttreiber des verbleibenden Perf-Problems. Nächster Schritt: broadleaf a/b/c durch die reviewed Fantasy-Bäume ersetzen; bush_lush/fern_lush können shrub_round/fern_cluster ergänzen oder ersetzen.

### Gras-Perf-Stand (bench p41-grass, LAST-KONTAMINIERT)

Bench-Lauf während Blender/Browser-Agenten aktiv: ground 52.94/12.56 FPS, flight 56.18/11.57, längste Frames 133-250 ms (Last-Spikes, keine steady-state Gras-Kosten). **Aber echtes Signal: Dreiecke max 4.579.266 auf ground über 4M-Richtwert** (vor Gras ~2.37M an G3). Textur 936 MiB ok. Nach Agenten-Ende: sauberer Rerun nötig; falls Dreiecke weiterhin über Budget: Distanz-Instanzen/Dichte optimieren (fadeEnd=viewDistance bei high=96m, kaum tote Instanzen — eher Density/Clump-Geometrie/Distanzabstufung prüfen).

### Gras-Perf-Optimierung (laufender Commit nach 8045b61)

- **Streaming/CPU:** Zellbau ist jetzt inkrementell mit harter Zeitscheibe (`buildBudgetMs` 1,5 ms, `maxBuildPerFrame` nur Sicherheitskappe 8). Render-Slots mit Material, Nah/Fern-Geometrien, Instanzmatrizen und Attributpuffern werden gepoolt statt an Zellgrenzen synchron disposed/neu erzeugt. Beim Slot-Reuse werden nur belegte Präfixe per `addUpdateRange` hochgeladen.
- **Scan-Kosten:** `densityCellMax()` bildet eine konservative obere Makro-Dichte je 16-m-Zelle. Ganz leere Wasser/Weg/Fels-Zellen werden sofort verworfen; nichtleere Zellen scannen nur den statistisch nötigen Kandidatenanteil und kompensieren ihn über denselben Hash (`h1 * densityScale`). Am G3-Ring: 78/139 Zellen leer, mittleres Dichte-Maximum 0,363 → ca. 64 % weniger Kandidaten. Messung settled: `skipDensity` 162.008 → 33.389 bei praktisch gleicher Instanzzahl 38.739 → 38.724.
- **LOD ohne Rebuild:** Kandidaten laufen in deterministisch permutierter, pro Zelle rotierter Reihenfolge; jedes Präfix ist räumlich uniform. `mesh.count` ist dadurch ein Distanz-Dichte-LOD ohne Instanz-Neuaufbau. Ferngeometrie ab ca. 42 m (high): 6 gerade Ein-Dreieck-Halme statt 6 gekrümmten Drei-Dreieck-Halmen, 24 % breiter als Silhouettenausgleich. Instanzverdünnung auf 50 % liegt erst innerhalb der vorhandenen Shader-Fade/Width-Boost-Hülle 69–96 m, damit keine sichtbare Mitteldistanz-Lücke entsteht.
- **Sichtprüfung G3** (`cam=360,1.7,1680,-0.68,-0.18&agl=1&freeze=1`): `grassperf-after4/G3.png` bleibt dicht/saftig, ohne erkennbare Kachelwiederholung, Pop-Kante oder Farbversatz; Vergleich `grassperf-compare-after3.png`. Settled-Stats final: 49 bebaute Zellen, 38.724 Vollinstanzen, 33.456 sichtbar nach Präfix-LOD, 382.752 Gras-Dreiecke statt 697.032 bei durchgehend voller Nahgeometrie.
- **Verifikation:** `node --test test/grass.test.ts` 8/8, Gesamt-suite zuletzt 95/95, `npx tsc --noEmit` sauber. QA-Stats sind über `window.__vr.stats().grass` verfügbar.
- **Bench-Status:** Sauberer `p41-opt-clean` (WebGPU/RDNA2): ground 57.69/20.54 FPS, max 66.8 ms, Dreiecke max 4.169.942; flight 58.06/17.00, max 200.2 ms; sechs Budgetverletzungen plus Dreieckswarnung. Nach der grass_tuft-Entfernung (`tuft-entfernt`, ebenfalls valid): ground 57.99/21.77, max 66.9 ms, Dreiecke max 4.168.620; flight 58.32/18.87, max 200.1 ms. Frames >50 ms verbessern sich ground 12→10 und flight 18→9, aber das Budget bleibt verletzt. Die alte Annahme, grass_tuft sei der große Dreieckshebel, ist empirisch widerlegt; verbleibende Ursachen müssen gemessen werden (GPU-Gras/Terrain/Instanz-Assets/Streaming).

### Gras-System Architektur (Phase 4.1, committed, unverifiziert)

- `grass-macro.ts`: CPU-Sampler, bilinear, liest DIESELBEN `macro_grass.webp`/`macro_color_ao.webp` wie der Boden-Shader (perfekter Farb-/Dichteanschluss). Kanäle: Dichte/Höhe/Dry/Canopy + Tint/AO.
- `grass-clump.ts`: prozedurale Büschel, 6 Halme à 3 Tris (spitz zulaufend, 5 Verts), uv.y=Höhenfraktion, color.r=Blatt-Hash, color.g=Flex.
- `grass-material.ts`: TSL, Fantasy-Blueprint — 3-Komponenten-Wind (wave/gust/flutter, h²-gewichtet, worldTime-fähig/freeze-sicher), Width-Boost in der Mitte, Distance-Fade, Wurzel-zu-Spitze-Gradient, macro-gekoppelte Tönung pro Instanz, warmes Backlight. Instanz-Attribute: `aInfo`(xyz Welt+Hash), `aShade`(canopy,dry,heightScale,widthMul), `instanceColor`(tint).
- `grass-system.ts`: Ring-Streaming 16-m-Zellen, seit der Perf-Runde zeitscheiben-inkrementelle Builds, gepoolte Render-Slots, reine Translations-Instanzmatrizen (Wind bleibt weltkohärent), kein Shadow-Casting, receiveShadow ja.
- `main.ts`: Qualitätsstufen low/medium/high/ultra = 44m/2.6, 68m/4.0, 96m/5.5, 128m/6.5 (Sichtweite/Dichte pro m²). Deaktivierbar mit `?nograss`.
- Perf-Budget: Grundstrecke hatte vor Gras nur 47,71 FPS 1%-low — Grass muss sparsam bleiben. Der verbleibende Integrationshebel ist weniger weitere GPU-Gras-Verdünnung als das Entfernen/Ersetzen der parallelen alten `grass_tuft_a`-Instanzen.

## Noten je Lesezeichen — Nulllinie (`p0-baseline`)

Median aus 3 unabhängigen Prüfern (`reviewer_a`, `reviewer_b`, `reviewer_c`; Einzelwertungen `A/B/C` in `C:\Users\Mark Waldeis\devin-screenshots\violet-reach\p0-baseline\`). Skala 1–10 (Ziel M1/M2: Median ≥ 8 in jedem Punkt).

| Lesezeichen | Licht & Atmo | Boden | Vegetation | Fels & Bauten | Wasser | Himmel | Maßstab | Technik |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **G1** (Wanderweg → See) | **3** (3/3/2) | **2** (2/3/2) | **1** (1/2/1) | **3** (3/4/3) | **3** (3/3/2) | **2** (2/3/2) | **2** (2/3/2) | **4** (4/4/3) |
| **G2** (Hain Gegenlicht) | **3** (3/3/3) | **2** (2/3/2) | **2** (2/3/2) | **1** (1/2/1) | — | **2** (2/3/2) | **3** (3/3/2) | **3** (3/3/2) |
| **G3** (Offene Wiese) | **3** (3/3/2) | **3** (3/3/2) | **2** (2/2/1) | **3** (3/3/2) | **3** (3/3/2) | **2** (2/3/2) | **2** (2/3/2) | **4** (4/4/3) |
| **G4** (Stamm & Farne) | **3** (3/3/2) | **2** (3/2/2) | **2** (2/3/2) | **2** (2/2/2) | **3** (3/3/2) | **2** (2/2/2) | **3** (3/3/2) | **2** (2/2/1) |
| **G5** (Strand, Tor, Brücke) | **3** (3/3/2) | **3** (3/3/3) | **2** (2/3/2) | **4** (4/4/3) | **2** (2/3/2) | **2** (2/3/2) | **3** (3/3/2) | **3** (3/4/2) |
| **G6** (3 m vor Säulensockel) | **4** (4/4/3) | **3** (3/3/2) | **2** (2/2/1) | **4** (4/4/3) | **3** (3/3/2) | **2** (2/3/2) | **3** (3/3/2) | **3** (3/3/2) |
| **G7** (Fuß der Steilflanke) | **3** (3/3/2) | **2** (2/2/2) | **3** (3/3/2) | **1** (1/1/1) | — | **2** (2/3/2) | **1** (1/2/1) | **3** (3/3/2) |
| **F1** (Flugstart) | **3** (3/3/2) | **2** (2/3/2) | **2** (2/3/2) | **2** (2/3/2) | **2** (2/3/2) | **2** (2/3/2) | **3** (3/3/2) | **3** (3/4/2) |
| **F2** (30 m über Nordufer) | **3** (3/3/2) | **2** (2/3/2) | **2** (2/2/2) | **2** (2/3/2) | **3** (3/3/3) | **2** (2/2/2) | **2** (2/2/2) | **3** (3/3/2) |
| **F3** (Über Hain → SW-Ufer) | **3** (3/3/2) | **2** (2/2/2) | **2** (2/3/2) | **1** (1/1/1) | **3** (3/3/2) | **2** (2/3/2) | **2** (2/2/1) | **2** (2/3/2) |
| **F4** (Ostflanke Mittelrücken) | **3** (3/3/2) | **2** (2/2/2) | **3** (3/3/2) | **1** (1/1/1) | — | **2** (2/3/2) | **2** (2/2/1) | **3** (3/3/2) |
| **H1** (350 m über Ausschnitt) | **2** (2/2/2) | **2** (2/2/2) | **2** (2/2/2) | **2** (2/2/2) | **2** (2/3/2) | **1.5** (1/2/—) | **2** (2/2/2) | **3** (3/3/2) |
| **H2** (350 m Fernsicht Welt) | **2** (2/2/2) | **2** (2/2/1) | **1** (1/1/1) | **1** (2/1/1) | **2** (2/3/2) | **2** (1/2/2) | **2** (2/2/1) | **2** (2/2/1) |

## Messwerte — Nulllinie (`p0-baseline` / `high`, WebGPU · AMD RDNA-2, 1920×1080)

| Strecke / Metrik | Bodenweg (`ground`, 399,8 m, 40 s) | Überflug (`flight`, 2638,1 m, 38,8 s) | Budget (`high`) |
|---|---:|---:|---:|
| **FPS Mittel** | 59,94 FPS | 59,94 FPS | ≥ 60 (±0,5 VSync) |
| **FPS 1 % Low** | 58,28 FPS | 58,74 FPS | ≥ 45 |
| **Längstes Einzelbild** | 19,8 ms | 17,6 ms | < 50 ms |
| **Framezeit (Mean / P95 / P99)** | 16,68 / 16,8 / 16,9 ms | 16,68 / 16,8 / 16,9 ms | — |
| **CPU-Zeit (Mean / P95)** | 4,75 / 9,2 ms | 3,34 / 4,5 ms | — |
| **Sichtbare Dreiecke (Mean / Max)** | 1,65 Mio. / 2,68 Mio. | 0,86 Mio. / 1,38 Mio. | Richtwert 4 / 5 Mio. |
| **Draw Calls (Mean / Max)** | 120,6 / 174 | 113,1 / 172 | ≤ 400 |
| **Texturspeicher GPU** | 1473,6 MiB (1.545.230.143 B, 77 Texturen) | 1473,6 MiB (1.545.230.143 B, 77 Texturen) | ≤ 1536 MiB (1,5 GiB) |
| **Budget-Verletzungen** | 0 | 0 | 0 |

*(Hinweis: Der Texturspeicher liegt bereits im Ausgangszustand bei 1,47 GiB von 1,50 GiB, weil die 15 Alt-Assets unkomprimierte 2K/4K-RGBA-Texturen aus WebP auf der GPU entpacken — KTX2 in Phase 3/5 wird diesen Speicher drastisch senken.)*

## Offene Mängel (Stand nach Phase 1 `p1-r7`)

1. ~~**Flaues, kontrastarmes Licht und dichter 82-%-Beigeschleier**~~ → **Phase 1 umgesetzt (`p1-r7`)**: ACESFilmic, 3D-Six-Way-Wolken (2048×1024), Gasriese & zertrümmerter Mond, Sky-PMREM, 4 CSM-Kaskaden, GTAO, Godrays, Bloom & Grading. *(Offen in Phase 2/5: Sand-Highlight-Clipping in G5 über PBR-Sand-Albedo beheben; Mond-Bruchstücke noch felsiger nachschärfen.)*
2. **Prozeduraler Einheitsboden mit Treppenstufen an Hängen und Detail-Abbruch ab 30 m** (G1, G3, G7, F1, F4, H1, H2): Sägezahn-Artefakte entlang der Grün-Beige-Hangschwelle auf dem 2-m-Raster, fehlende KTX2/PBR-Bodenschichten, fehlende 4096²-Welt-Makrokarte und fehlende Triplanar-Felsprojektion ab 35° → **Phase 2**.
3. **Opakes, graublaues Wasser ohne Tiefendurchsicht, Uferschaum, nassen Saum und Spiegelung** sowie isoliertes Wasserloch unter der Brücke in G1 → **Phase 2**.
4. **Massiver Vegetationsmangel und grobe Alt-Bäume mit hervorstehendem Wurzelkragen** (G1–G4, F3, H2): Gras endet nach 20 m (Grünanteil G1 14,6 % statt 62,8 %), brauner Polygon-Kragen ragt in G4 scharfkantig aus dem Hang, flache Laubkarten ohne Durchlicht, 0 Bäume/Impostors außerhalb des Ausschnitts → **Phase 4**.
5. **Vollständiges Fehlen von Klippen, Schichtfelsen, Großmonumenten (>100 m Rippenkrone, Inselmonument, Viadukt) und Pods** (G7, F1–F4, H1, H2) → **Phase 3, 5, 6**.

---

## Phase 1 — Licht, Himmel, Wolken, Planeten & Post-Processing (`p1-r7`)

### Tonemapping-Vergleich (`p1-tonemap-*`, WebGPU `high`)

| Modus | `G1` Kontrast / Sat | `G2` Kontrast / Sat | `F1` Kontrast / Sat | Entscheidung |
|---|---:|---:|---:|---|
| `agx` (`p1-tonemap-agx`) | 0,4672 / 0,1711 | 0,5834 / 0,4966 | 0,3438 / 0,1973 | verworfen (zu flau/entsättigt) |
| `neutral` (`p1-tonemap-neutral`) | 0,7076 / 0,3154 | 0,5279 / 0,7646 | 0,5821 / 0,3502 | verworfen (Übersättigung / harte Tiefen) |
| **`aces`** (`p1-tonemap-aces`) | **0,6381 / 0,2241** | **0,6445 / 0,5292** | **0,4882 / 0,2666** | **Standard (`ACESFilmicToneMapping`)** |

### Iterationsverlauf (`p1-r2` → `p1-r7`)
- **`p1-r2` / `p1-r3`:** Horizonthimmel-Ring (`768×384`) zeigte horizontale UV-Naht und leere Blickwinkel; unpremultiplied WebGL2-Six-Way-Decoder & `samples=1` Post-Warmup ergänzt (Max-Framezeit `50,1 ms` → `17 ms`).
- **`p1-r4`:** 108 instanziierte 3D-Six-Way-Wolken-Billboards (`2048×1024`-Atlas) über 360° eliminierten die Horizontalnaht; Decknamen/Cones zeigten jedoch gerade Unterkanten, und der Mondring bildete Streifenartefakte.
- **`p1-r5`:** Organische Basis-Auflösung über exaktem `baseline_v` pro Zelle (ohne Streifen-/Kegelzellen `[1,6,7]`) beseitigte alle geraden Wolken-Cuts, wusch jedoch über zu dichten Nebel Kontrast (`H2 0,358`) und Wolkenplastik aus.
- **`p1-r6`:** Kräftigeres Sky-Blau, zurückgenommener Nebel (`≤ 44 %`), skulptierte Wolken-Selbstverschattung (`scatteredDirect^1.05`) und Polygon-Mondtrümmer hoben 8/12 Himmel-Lesezeichen auf Median `7`, hinterließen jedoch Planeten-Schattenhalo, breite Diagonal-Zirren und dunklen `G2`-Stamm (`luma_p5 = 0,011`).
- **`p1-r7`:** Physikalische Taghimmel-Streuung am Gasriesen (halo-frei), feinere gepatchte Multi-Oktav-Zirren, härtere Mondbruch-Kanten (`A+B+C` bestätigt) und Schattenboden-Erholung in `G2` (`luma_p5 = 0,044`).

### Noten je Lesezeichen (`p1-r7` — 3 unabhängige Prüfer `A/B/C`: `9cf215bb` / `3c04f8bc` / `f6a8d5ea`)

| Lesezeichen | Himmel (Median) | Licht (Median) | Hinweis (Trennung zu Legacy-Terrain/Wasser) |
|---|---:|---:|---|
| **G1** (Wanderweg → See) | **7** (7/8/7) | **7** (7/7/6) | Gasriese halo-frei, Taldunst & Wolken sauber |
| **G2** (Hain Gegenlicht) | **7** (7/7/6) | **8** (8/8/8) | God-Rays & Stamm-Schattenboden (`luma_p5 = 0,044`) stark |
| **G3** (Offene Wiese) | **7** (7/7/7) | **6** (7/6/6) | Himmel sauber; flaches Legacy-Gras/Wasser vor Phase 2 |
| **G4** (Stamm & Farne) | **6** (6/7/6) | **7** (6/7/7) | Nur 9,1 % Himmelsausschnitt in Bildecke |
| **G5** (Strand, Tor, Brücke) | **7** (7/7/7) | **5** (5/6/5) | Heller un-PBR-Sand rechts vor Phase 2 |
| **G6** (3 m vor Säulensockel) | **7** (6/8/7) | **8** (7/8/8) | Architektur-Licht & Highlight-Rolloff exakt |
| **G7** (Fuß der Steilflanke) | **6** (6/7/6) | **6** (6/6/6) | Untexturierter Steilhang vor Phase 2, schmaler Himmel |
| **F1** (Flugstart) | **7** (7/8/7) | **7** (7/7/7) | Komplettes Himmelspanorama ohne Halos/Cuts |
| **F2** (30 m über Nordufer) | **7** (7/7/7) | **7** (7/7/7) | Planet & Wolken sauber; See noch unfertig (Phase 2) |
| **F3** (Über Hain → SW-Ufer) | **7** (6/7/7) | **6** (6/6/6) | Legacy-Grashügel vor Phase 2 |
| **F4** (Ostflanke Mittelrücken) | **7** (7/7/7) | **7** (7/7/7) | Gute Wolkenstaffelung & Hangrelief |
| **H1** (350 m über Ausschnitt) | **n/v** | **6** (5/6/6) | Steilblick nach unten ohne Himmel; Legacy-Boden |
| **H2** (350 m Fernsicht Welt) | **7** (7/8/7) | **7** (7/7/7) | Monumentalansicht mit Zirren, Planet & Mond |

### Messwerte (`p1-r7` / `high`, WebGPU · AMD RDNA-2, 1920×1080, nach KTX2 `df87c8f`)

| Strecke / Metrik | Bodenweg (`ground`) | Überflug (`flight`) | Budget (`high`) |
|---|---:|---:|---:|
| **FPS Mittel** | 59,94 FPS | 59,94 FPS | ≥ 60 (±0,5 VSync) |
| **FPS 1 % Low** | 59,38 FPS | 59,42 FPS | ≥ 45 |
| **Längstes Einzelbild** | 17,0 ms | 17,1 ms | < 50 ms |
| **CPU-Zeit (Mean / P95)** | 4,51 / 7,1 ms | 3,90 / 5,0 ms | — |
| **Sichtbare Dreiecke (Mean / Max)** | 1,88 Mio. / 3,03 Mio. | 1,01 Mio. / 1,68 Mio. | Richtwert 4 / 5 Mio. |
| **Draw Calls (Mean / Max)** | 139,5 / 193 | 127,1 / 186 | ≤ 400 |
| **Texturspeicher GPU** | **537 MiB** (99 Texturen) | **537 MiB** (99 Texturen) | ≤ 1536 MiB |
| **Budget-Verletzungen** | **0** | **0** | 0 |

---

## Phase 2 — Zwischenstand (WIP Checkpoint `p2-r12`)

- **Umgesetzte Änderungen (`p2-r4`..`p2-r12`):**
  - `tools/world/build_macromap.py` + neu generierte `web/explore/public/ground/{macro.json,macro_color_ao.webp,macro_grass.webp,macro_weights_a.webp,macro_weights_b.webp}`: Tal-Fels-Schwelle auf `41,0–50,0°` angehoben und hochalpines Kalkstein-Plateau (`h > 325..400 m` ab `14..26°` + `h > 420..490 m`) ergänzt; falsche Kreideflecken/Grünsprenkel auf Tälern sowie die `H1`-Gratnaht beseitigt.
  - `web/explore/src/ground-material.ts` (+ `web/explore/src/main.ts`, `web/explore/test/ground-material.test.ts`): 9 `1k`-PBR-Schichten in `1024×1024×9` `DataArrayTexture`s + 3 Welt-Makrokarten (`waitForGroundTextures()`), `36 m`-Makro-Bodenstruktur (`soil` + `mNrm` mit `midNormalFade` `45..160 m` bis `980 m`), gekörnte Sand-/Kies-Küsten mit dunklem Nasssaum (`roughness 0,18`), gekalkte Pfade, `64 m` geschichtete Kalkklippen (`chalk_rock`) und enges `screeBand` an Steilflanken (`G7`/`F4`).
  - `web/explore/src/water.ts`: `MeshPhysicalNodeMaterial` (`metalness: 0`, `ior: 1.333`) mit `specularIntensityNode` (gegen Grazing-Milchschleier), echtem Planaren `reflector({ resolutionScale: 0.25, bounces: false })` auf dem Spiegelsee (`y = 180.03`) mit `hWave`-Fade bis `85 m` (ohne Nyquist-Stipple), Beer-Lambert-Tiefe/Farbkörper, HDR-Sonnenglanz und geflecktem Uferschaum (`isOpenLake`).
  - `web/explore/src/quality.ts` (`REFLECTION_LAYER = 1`), `atmosphere.ts`, `sky-bodies.ts`, `terrain-stream.ts`, `instance-assets.ts`: Layer-Filterung (`REFLECTION_LAYER = 1`) und `DirectionalLight`-Shadow-Reuse im Planar-Reflector.
- **Iterationsverlauf:**
  - `p2-r9`: `0` Budget-Verstöße (`59,91 / 59,94 FPS`, `897 MiB`), Grauschleier behoben; 3 blinde Prüfer noch `FAIL` (dunkles Wasser, `windPatch`-Streifen, falsche Kreideflecken).
  - `p2-r10`: `0` Budget-Verstöße (`59,94 / 59,94 FPS`, `897 MiB`), falsche Tal-Kreideflecken & `H1`-Naht beseitigt; 3 blinde Prüfer noch `FAIL` (`hWave`-Stipple, durchgehender Schaumring, glatte Grünhügel, fehlende Strände/Spiegelungen).
  - `p2-r11`: Planarer Reflector (`0.35`), `36 m` Makro-Körnung, `64 m` Schichtfels, durchgehende Strände und gefleckter Schaum umgesetzt (optisch großer Sprung), jedoch `bench.mjs` `FAIL` (Exit `4`, `5` Verstöße: `ground` `58,51 FPS` Mean / `24,37` 1% Low / `66,9 ms` Max / `6,05 Mio.` Tris / `386` Draws) durch volle Szenen-/CSM-Neurenderung im Reflector.
  - **`p2-r12` (aktueller Pause-Stand):** `REFLECTION_LAYER = 1`, `resolutionScale: 0.25` & Shadow-Reuse-Wrapper implementiert; `84/84` Explorer-Unit-Tests & `vite build` grün. `capture.mjs --run p2-r12 --seq` wurde beim Pausieren nach den 13 Lesezeichen-Screenshots (`G1`..`H2` in `C:\Users\Mark Waldeis\devin-screenshots\violet-reach\p2-r12\`) gestoppt; Sichtung, `bench.mjs --run p2-r12` und 3 blinde Prüfer stehen beim Fortsetzen an erster Stelle aus.


---

## Phase 2 — Vegetations-Export und Streaming-Performance (aktuell)

- **Fantasy-Vegetation approved + exportiert:** `tree_oak_a`, `tree_beech_a`, `tree_ancient_a`, `tree_willow_a`, `fern_lush_a` sind alle approved und exportiert (`web/public/assets/*.glb`, Manifest synchron, `vr.py check` grün: 34 Assets). Export-LOD-Zielwerte: oak `[3820,1500,550,160]`, beech `[2700,1100,420,140]`, ancient `[5290,2000,750,220]`, willow `[2596,1000,380,140]`, fern `[448,220,96,48]`; Export-Pipeline trianguliert vor Decimate, damit LOD-Budgets in Dreiecken stimmen.
- **Grass-Streaming root cause:** Spikes sind exakt an 16-m-Graszellgrenzen synchronisiert (z. B. x352/368/384/400/416/432/448 und z1392/1408/1424). Terrain-x512 ist ausgeschlossen. Hauptmechanismus: Ring-Edge-Builds + Completion-Bursts + viele separate WebGPU-`writeBuffer`-Uploads; 59 % der Gras-Uploadbytes waren semantisch ungenutzte `instanceMatrix`-Daten.
- **Commits seitdem:** `e2b7b68` Subsystem-Frame-Timing + pendingVisible-Fix; `e3d2c37` Grass ohne Matrix-Upload, analytische Bounds, `maxBuildPerFrame=2`, keine unchanged Asset-Matrix/Tint-Reuploads; anschließend Vegetationsexport committed.
- **Bench `ground-streamfix` (nach Upload-Fixes, vor Vegetationsintegration):** ground 57,31 FPS mean / 15,48 1%-low / max 83,6 ms, Dreiecke max 4,177 M, Draws max 292. Subsystem-Timings sind eindeutig: `grassMs` max 1,9 ms, `terrainMs` ~0, `assetsMs` klein, aber `renderMs` max 88,7 ms. Das verbleibende Problem ist Render/GPU-Backpressure bzw. Render-Upload/Pipeline/Draw-Last, nicht mehr der Scatterloop.
- **Gegenmaßnahmen aktuell:** final verbesserte Vegetationsexporte committed (`5b6124c`); Grass-Ferngeometrie ab ca. 25 % statt 44 % der Sichtdistanz committed (`a0a1a4d`); Grass-Shader nutzt namensbasierte Geometry-Attribute statt object-gehashter Slot-Buffer (`6c61cad`, Pipeline-Sharing; visuell noch zu verifizieren); Null-skalige Halme am Fade-Ende werden nicht mehr gezeichnet (`5a72eed`); Tint liegt jetzt als vec4-Geometry-Attribut statt vec3-instanceColor vor (`15c8f35`, vermeidet WebGPU-Full-Capacity-Paddingkopien). Diese Perf-Patches sind getestet, aber noch nicht capture-/bench-verifiziert.
- **Unabhängige Renderanalyse:** die 134 Grass-Slots erzeugen pro Frame weiterhin eigene RenderObjects/BindGroups auch bei geteilter Pipeline. Kurzfristige Hebel: weniger äußere Graslast, weniger Zell-/Mesh-Draws; struktureller Haupthebel ist Sektor-Batching mehrerer Zellen in wenige große Instanzbuffer. vec3-Tint-Padding und writeBuffer-Bursts sind reale, aber kleinere Verstärker.
- **Meshy/Export-Checkpoint:** log_fallen_a, trunk_acacia_b und rock_slab_a sind approved, exportiert und committed; stump_roots_a, trunk_baobab_a und monument_split_disc_a sind nach unabhängigen v2-Reviews rejected. v3-Regeneration läuft mit hartem Zusatzbudget max90 Credits (Ledger-Reserve Pflicht). Capture-Review des Vegetationspilots: Gras technisch Go mit Feinschliff, Vegetationspipeline technischer Go, aber aktuelle Hainintegration No-Go wegen G4-Ancient/Nahstamm, Detailmap-Zuordnung, Reflexionslücke, Farninszenierung und G2/G4-Framing; Korrekturpaket läuft. Wichtiger Perf-Hinweis: alte broadleaf LOD0 haben 30k–60k Tris, neue Fantasy-Bäume nur 2.6k–5.3k — vollständiger Ersatz ist vermutlich ein großer Dreieckshebel.
- **Session-Checkpoint 25.11. spät:** Hain-Pilot committed (`9cbc2a9`); Capture `pilot-veg-grassfix` zeigt keinen offensichtlichen Grass-Tint-/Culling-Bruch, aber G4 ist integrationsseitig problematisch (Ancient-Hero zu nah/blass/facettiert; Art/Scale vor Rollout prüfen). Bench `grassfix-pilot-bench` nach Shader/Culling/Tint weiterhin FAIL: ground 57.61/18.44, max 66.8 ms, 4.096M Tris; flight sauber. Aktuell läuft ein noch UNCOMMITTED Experiment `high grass viewDistance 96→72` in `web/explore/src/main.ts`; zuerst `grass72-check`/Bench auswerten, dann committen oder verwerfen. Meshy v2: log+acacia approved, stump+baobab rejected; rock+monument Review ausstehend.
- **Grass-Sektor-Bench `grass-sector-clean`:** 32-m-Sektor-Batching ist der bisher größte Performance-Durchbruch. Sauberer Bench nach Abschluss aller Edits: ground **59.66 FPS mean / 40.96 1%-low / max 33.5 ms**, flight **59.94 / 59.17 / max 17 ms**, CPU ground nur 5.83 ms. Vorher 16-m-Zellen: ground 57.61/18.44/max66.8. Verbleibend: nur 11 Frames >25 ms, alle als einzelne 33-ms-Verschlucker im frühen Wegabschnitt x357–385; `renderMs` bleibt dabei niedrig, daher wirken sie wie asynchrone GPU-/Framepacing-Restspitzen. Einzige Budgetverletzung ist ground-1%-low 40.96 <45; Dreieckspeak 4.172M bleibt über dem 4M-Richtwert und ist der nächste Hebel durch den Broadleaf-Rollout. Der zuvor katastrophale Lauf `grass-sector-bench` (2–4 FPS) war kontaminiert, weil gleichzeitig ein Subagent noch Grass-Dateien editierte.
- **Broadleaf-Rollout appliziert + Bench `rollout-fantasy-a`:** Der invariant-geprüfte Offline-Applier hat alle 360 count-1-Bäume deterministisch auf oak150/beech112/ancient44/willow54 umgestellt; Seeds, Polygone, Counts, Constraints und Positionen blieben unverändert (`d574559`). Der erste A/B-Bench zeigt den erwarteten großen Geometry-/Speicherhebel: ground-Dreieckspeak **4.172M→2.940M**, flight **2.704M→1.373M**, Textur **1142→1035 MiB**. Flight bleibt perfekt (59.94/59.14/max17.3). Ground ist aber noch nicht bestanden: **59.64 mean / 39.77 1%-low / max exakt 50 ms**. Nur 11 Frames >25 ms, weiterhin früh x358–385. Auffällig: ein Frame hat `renderMs=45.7` bei 250 Draws; vermutlich first-use Pipeline-/Binding-/Upload-Kosten der zusätzlichen Baumarten/Geometrien bzw. ihrer dynamisch erzeugten InstancedMeshes. Der Rollout ist daher geometrisch ein Erfolg, aber das visuelle/perfekte Sign-off braucht noch Warm-up-/Streaming-Härtung.
- **Ground/Flight-Budget bestanden (`grass-prewarm-a`):** Root cause der verbleibenden 33/50-ms-Spikes war Poolwachstum der 32-m-Grasslots während der Fahrt. Die vorab persistent allokierten Warm-up-Slots eliminieren die first-use GPU-Kosten vollständig: ground **59.94 FPS mean / 58.92 1%-low / max 17.4 ms**, flight **59.94 / 58.69 / max 17.4 ms**, CPU 6.79/5.64 ms, Dreieckspeaks **2.940M/1.372M**, Draws max 272/226, Textur 1035 MiB. High-Budget **eingehalten**. Visuell bleibt der Vegetationspilot dagegen NO-GO: Bark/branch geometry, planar foliage, stiff grass, weak fern ecology and insufficient grove massing sind jetzt die Hauptarbeit; Performance ist nicht mehr der primäre Blocker.
- **LOD0-Reflection-Probe `lod0-canopy-reflect`:** Drei abgeleitete Uferposes wurden aufgenommen (`lr-east/lr-row/lr-west`). Ergebnis: keine belastbare positive Reflexionsbestätigung. Die Pilotbäume stehen 60+ m vom offenen See entfernt; Ufer, Gras und vor allem sehr grobe `shrub_round_a`/Bush-Konfettimassen verdecken den Wasserspiegel. `lr-row` ist zusätzlich als Komposition unbrauchbar, weil Strauchkonfetti den ganzen Frame füllt. Der Proxy-Pfad bleibt daher unbewiesen; ein harter Test braucht entweder einen wirklich wassernahen Willow/Tree-Placement oder eine temporäre dedizierte QA-Placementpose. Die Bilder bestätigen außerdem unabhängig die NO-GO-Kritik: breite steife Schwertgrashalme, schwarz-gelbes planar wirkendes Strauchkonfetti und facettierte orange Stämme dominieren die Nahsicht.
- **Meshy-v3 + Pilot-Capture:** v3-Regeneration für stump/baobab/monument committed (`29cd37b`); 87/90 Paket-Credits verbraucht, rework 246/320, total 615/2000. Alle drei sind `blender_review` mit formalen Sheets und warten auf unabhängige Gates; Baobab-Krone breit/flach und Monument-Nahporen sind benannte Restrisiken. Pilot-Captures nach Korrektur: G2 in `pilot-veg-r2`, G4/F3 in `pilot-veg-r2b` erfolgreich; unabhängiger visueller Review läuft.
- **Session-Checkpoint 25.11. nachts:** Pilot-Korrekturen committed (`aeba368`, `3da0a51`): Reflexionsproxy nutzt jetzt den ersten verfügbaren vereinfachten Canopy-LOD statt hart LOD1; Foliage-/Bark-Detailzuordnung ist testabgedeckt; Ancient steht nicht mehr auf der G4-Nahposition, G4 hat eine moderate Eiche, Farnringe sind dichter, G2/G4-Kameras zeigen Stamm+Krone+Boden statt Stammblockade/Himmels-Pitch. Grass-Hygiene committed (`4f4d837`): alle Grasslots teilen eine Materialinstanz und die ungenutzte full-capacity-instanceMatrix ist durch einen 1-Instanz-Dummy ersetzt. Unabhängige Renderanalyse bestätigt: 96→72 m senkt Grasslots/Dreiecke, aber nicht den dominierenden Fixpreis pro Zell-/Mesh-/Upload-Ereignis; 32-m-Sektor-Batching ist der strukturelle nächste Schritt. Meshy-v3-Rohmodelle für stump/baobab/monument sind bereits heruntergeladen (rework 246/320, total 615/2000) und werden gerade blender-seitig aufbereitet.
- **Integration aktuell:** Hain-Pilot gemäß Plan in Arbeit: zuerst 8–15 Bäume + wenige Farnringe um G2/G4, Reflexionsliste erweitern, `slice.json` vier-LOD-Werte, Tests synchron, Captures G2/G4/G1/F2/F3, dann Bench; kein shrub-Massentausch.
- **Visual-Fix-Arbeitsstand nach dem bestandenen Perf-Budget:** Pilot-Unterwuchs im engen G2/G4-Rechteck verwendet jetzt `bush_lush_a` statt `shrub_round_a` (`10ba004`); der Welt-Content-Test wurde auf den vollständigen 360-Baum-Rollout korrigiert. Grassilhouetten sind dünner, gebogener, wurzeln über eine 21-cm-Fläche statt punktuell und mischen Halm-/Instanzvariation (`e3bec57`); 18/18 Grasstests und `tsc` grün. `tools/qa/shot.mjs` unterstützt absolute Kamera-Höhen per `,abs` (`89d1f22`) für echte Wasseroberflächen-Reflexionstests. Parallel laufen noch uncommitted Subagenten-Arbeiten an Baumrinde/Wurzeln/Astenden und an der Foliage-Atlas-/LOD-Pipeline; dadurch ist das Gate vorübergehend erwartungsgemäß rot, bis neue Sheets, Reviews und Exporte abgeschlossen sind.
- **Review-Realität der Visual-Fixes:** Die neue Canopy-LOD-/Alpha-Pipeline ist committed (`40af21e`). Die Baumgeometrie-R7 verbesserte Verankerung/Metriken messbar, aber ein strenges unabhängiges Sheet-Gate rejected weiterhin alle vier Arten wegen plastischem Holz, flachen Leaf-Cards und Wurzelplatten; diese Sheets entstanden zusätzlich vor dem finalen Foliage-Atlas-Stand und sind daher keine Exportfreigabe. Baobab-v4 ist geometrisch deutlich erfolgreich (volumetrisch statt planar, wasserdicht), wurde aber wegen crackled/reptile statt elephant-hide Material rejected; eine creditfreie Materialreparatur läuft. Monument-Materialfix reduzierte Crackle/warme Streifen messbar, wurde aber dennoch rejected u. a. wegen noch prozeduraler Mikrostruktur und unzureichender Sockelverankerung.

---

## Phase 6 / M1 — Checkpoint nach Insel-, Wasser-, Cliff- und Fernsicht-Patch (26.11.2025)

- **Gesicherter Zwischenstand:** Nach dem Insel-/Wasser-Commit `de339d0` wurde ein zentraler Qualitätspatch vorbereitet: G7-Cliffline hangeinwärts eingebettet (`cliff_chalk_corner/wall_a/wall_b`, `rock_pillar_chalk_a`), regelmäßige kohärente Fernwellen stärker räumlich gebrochen und kürzer gefadet, nichtperiodische Windpatch-Normalen für Fernwasser ergänzt, Mineral-/Kristall-Detailmaps verstärkt und ihr Makro-/Mikro-Fade entkoppelt (grobe Mineralstruktur reicht jetzt je nach Klasse ca. 34–140 m statt pauschal nur 22 m), plus erste sehr zurückhaltende Fernvegetations-Mottling-Schicht im Terrainshader.
- **Verifikation grün:** vollständige Explorer-Suite **180/180**, `npm run build` erfolgreich, `python tools/vr.py check` **gate ok: 38 assets checked**, Welt-Content zuvor **53/53**. Captures: `phase6-water-cliff-fix1`, `phase6-detail-wind-fix2`, `phase6-aerial-veg-water-fix3` unter `C:\Users\Mark Waldeis\devin-screenshots\violet-reach\`.
- **Visueller Befund:** F2-Wasser ist deutlich organischer und ohne die alten regelmäßigen Wellenstreifen; die Insel-Scholle bleibt kompositorisch tragfähig. G7 hat keine schwebenden schwarzen Felslücken mehr und wirkt geerdeter. Das ist noch **kein M1-Pass**: G7 bleibt sehr nah/weich, Grassilhouetten wirken sparsam/schwertartig, G6-Säulenoberfläche und flache magenta Kristalle sind unter Zielniveau, F3-Rippenkrone wirkt plastisch, H2-Fernwelt und Fernwasser bleiben zu leer/glatt. Die erste Fernvegetations-Mottling-Schicht ist absichtlich subtil und reicht noch nicht.
- **Performance-Warnung:** unverändert kritischer Headroom bei G7: `3.988.796` Dreiecke / `312` Draws im High-Capture, also fast am 4-Mio.-Richtwert. Keine weiteren sichtbaren Geometriemassen ohne LOD-/Budget-Gegenmaßnahme.
- **Nächste zentrale Schritte:** H2-Fernwelt strukturell statt nur shaderseitig stärken (bestehende prozedurale Forest-Canopy/Makro-AO nutzen oder erweitern), G6-Steinmaterial/Gras-Nahsilhouette reparieren, F3-Kronenmaterial und G5-Framing prüfen, danach erneut vollständige Captures/Bench und erst dann die formale dreifache M1-Abnahme.

### Makro-Fernboden-Checkpoint (unmittelbar danach)

- **Patch:** Die bisher fast nur im Hochgebirge genutzte `macro_color_ao`-Farbkarte wird jetzt distanzgestaffelt auch für ferne Tiefland-/Vegetationsflächen verwendet (`evaluateMacroGroundBlend`, ab ca. 280 m, Maximum bewusst unter 90 %). Dadurch bleibt Nahdetail unverändert, während H1/H2 die bereits gebackene Wald-, Wiesen- und Bodenfärbung statt einer glatten prozeduralen Durchschnittsfläche zeigen.
- **Verifikation:** Explorer-Suite **181/181**, `tsc --noEmit`, Vite-Build und `python tools/vr.py check` (**38/38 Assets**) grün. Targeted Regression `phase6-macro-ground-regression` für G6/G7/F2/F3/H1: keine neue Ufer-, Weg-, Wasser- oder Nahsichtkatastrophe; H2 gegenüber `phase6-aerial-veg-water-fix3` sichtbar strukturierter und weniger leer.
- **Noch offen:** H2/H1 wirken trotz besserer Makrofärbung weiterhin zu sparsam an echter Fernvegetation; die dunklen AO-/Canopy-Flächen sind teils zu weich. G6/G7-Hauptblocker ist jetzt eindeutig die Gras-Nahsilhouette (wenige breite, dunkelgrüne Schwert-Halme auf trockenem/hellem Boden statt dichter Wiesenfilz), gefolgt von plastischem Weißstein/Kristall und der noch zu glatten F3-Rippenkrone.

### Gras-Nahsilhouette Test 1

- **Patch:** gleiche Dreieckskosten, aber niedrigere/stärker gebogene Halme, größere Wurzelstreuung und weniger prozedurale Trocken-/Erddominanz im Bodenlayer. Targeted Capture `phase6-grass-shape-test1` (G6/G7) bei unveränderten Dreieckszahlen: G7 wirkt weniger stachelig und der Bodenanschluss ist grüner; G6 bleibt wegen Ruinen-/Erdgewichtung fast unverändert.
- **Bewertung:** kleiner echter Fortschritt, noch kein M1-Pass. Der nächste Hebel ist nicht noch einmal dieselbe Halmform, sondern die Kopplung aus Wiesengrundfarbe, trockener Makro-Gewichtung und sichtbarer Blattfläche pro Büschel.

### Verworfene Gras-Dichteprobe / Filter-Faktencheck

- **Negativtest:** `density 5.5→6.8` plus früherem Grass-LOD (`0.20×viewDistance`) verbesserte G7 nur moderat, erhöhte den Capture-Peak aber auf **4.047.590 Dreiecke** und wurde daher verworfen; `main.ts` ist wieder exakt auf dem committed Stand.
- **Faktencheck:** Die Terrain-Array-Texturen nutzen bereits `anisotropy = 4`; ein vermeintlich neuer Filterpatch war daher wirkungslos/nicht nötig. Nahbodenglättung ist folglich kein einfacher fehlender-Anisotropie-Bug, sondern weiterhin ein Farb-/Gewichtungs-/Coverage-Problem.

### Gras-/Bodenkopplung Test 4 (Team-Analyse integriert)

- **Patch:** keine Dichte-/Dreieckserhöhung, sondern vier gezielte Kopplungsfixes: weniger prozedurale Hang-Erde/Trockeninseln im Boden, Dry-Mix weniger stark künstlich begrünt (`1.7→1.35`), deutlich reduzierter Halm-interner Wertkontrast (Wurzel `0.40→0.68`, weniger heiße Spitzen/Hashvariation) sowie eine zweistufige Wiesenstruktur aus niedriger breiter Unterfläche und wenigen hohen Akzenten.
- **Verifikation:** Explorer-Suite **181/181**, TypeScript grün. Targeted Capture `phase6-grass-coupling-test4` bei unveränderten Dreieckszahlen (`G7 3.988.796`, `G6 3.758.724`): G3 wirkt erstmals als zusammenhängende saftige Wiese statt Einzelhalme; G7 ist deutlich weniger schwertartig und besser am Boden verankert; G6 bleibt trockener/ruinöser, aber die Halme schneiden sich farblich weniger ab.
- **Bewertung:** erster wirklich großer Gras-Fortschritt ohne Perf-Kosten. Noch offen: G6-Stein/Kristall, G7-Felsintegration, F3-Kronenmaterial und strukturelle Fernvegetation.

### Steinmaterial, Platzierung und Performance-Instrumentierung (Targeted Tests 5–7)

- **Weißstein-/Mineralpatch:** großräumige Albedo-Variation ist jetzt vom kurzen Normalen-Fade entkoppelt (`noiseFadeEndM`, Weißstein bis 520 m), sodass Monumente nicht schon nach ca. 78 m materialmäßig kahl werden. Zusätzlich nutzt `stone_white` die grobe Detailoktave jetzt auch für Rauheit und hue-neutrale Luminanz sowie sparsame vertikale Runoff-Streaks; Kristall-/Mineralwerte bleiben testbegrenzt.
- **Platzierung:** `monument_rib_crown_a` wurde von `y_offset -5.8` auf `-1.6` angehoben, damit Rib-Basis und Podest wieder als Architektur lesbar sind; die drei stehenden `column_white_a` wurden moderat angehoben (`-1.10/-0.66/-1.08`), ohne ihre Ruinenneigung zu verlieren. F3/G6-Captures `phase6-stone-material-test7` zeigen eine deutlich geerdetere Krone und sichtbarere Säulenbasen. Die freiliegende Kronen-Sockelkante bleibt ein benanntes Restrisiko, aber weniger schlimm als das zuvor fast vollständig eingegrabene Podest.
- **QA-Instrumentierung:** `capture.mjs` akzeptiert jetzt `--extra "cascades=2&noreflection=1"`, `shot.mjs` reicht unbekannte QA-Parameter durch, `cascades`/`shadows` sind validierte URL-Overrides, und `window.__vr.stats()` meldet Gras- sowie echte Reflexionspass-Dreiecke/Draws. Die Reflexionsmessung differenziert den Planar-Reflection-Pass innerhalb des Gesamt-Renderings.
- **G7-Isolationsmatrix (`high`, WebGPU):** Baseline `3.988.796` Dreiecke / `312` Draws; zwei statt vier CSM-Kaskaden `2.747.964` / `277` (**−1.240.832 Dreiecke**); null Kaskaden `1.618.172` / `231`; ohne Wasserreflexion `3.610.849` / `250` (**−377.947**); ohne Gras `3.722.462` / `300` (**−266.334**). Damit ist die Schattenpass-Amplifikation der dominante Hebel, nicht Gras.
- **Qualitätsentscheidung:** G7 ist zwischen vier und zwei Kaskaden nahezu pixelgleich (`mean Diff 0,229`, nur `0,74 %` Pixel über Schwelle 8); F3 ist praktisch pixelidentisch (`max Diff 2`, `0 %` über Schwelle) und spart dennoch `368k` Dreiecke. `quality.high` nutzt daher jetzt zwei statt vier Kaskaden bei unverändertem 2048er-Shadowmap; `ultra` bleibt bei vier. Dies ist ein gemessener dreieckskostenfreier Qualitätsgewinn, keine visuelle Verschlechterung.
- **Verifikation:** Explorer-Suite **182/182**, TypeScript/Vite-Build und `python tools/vr.py check` (**38/38 Assets**) grün. Verbleibende M1-Hauptblocker: strukturelle H1/H2-Fernvegetation, G6-Kristalle/Nahsteinfeinschliff, G5-Framing und anschließend die formale dreifache Abnahme.


### Strukturelle H1/H2-Makro-Vegetation Test 4

- **Patch:** `tools/world/build_macromap.py` baut die bisher fast verwaschene prozedurale Fernwald-Belegung als echte 4k-Kronenstruktur mit nicht-nuller Waldgrundbelegung und klar geformten Lichtungen; offene Wiesen erhalten eine feuchte-/gewichtungskorrelierte 15/38-m-Tussock-Struktur, und signifikante Canopy-Belegung wird nicht mehr nur als beschatteter Boden, sondern als hue-sichere Blattdach-Albedo in `macro_color_ao` gebacken. Im Terrainshader übernimmt `macro_color_ao` das Tiefland jetzt etwas früher/stärker (`280..1050 m`, Stärke `0.82`), während das zusätzliche decorrelierte prozedurale Canopy-Mottling von `0.48` auf `0.28` reduziert wurde.
- **Iterative Bildprüfung:** `phase6-macro-veg-test1/2` zeigten, dass die erste Bake zwar Daten enthielt, aber im Tiefland noch zu schwach übernommen wurde; `test3/4` mit verstärkter Wiesenstruktur und Canopy-Albedo zeigen in H2 erstmals breitere zusammenhängende dunkle Vegetations-/Waldflächen im Vorder- und Talhintergrund. H1 bleibt konservativ und ohne Cow-Spot-/Rauschartefakt; die Verbesserung ist moderat, aber strukturell echt.
- **Regression:** `phase6-macro-veg-regression1` (G3/G6) zeigt keine Nahwiesen- oder Bodenverschlechterung durch die neue `macro_grass`/Farb-Bake. G3 bleibt eine zusammenhängende saftige Wiese; G6 behält seinen trockeneren Ruinencharakter. Die dort sichtbaren plastischen Kristalle/Weißsteinflächen sind unverändert separate M1-Blocker.
- **Verifikation:** Explorer-Suite **182/182**, TypeScript/Vite-Build und `python tools/vr.py check` (**38/38 Assets**) grün. Capture-Dreieckszahlen bleiben unverändert (`H1 1.633.923`, `H2 980.825`, `G3 2.609.069`, `G6 2.764.136` bei zwei High-Kaskaden).
- **Noch offen:** H2 ist besser, aber noch kein finaler M1-Pass — die Fernwelt braucht vermutlich zusätzlich eine geometrische/impostor-artige Baumkronen-Silhouette oder eine deutlich glaubwürdigere Wald-/Wiesen-Makroästhetik. Separat entdeckt und noch nicht in diesem Patch behandelt: die channel-gepackten RGBA-WebP-Gewichtskarten müssen auf Alpha-/RGB-Verluste durch verlustbehaftete WebP-Kodierung geprüft und ggf. exakt/verlustfrei gespeichert werden.

### G5-Framing-Korrektur

- **Patch:** reine QA-Kamera-Korrektur in `world/bookmarks.json` von `(556,1536,yaw1.32)` zum nassen Uferpunkt `(550,1540,yaw1.10)`. Die erste östlichere Testpose `(580,1542)` verschlechterte die Überlappung; die geometrische Auswertung zeigte, dass der südlliche Uferpunkt bei gleicher Torentfernung ca. 41 m die Winkeltrennung Tor/Brücke auf fast 20° erhöht.
- **Bildbefund:** `phase6-g5-framing-test2` erfüllt die Lesezeichenbeschreibung deutlich besser: Seefläche und Schilf links, Brücke frei lesbar in der Mitte, Tor rechts als großer begrenzender Rahmen statt zentraler Bildblockade. `phase6-g5-framing-test1` und das Vorherbild bleiben als verworfene Vergleichsaufnahmen dokumentiert.
- **Verifikation:** gezielte QA-/Bookmark-Tests **10/10** grün; keine Welt- oder Asset-Geometrie verändert.

### Exakte channel-gepackte Makro-Daten-WebPs

- **Befund:** `macro_weights_a/b` und `macro_grass` sind keine normale Bild-/Alpha-Textur, sondern channel-gepackte Daten. Die bisherige lossy-WebP-Kodierung behandelte den vierten Kanal als Transparenz; über weiten Bereichen mit legitimem `moss/strata = 0` wurden die bedeutungstragenden RGB-Gewichte verworfen oder stark quantisiert. Empirisch lagen einzelne Kanalfehler bis `255/255`, die Layergewichtssumme fiel stellenweise auf `.01` (statt `1.0`), und z. B. am G5-Ufer wurde `wet_shore` praktisch zu `0` verfälscht.
- **Patch:** `tools/world/build_macromap.py` speichert die drei Datenkarten jetzt mit Pillow-WebP `lossless=True, exact=True`; nur `macro_color_ao` bleibt eine normale visuelle lossy WebP. Die erzeugten Datenkarten sind größer (`weights_a 3502KB`, `weights_b 2089KB`, `grass 6843KB`), aber weiterhin deutlich kleiner als PNG-Äquivalente. `tools/world/test_build_macromap.py` prüft jetzt byte-exakte RGBA-Roundtrips bei null im vierten Kanal sowie die normalisierte Layergewichtssumme nach Decoding.
- **Messung nach Fix:** Layergewichtssumme mean `.999987`, p1/p5 `.996078`, p95/p99 `1.00392`, `0 %` unter `.8`; alle Stichproben liegen innerhalb `.98–1.02` (u. a. G3 `.996`, G5-Ufer `1.0`, G6 `1.0`). Gegenüber den committed lossy Daten sind die durchschnittlichen absoluten Kanaländerungen `weights_a 12.17/255`, `weights_b 4.67/255`, `grass 4.01/255` mit Maxima bis `255`.
- **Visuelle Regression:** Targeted Capture `phase6-macro-exact-test1` (G3/G5/H2) zeigt keine neue Artefaktbildung. H2 ist gegenüber `phase6-macro-veg-test4` praktisch unverändert (`pct>8 = 0`); G3/G5 bleiben sicher im normalen Bewegungs-/Samplingrauschen. Der Fix ist damit primär Datenkorrektheit und keine sofortige große Bildänderung.
- **Verifikation:** `python tools/world/test_build_macromap.py` grün, Explorer-Suite **182/182**, TypeScript/Vite-Build grün, `python tools/vr.py check` **38/38**. Capture-Dreieckszahlen: G3 `2.612.351` / 275 Draws, G5 `1.816.065` / 248, H2 `980.825` / 122.

### Exakte Browser-Decodierung der Gras-Makrodaten

- **Befund:** Nach der exakten WebP-Dateikodierung blieb eine zweite Datenlücke im CPU-GrasSampler: `macro_grass`/`macro_color_ao` wurden über 2D-Canvas decodiert, wobei Browser RGBA implizit premultiplizieren/quantaisieren können. Die Alphakanäle sind jedoch Daten (`canopy_shadow`, `AO`), keine Transparenz.
- **Patch:** `web/explore/src/grass-macro.ts` decodiert beide Makrokarten jetzt über `createImageBitmap(..., premultiplyAlpha:"none")` plus WebGL2-Framebuffer/`readPixels` mit deaktivierter Premultiplication. Die top-first-Zeilenorientierung wurde vor Übernahme in echtem Chrome empirisch geprüft.
- **Canary:** In Chrome wurden 28 deterministische/low-alpha-Stichproben aus `macro_grass` und 28 aus `macro_color_ao` gegen Pillow-Referenzbytes verglichen: **56/56 exakt, maximaler Kanalfehler 0**.
- **Verifikation:** Explorer-Suite **182/182**, TypeScript/Vite-Build grün, Asset-Gate **38/38**. Zwei Capture-Versuche (`phase6-macro-decode-test1/2`) mussten als Infrastrukturfehlversuche verworfen werden, weil der wiederverwendete Vite-Prüfserver durch den parallelen Produktionsbuild bzw. hängende Chrome-Instanzen vor der ersten fertigen Aufnahme einfror; die App selbst erreichte in der Diagnose den Terrainlader und zeigte keinen Decode-Fehler. Eine visuelle Regression ist deshalb weiterhin vor der finalen M1-Abnahme nachzuholen.

### Makro-Decode-Regression und QA-Server-Factcheck

- **Nachgeholte Regression:** `phase6-macro-decode-test5` (G3/G5/G6, high, WebGPU AMD) ist nach sauberem Serverstart erfolgreich. G3/G5 sind gegenüber `phase6-macro-exact-test1` praktisch unverändert (`G3 mean 0.286/p95 1`, `G5 mean 0.0087/p95 0`); G6 zeigt gegenüber der älteren Vor-Exact-Baseline nur eine moderate, lokal erwartete Grasverteilungsänderung (`mean 0.753`, `pct>8 1.34 %`) ohne neue Artefakte. Die korrigierte CPU-Decodierung ist damit visuell sicher.
- **Infrastruktur-Factcheck:** die vorherigen Capture-Hänger waren keine Decode-/Terrainregression. Der manuell gestartete Vite-Server fehlte mit `VR_GATE_CACHE_MS`; dadurch führte die World-Content-Middleware bei jeder Terrain-/Asset-Anfrage synchron `vr.py check` aus (132 KB in ca. 11 s, große Makrodateien in Timeouts). Mit von `capture.mjs` selbst gestartetem Server läuft jede Aufnahme reproduzierbar in ca. 90 s. Dieser Prozessfakt ist jetzt zusätzlich in `AGENTS.md` festgehalten.

### Offline-Pilot für volumetrische Fernvegetation

- **Generator:** `tools/world/build_farveg.py` erzeugt deterministisch sparsame Fernkronen-Instanzen für die volle 8×8-km-Welt außerhalb des handgepflegten 1×1-km-Spielslices. Die Verteilung benutzt denselben nun in `forest_macro_density` geteilten Makro-Wald Noise wie die Makro-Bake, volle R16-Höhen/Slope, analytische Hydrologie, Pfad-/Monumentclearance, Slice-Kernausschluss plus 120-m-Dichtarampe und variables Poisson-artiges Thinning.
- **Pilotmessung:** 3257 Instanzen, 409543 Bytes JSON, Varianten Oak/Beech/Willow/Ancient `1346/1422/315/174`; harte Ausschlüsse und Spacing sind synthetisch sowie an realer Welt geprüft. Keine Instanz im Slice-Kern; nächster Slice-Abstand ca. 52 m innerhalb der dokumentierten weichen Übergangsrampe. Lagebild: `farveg-pilot-map.png` im Projekt-Screenshot-Ordner.
- **Verifikation:** `test_build_farveg.py` **12/12**, `test_build_macromap.py` grün, `test_world.py` **WORLD OK**. Der Generator ist bewusst write-opt-in (`--out` oder `--dry-run`) und hat noch keinen produktiven Runtime-Output geschrieben.
- **Nächster Schritt:** sektorisiertes/instanziiertes Runtime-System auf Basis der bereits freigegebenen LOD3-Kronen der vier Laubbaum-Assets, ohne Schatten- und ohne Reflexionspass.

### Runtime-Pilot volumetrische Fernvegetation / erster produktiver `farveg.json`

- **Runtime:** `web/explore/src/far-vegetation.ts` lädt das versionierte `farveg.json` und rendert die vier freigegebenen Baumvarianten ausschließlich als exakte LOD3-Instanzen. Pro Variante werden Bark- und Canopy-Primitives zu statischen `InstancedMesh`-Batches kompaktiert; CPU-Culling läuft alle 100 ms über 256-m-Sektoren plus Einzelsphären. Es gibt bewusst keine Schatten, keine Reflexionslayer, keine pro-Instanz-LOD-Kaskade und keine Placeholder-Billboards. Bark entfällt zusätzlich jenseits von 1400 m.
- **Korrektheit nach Review:** exakt LOD3 wird erzwungen statt stillschweigend das höchste LOD zu nehmen; Chunk-Padding berücksichtigt jetzt den Bounding-Sphere-Mittelpunkt; die Upload-Signatur enthält die Bark/Canopy-Zuordnung; `farveg.update` läuft erst nach `nav.update`. `tools/qa/capture.mjs`/`shot.mjs` melden Farveg-Dreiecke und sichtbare Instanzen explizit.
- **Gemeinsamer GLB-Cache:** `web/explore/src/asset-gltf.ts` teilt dieselben geparsten GLB-/KTX2-Ressourcen zwischen normalen Slice-Assets und Fernvegetation. Dadurch fiel der zuvor im Piloten gemessene Texturzuwachs von ca. 61,5 MB vollständig weg: `phase6-farveg-regression1` meldet in G3/H1/H2 wieder exakt `textureBytes = 1.253.220.537`, denselben Wert wie die Vorbaseline.
- **Produktive Daten:** nach Treeline-/Lowland-Retune enthält `web/explore/public/farveg/farveg.json` **4081** deterministische Instanzen (`511244` Bytes), Varianten Oak/Beech/Willow/Ancient `1659/1754/498/170`. Alpine Einzelbäume oberhalb der Waldgrenze wurden entfernt; die offene Tiefland-/Savannenstruktur wurde gegenüber dem ersten 3096-Instanzen-Retune nochmals verdichtet.
- **Echte WebGPU-Regression `phase6-farveg-regression1`:** H2 `1.070.449` Dreiecke / `130` Draws, davon Farveg `737` sichtbare Instanzen / `89.624` Dreiecke / `8` Draws. H1 `1.744.117` / `219`, davon Farveg `929` Instanzen / `110.194` Dreiecke / `7` Draws. G3 `2.743.760` / `283`, davon Farveg `1091` Instanzen / `130.623` Dreiecke / `8` Draws. Gegenüber den zuletzt dokumentierten Baselines sind das etwa **+130k in G3**, **+110k in H1** und **+89,6k in H2** bei maximal **+8 Draws** und ohne zusätzliche Schatten-/Reflexionspässe.
- **Visueller Befund:** H1/H2 zeigen erstmals echte volumetrische Fernkronen und kleine Haine statt nur gebackener Bodenfarbe; H1 zeigt keinen harten rechteckigen Slice-Rand. Die Kronen sind jedoch noch zu hell/entrückt gegenüber der dunkleren Makro-Vegetation und H2 erreicht noch nicht das ursprüngliche +200k-Ziel. Das Slice-Rand-Nahproblem grober LOD3-Kronen bleibt ein benanntes Risiko; eine spätere LOD3-only-Asset-Pipeline oder Übergangs-LOD ist noch offen.
- **Verifikation:** `test_build_farveg.py` **13/13**, Explorer-Suite **185/185**, TypeScript/Vite-Build und Asset-Gate **38/38** grün. Der Pilot ist ein legitimer M1-Fortschritt, aber noch nicht die endgültige Fernwelt-Abnahme.

### Farveg-Materialintegration und zweite Dichteabstimmung

- **Befund:** der erste Runtime-Pilot zeigte echte Fernkronen, aber sie wirkten in H1/H2 zu hell und „aufgemalt“. Unabhängiger Review wies nach, dass die Baumkronen eine konstante emissive Translucency-Basis von ca. `0.22` besitzen; reine diffuse Instanz-Tints können diese Selbstaufhellung nicht vollständig kompensieren.
- **Patch:** `FarVegetation` klont nur die Canopy-Materialien für die Ferninstanzen und reduziert deren Emission auf `45%`; die gemeinsam gecachten GLB-Materialien der handplatzierten Nahbäume bleiben unverändert. Zusätzlich ist die Fernkrone diffuser abgedunkelt (`canopyBrightness 0.72`) und die zufällige Tintvariation von `0.09` auf `0.06` reduziert. Bark bleibt neutral getintet. Der reine Helligkeitstest `phase6-farveg-brightness-test1` und die materielle Probe `phase6-farveg-material-test1` zeigen die erwartete Integration ohne Kostenänderung.
- **Dichte/Scale:** die produktive `farveg.json` wurde auf **5078 Instanzen** (`635345` Bytes) retunt: größere Kronen-Skalierung (ca. +10–15%) und dichtere Waldkerne/Edges (`24–40 m`/`40–65 m`), während die offene Savanne bei sparsamen 120-m-Akzenten bleibt. Alpine Treeline- und Wasser-/Pfadausschlüsse bleiben aktiv.
- **Messung `phase6-farveg-density-test1`:** H1 `1.776.452` Dreiecke/`219` Draws, davon Farveg `1196` sichtbare Instanzen/`142.529` Dreiecke/`7` Draws; H2 `1.096.507`/`130`, davon Farveg `948`/`115.682`/`8`. `textureBytes` bleibt exakt `1.253.220.537` dank gemeinsamem GLB-Cache. Visuell sind H1/H2 deutlich weniger leer; die Kronen wirken dunkler und besser eingebettet. H2 bleibt bewusst eine offene Savannen-/Parklandschaft und nicht geschlossener Wald.
- **Bodenregression:** `phase6-farveg-density-regression1` zeigt in G3 keine neue Artefaktbildung; die zusätzlichen Fernkronen bleiben im Hintergrund eine moderate Bereicherung. G3 liegt bei `2.777.395` Dreiecken/`283` Draws, davon Farveg etwa `166k` — mehr als der erste Pilot, aber weiterhin ohne zusätzliche Passes und innerhalb des bisherigen Nahbudgets.
- **Verifikation:** `test_build_farveg.py` **13/13**, Explorer-Suite **186/186**, TypeScript/Vite-Build und Asset-Gate **38/38** grün.

### G6-Kristallmaterial und Basisfreilegung

- **Befund:** die drei Säulen-Kristalle waren so tief eingesenkt (`-1.40/-1.05/-1.55 m`), dass Felssockel, kleine Nebenkristalle und dunkle Kernbereiche im Bookmark praktisch unsichtbar waren. Gleichzeitig überdeckte der fast weiße gebackene Emissionsfaktor die diffuse Facetten- und Rauheitsantwort; das erzeugte die plastische, gleichmäßig neon-violette Fläche.
- **Patch:** die drei Cluster sitzen jetzt bei `-0.55/-0.35/-0.75 m` und bleiben damit partiell eingebettet, zeigen aber wieder ihren pale rock base und die kleineren side shards. Runtime-seitig werden Kristalle auch dann als `MeshPhysicalNodeMaterial` gepatcht, wenn der GLB-Export sie zu einem Standardmaterial abgeflacht hat; Clearcoat/IOR werden nur ergänzt, wenn keine authored Werte vorhanden sind. Die Emission wird auf **18%** reduziert, ohne die Originalmaterialien im gemeinsamen GLB-Cache zu mutieren.
- **Bildverifikation:** `phase6-crystal-material-test3` (G6, high, WebGPU AMD) zeigt sichtbar geerdete Cluster mit freiliegendem Sockel und kleineren Nebenkristallen. Im violetten Kristallbereich sinkt die mittlere RGB von etwa `(139,61,199)` auf `(107,52,156)`, während die Luminanzvarianz von `18.9` auf `31.3` steigt — also weniger flächiges Eigenleuchten und mehr Facettenstruktur. Die Kosten bleiben unverändert bei `2.890.201` Dreiecken/`225` Draws.
- **Negativtest:** eine zusätzliche großräumige Kristall-Luminanznoise (`1.4 m`, Amplitude `0.080`) war selbst nach korrekter Anwendung praktisch unsichtbar (`max Diff 4`, keine Pixel über Schwelle 8 gegenüber Test 3) und wurde verworfen. Ebenso wurde der erste zu schwache per-Asset-Crown-Detailprobe-Patch aus der Arbeitskopie entfernt; F3-Kronenmaterial und Sockelkante bleiben offene M1-Blocker.
- **Verifikation:** Explorer-Suite **187/187**, TypeScript/Vite-Build und Asset-Gate **38/38** grün. Fokussierte Detail-/Welt-Tests decken die physical-clone/emission-Regel und die neue teilweise Burial-Spanne ab.
