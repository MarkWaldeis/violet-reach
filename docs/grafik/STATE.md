# Grafik-Stand (GRAFIK_PLAN.md)

Diese Datei reicht, damit eine neue Session nahtlos weitermacht. Nach jedem Arbeitspaket aktualisieren.

## Aktuell

- Zweig: `grafik/next-level` — letzter Commit **`b0b5494`** "Phase 2 p2-r16 rendering work + Phase 4.1 GPU grass foundation"
- Phase: **Phase 2 fast abgeschlossen** — Rendering von Antigravity reviewt, verifiziert und committed; Bench p2-r16 bestanden. **Phase 4.1 GPU-Gras Fundament implementiert** (noch nicht visuell verifiziert!).
- Verifikation: **89/89 Explorer-Tests grün** (84 alt + 5 Gras), `tsc --noEmit` sauber, `vr.py check` grün (34 Assets).
- Bench p2-r16 (sauberer Lauf, unbeladene Maschine): ground 59,79 FPS mean / 47,71 1%-low, flight 59,94 / 59,48, 0 Budget-Verletzungen, max 245 Draws, 896 MiB Textur. Der ursprüngliche r16-Fail (29er 1%-lows) war Load-Rauschen paralleler Blender-Jobs.
- Meshy-Kostenbuch: **369 / 2000 Credits** verbraucht (Antigravity +228 für 10 Klasse-B-Modelle, 2 Bilder, 2 Klasse-A-Multiview), Kontostand 2791. Stopp bei 1800.
- **Neue Regel von Mark (ersetzt die Spar-Regel in MESHY.md):** Bildgenerierung wieder über Meshy erlaubt (nicht mehr zwingend lokal/Grok); Bäume/Gras/Wasser/AAA-Assets kommen bevorzugt aus dem Fantasy-open-world-Projekt (siehe `docs/grafik/FANTASY_OPEN_WORLD_REUSE.md`), Meshy-Credits bleiben für andere wichtige Assets.

- **Erkenntnis Ladezeiten:** die App braucht in dieser Umgebung 2–4 min bis `__vr.ready` (Wasserstufe allein ~90 s — `surfaceData` lädt viele Höhenkacheln; kein Deadlock!). Smoke-Tests brauchen Timeout ≥ 300 s. Dev-Server für QA immer mit `VR_GATE_CACHE_MS=30000 npm run dev` starten, sonst serialisiert der Gate-Check jede Kachel-Anfrage (~1 s × 256 Kacheln). Dev-Server nach größeren Edits/Gate-Flips neu starten — HMR-Zustand kann korrupt sein.
- **Tree-Import abgeschlossen (Subagent):** 6 Fantasy-Bäume in `blender_review` (tree_oak/beech/ancient/willow, bush_lush, fern_lush), Export-Smoke-Test Oak ≈ 2,29 MB vs ~17 MB alte broadleaf — klarer Ersatz für Massenbewuchs. Offene Pipeline-Punkte: Canopy-LOD fehlt für meshy_class B (export_asset.py:244), exakt duplizierte Faces in Templates (4–8 je Baum), KTX2-Initialpfad nutzt ETC1S statt UASTC für Vegetation. Diese Assets + die 4 von Builder-a (scree/shore/arch/monument) brauchen noch unabhängige Gate-Reviews.

### Offene Arbeiten (in dieser Reihenfolge)

1. **Gras visuell verifizieren & iterieren** (höchste Priorität): Das GPU-Gras-System (`web/explore/src/grass-*.ts`) ist implementiert und ungetestet im Browser — zum Sessionende war die Maschine durch parallele Blender-Jobs der Builder-Subagenten zu stark gesättigt für das Laden der App. Vorgehen: Dev-Server (`npm run dev` in `web/explore`), Playwright mit `channel: "chrome"`, URL `http://localhost:5173/?cam=460,2.2,1560,0.5,-0.12&agl=1&freeze=1`, warten bis `window.__vr.ready` (kann 1–3 min dauern!), Screenshot. Prüfen: sichtbare Halme in Bodennähe, Farbanschluss ans Gelände, keine Shader-Fehler in der Konsole, Wind nur bei `freeze=0`. Danach Dichte/Farbe/Höhe feinjustieren (`grass-material.ts`, `main.ts` quality-Tabelle). **Achtung HMR:** captures/benches NIEMALS parallel zu Code-Edits laufen lassen — vite-HMR lädt Seiten neu und kontaminiert Läufe (p2-r16-Capture dadurch unbrauchbar geworden).
2. **Builder-Subagenten-Ergebnisse ernten:** Zwei Subagenten (SWE max) haben gearbeitet: (a) Assets `trunk_acacia_b`, `trunk_baobab_a`, `log_fallen_a`, `stump_roots_a` u.a. durch Blender-Pipeline bringen; (b) 6 Fantasy-open-world-Bäume importieren (`tree_oak_a`, `tree_beech_a`, `tree_ancient_a`, `tree_willow_a`, `bush_lush_a`, `fern_lush_a` — Ordner existieren schon, uncommitted!). Status prüfen, fertige Assets durch unabhängiges Gate-Review schicken, dann committen.
3. **Abgelehnte Assets reparieren:** Gate-Review `devin-gate-rev-a` hat alle 6 geprüften Assets abgelehnt (Reviews in den jeweiligen `asset.json`): systemische Meshy-Defekte — papierdünne Schalen, schwarze Löcher, abgeschnittene Rohr-Astenden, repetitive Rinde. Entweder Blender-Reparatur in `vrmeshy.py` verstärken oder innerhalb des Retry-Budgets regenerieren.
4. **Capture-Lauf p2-r16 NEU fahren** (alter Lauf durch HMR kontaminiert, G1–G7/F1 evtl. noch valide in `devin-screenshotsiolet-reach\p2-r16\`): `node tools/qa/capture.mjs --run p2-r16` + `bench.mjs`, aber erst NACH Gras-Stabilisierung, sonst doppelt Arbeit.
5. **3 blinde Reviews** der finalen Lesezeichen (G1, G5, F1, F2, H1 >= 8) -> Phase-2-Sign-off.
6. **Danach:** genehmigte Assets exportieren + platzieren, Fantasy-Bäume gegen alte broadleaf-Bäume tauschen, Gras alte `grass_tuft_a`-Instanzen ersetzen oder ergänzen (A/B-Vergleich), Phasen 5-6.

### Gras-System Architektur (Phase 4.1, committed, unverifiziert)

- `grass-macro.ts`: CPU-Sampler, bilinear, liest DIESELBEN `macro_grass.webp`/`macro_color_ao.webp` wie der Boden-Shader (perfekter Farb-/Dichteanschluss). Kanäle: Dichte/Höhe/Dry/Canopy + Tint/AO.
- `grass-clump.ts`: prozedurale Büschel, 6 Halme à 3 Tris (spitz zulaufend, 5 Verts), uv.y=Höhenfraktion, color.r=Blatt-Hash, color.g=Flex.
- `grass-material.ts`: TSL, Fantasy-Blueprint — 3-Komponenten-Wind (wave/gust/flutter, h²-gewichtet, worldTime-fähig/freeze-sicher), Width-Boost in der Mitte, Distance-Fade, Wurzel-zu-Spitze-Gradient, macro-gekoppelte Tönung pro Instanz, warmes Backlight. Instanz-Attribute: `aInfo`(xyz Welt+Hash), `aShade`(canopy,dry,heightScale,widthMul), `instanceColor`(tint).
- `grass-system.ts`: Ring-Streaming 16-m-Zellen, 1 Zelle Build-Budget/Frame, reine Translations-Instanzmatrizen (Wind bleibt weltkohärent), kein Shadow-Casting, receiveShadow ja.
- `main.ts`: Qualitätsstufen low/medium/high/ultra = 44m/2.6, 68m/4.0, 96m/5.5, 128m/6.5 (Sichtweite/Dichte pro m²). Deaktivierbar mit `?nograss`.
- Offene Designfrage: LOD/fade-pop an Zellgrenzen prüfen; Perf-Budget: Grundstrecke hatte nur 47,71 FPS 1%-low — Grass muss sparsam bleiben, ggf. Dichte senken oder alte Tufts entfernen.

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
