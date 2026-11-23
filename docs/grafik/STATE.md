# Grafik-Stand (GRAFIK_PLAN.md)

Diese Datei reicht, damit eine neue Session nahtlos weitermacht. Nach jedem Arbeitspaket aktualisieren.

## Aktuell

- Zweig: `grafik/next-level` (von `main` @ 0fff854)
- Phase: **Phase 1 abgeschlossen** (`p1-r7`, 3 unabhängige Prüfer: `himmel` Median **7–8** auf allen 10 großen Himmels-Lesezeichen, `G2`/`G6` `licht = 8`, `0` Budget-Verstöße bei **537 MiB** GPU-Texturspeicher nach KTX2-Umbau `df87c8f`). Verbleibende `licht`-Abzüge (`G3, G5, G7, F3, H1`) hängen direkt an den noch unfertigen Legacy-Materialien für Boden/Sand/Wasser und werden in **Phase 2** behoben.
- Arbeitspaket: P0 (`p0-baseline`), KTX2-Loader/Repack (`df87c8f`), 3 Blender-Gate Pilot-Assets (`3d780fb`), Makrokarte (`build_macromap.py` + `macro*.webp`) und **Phase 1** (`atmosphere.ts`, `sky-bodies.ts`, `post-processing.ts`, `scene-warmup.ts`) abgeschlossen.
- Nächster Schritt:
  1. Makrokarte + `check_image.py` committen und unfertigen Vegetations-Entwurf (`tools/vegetation/`, `web/explore/public/vegetation/`) entfernen.
  2. **Phase 3 Pilot In-Game-Verifikation:** `detail-maps.ts` + Hook in `instance-assets.ts` umsetzen, die 3 Pilot-Assets (`boulder_chalk_a`, `ruin_wall_a`, `trunk_acacia_a`) im Ausschnitt platzieren und via `p3-pilot` prüfen (`≥ 8`).
  3. **Phase 2:** PBR-Boden (`ground-material.ts` mit 9 Schichten, Makrokarte & Triplanar-Klippen ab 35°) und Tiefen-/Glanzwasser (`water.ts` inkl. `G1`-Brückenkanal) umsetzen und verifizieren.

## Meshy

- Bibliothek: `C:\Users\Mark Waldeis\Desktop\Violet Reach Meshy\` (`ledger.csv`, `queue.json`, README)
- Verbraucht laut Kostenbuch: **141 / 2000 Credits** (Posten Pilot/Kalibrierung: 141 / 150; Stopp bei 1800). Kontostand am 22.11. nach Pilot: **3019 Credits** (Start: 3160).
- Kalibrierung dokumentiert in `docs/grafik/MESHY.md`:
  - `gpt-image-2-5-flare` (9 Cr.) schlug `nano-banana-2-lite` (3 Cr.) mit 3/3 vs. 1/3 bestandenen Vorlagen.
  - **Neue Spar-Regel von Mark:** Für zukünftige Referenzbilder (`image/chosen.png`) darf die eigene Bildgenerierung (`image-generator` / Grok) + lokale Freistellung genutzt werden (0 Meshy-Credits fürs Bild), damit Meshy-Credits rein für `image-to-3d` / `multi-image-to-3d` gespart werden.
  - Klasse B (`smart-topology`, 15 Cr., LOD0 direkt aus aufgeräumtem Meshy-Netz + UVs ohne Neu-Bake) ist aus 3 m Entfernung (`boulder_chalk_a/model_qa/compare.jpg`) zusammen mit Detailtextur (`rock_chalk`) von Klasse A (30 Cr.) kaum zu unterscheiden → Klasse B für alle Requisiten, Klasse A nur für Hero-Monumente und große Klippen.
  - Regel von Mark: Meshy-Rohmodelle werden immer erst in Blender mit `vrmeshy.py` fürs Spiel aufbereitet (`load_raw`, `drop_loose`, `normalize`, `delight_basecolor`, `grade_basecolor`, `clamp_material`, `burial_skirt`, `fix_normals`, bei Bäumen Laubkrone in Blender, LODs, Gate-Review).

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
