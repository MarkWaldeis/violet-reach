# Grafik-Stand (GRAFIK_PLAN.md)

Diese Datei reicht, damit eine neue Session nahtlos weitermacht. Nach jedem Arbeitspaket aktualisieren.

## Aktuell

- Zweig: `grafik/next-level` (von `main` @ 0fff854)
- Phase: 0 abgeschlossen (Nulllinie aufgenommen, gemessen und von 3 unabhängigen Prüfern benotet); Übergang zu Phase 1 (Licht, Himmel, Bildaufbereitung), Phase 2 (Boden, Fels am Hang, Wasser) und Phase 3 (3 Pilot-Assets in Blender aufbereiten & durchs Gate bringen)
- Arbeitspaket: P0 fertig (`p0-baseline`), Vorarbeiten für P1/P2 (PBR-Bodentexturen, Detailtexturen, Wolken- & Wasser-Bakes) und P3 (`vrmeshy.py`, `inspect_raw.py`, `docs/grafik/MESHY.md`, 3 Pilot-Rohmodelle) abgeschlossen
- Nächster Schritt:
  1. Phase 1 umsetzen (`atmosphere.ts`, `main.ts`: Himmelsverlauf, Wolkenebenen, Planeten/Monde, Umgebungslicht/PMREM aus Himmel, 4 CSM-Kaskaden, Luftperspektive statt 82-%-Beigeschleier, Post-Processing mit GTAO/Bloom/Godrays/Farbkorrektur, Tonemapping-Messung AgX vs. Neutral vs. ACES).
  2. Parallel die 3 Pilot-Assets (`boulder_chalk_a`, `trunk_acacia_a`, `ruin_wall_a`) mit `vrmeshy.py` in Blender aufbereiten, durch das Tor (`vr.py sheet` → unabhängiger Prüfer → `vr.py export`) bringen und im Ausschnitt platzieren.

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

## Offene Mängel (Top 5 der Prüfer aus der Nulllinie)

1. **Flaues, kontrastarmes Licht und dichter 82-%-Beigeschleier ohne Post-Processing** (alle 13 Lesezeichen; Kontrast in H1 0,284 vs. 0,617, F3 0,340 vs. 0,581, G1 0,395 vs. 0,673): AgX ohne Grading entsättigt, Hemisphärenlicht (1,9) wäscht Schatten aus (`luma_p5` ~0,30 statt <0,10), kein GTAO/Bloom/Godrays, kein Umgebungslicht aus der Himmelsszene → **Phase 1**.
2. **Prozeduraler Einheitsboden mit Treppenstufen an Hängen und Detail-Abbruch ab 30 m** (G1, G3, G7, F1, F4, H1, H2): Sägezahn-Artefakte entlang der Grün-Beige-Hangschwelle auf dem 2-m-Raster, fehlende KTX2/PBR-Bodenschichten, fehlende 4096²-Welt-Makrokarte und fehlende Triplanar-Felsprojektion ab 35° → **Phase 2**.
3. **Opakes, graublaues Wasser ohne Tiefendurchsicht, Uferschaum, nassen Saum und Spiegelung** sowie isoliertes Wasserloch unter der Brücke in G1 → **Phase 2**.
4. **Massiver Vegetationsmangel und grobe Alt-Bäume mit hervorstehendem Wurzelkragen** (G1–G4, F3, H2): Gras endet nach 20 m (Grünanteil G1 14,6 % statt 62,8 %), brauner Polygon-Kragen ragt in G4 scharfkantig aus dem Hang, flache Laubkarten ohne Durchlicht, 0 Bäume/Impostors außerhalb des Ausschnitts → **Phase 4**.
5. **Vollständiges Fehlen von Klippen, Schichtfelsen, Großmonumenten (>100 m Rippenkrone, Inselmonument, Viadukt) und Himmelskörpern (Planet, Monde, Pods)** (G7, F1–F4, H1, H2) → **Phase 1, 3, 5, 6**.
