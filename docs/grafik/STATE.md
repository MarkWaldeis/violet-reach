# Grafik-Stand (GRAFIK_PLAN.md)

Diese Datei reicht, damit eine neue Session nahtlos weitermacht. Nach jedem Arbeitspaket aktualisieren.

## Aktuell

- Zweig: `grafik/next-level` — aktueller Head siehe `git log`; zuletzt dokumentierte Kette: f7bb548 Gras-Fix → 8e86404 Felsen platziert → a413710 Gras-Farbtuning → 8045b61 Cleanup → grass_tuft-Altbestand entfernt
- Phase: **Phase 2 fast abgeschlossen** — Bench p2-r16 bestanden. **Phase 4.1 GPU-Gras RENDERT + Farbtuning ABGESCHLOSSEN** (saftiges Wiesengrün, siehe unten — Doppeltint/sRGB/normalNode-Fallen). Parallel: 3 Felsen approved+werden exportiert/platziert, 6 Fantasy-Bäume in Revision nach Gate-Review.
- Session-Stand (fortlaufend): VEGETATION-R5-REVIEW: oak/beech/willow/fern APPROVED (oak/willow/fern knapp), ancient weiterhin rejected wegen nahezu schwarzer plastischer Hauptäste, restlicher Speerenden und harter dreieckiger Wurzelplatten. Vier Exportkandidaten vorhanden; ancient R6 implementiert: warme strukturierte Rinde statt Schwarzplastik, Speerenden mit Zweig+Laub integriert, getrennte Wurzeln volumetrisch gerundet; finale Sheets/grüner Check, unabhängiges Review läuft. Ground-Bench nach Upload+Readiness: CPU 9.61→7.74 ms, 1%-Low 19.16→21.44, flight weiterhin perfekt; Ground-Spikes bleiben (max 66.9 ms, 4.167M Tris) und sind noch nicht gelöst. VEGETATION-R5 implementiert: separate horizontale Oberflächenwurzeln statt Kragen/Topfrand, verjüngte/begrünte Astenden, Willow-Vorhänge zerschlissen und Farn als 44 überlappende gebogene Wedel ohne schwarzen Kern/Spike-Rootlets. Finale Sheets gerendert, py_compile + vr.py check grün; alle fünf warten als `blender_review` auf ein neues unabhängiges Review. Metriken weiterhin im Korridor (Mediane .549–.689), Dreiecke 1852–14228. PERF-UPLOADFIX implementiert: Die falschen `DynamicDrawUsage`-Flags wurden aus GPU-Gras und Instanz-Assets entfernt; Asset-Matrix/Tint-Uploads nutzen jetzt Präfix-`updateRanges`. Grund: three.js WebGPU lädt Dynamic-Attribute auch ohne `needsUpdate` jeden Frame erneut voll hoch (G3-Gras theoretisch mehrere MB/frame); Tests 98/98 + tsc grün. Bench-Verifikation muss warten, bis die R5-Blenderjobs fertig sind. VEGETATION-R4 bewertet: Die korrigierte Kartenmetrik wurde erreicht (Mediane oak .652, beech .690, ancient .649, willow .622, fern .438; bushes Referenz .632), aber das unabhängige Gate-Review hat **alle fünf** Assets rejected. Kartengröße ist nicht mehr der Hauptblocker; jetzt blockieren vertikale plissierte Wurzelkragen/harte Topfränder, glatte schwarze/plastische Ast- und Speerenden, abgeschnittene/bulböse Kappen (besonders willow/beech/ancient) sowie beim Farn schwarzer Kern, stachelige braune Rootlets und angular-bändige Blattspitzen. Reviews formal als Runde 4 recorded; alle fünf sind wieder `modeling`. Nächste Runde muss horizontale einzelne Oberflächenwurzeln, kontinuierlich verjüngte/begrünte Astenden und einen komplett neuen Farnzentrumsaufbau liefern. MESHY-REWORK umgesetzt: Alle sechs Gate-Fails (`log_fallen_a`, `stump_roots_a`, `trunk_acacia_b`, `trunk_baobab_a`, `rock_slab_a`, `monument_split_disc_a`) wurden aus verschärften v2-Referenzen neu generiert, heruntergeladen, roh QA-geprüft und mit entrümpelten Build-Pipelines erfolgreich smoke-gebaut. Exakt 159 Credits verbraucht; Budget jetzt `rework 159/320`, `total 528/2000`, Meshy-Konto 2632. Formale Review-Sheets/Approval/Export stehen noch aus. PERF-QUICKWIN implementiert: GPU-Gras nutzt jetzt Kamerahöhe + exakte Terrainmaxima (`TerrainStream.maxHeightInRect`) für sichere 3D-Sichtbarkeitskriterien. Im hohen Flug werden garantiert unsichtbare Graszellen nicht mehr gebaut/hochgeladen; bereits gebaute Zellen werden auf count=0 statt nutzlos weiterzurendern. Bodenverhalten bleibt unverändert, bei hohem Relief bleibt die Abschaltung konservativ. Unit-Verifikation 98/98 + tsc grün. Bench `grass-flight-culling` valid: flight jetzt 59.94/59.22 FPS, max 17.0 ms, 0 Frames >25 ms (vorher 58.32/18.87, max 200.1 ms, 9 Frames >50 ms) bei praktisch unveränderten Dreiecken/Draws — der Flugspike ist damit eindeutig behoben. Ground bleibt separat verletzt (57.64/19.16, max 66.8 ms, 17 Frames >50 ms; Dreieckswarnung 4.168M). EXPORT-PAKET: `bush_lush_a` und `boulder_chalk_c` sind exportiert und klein testplatziert. Bush GLB 4.82 MB, LODs 1687/505/247/87, UASTC foliage albedo/normal + ETC1S ORM; Boulder GLB 1.41 MB, LODs 28101/5999/1599. Placements 1243 Einträge/16.019 expandierte Instanzen (+3 boulder_chalk_c bei G7, +15 bush_lush_a in zwei Hainclustern); Tests 96/96, tsc und npm run build grün. Browser-Sichtung/Bench noch offen, weil parallel R4/Meshy läuft. GRASS-INTEGRATION: `grass_tuft_a` vollständig aus den Placements entfernt (13 Scatter, exakt 64.120 expandierte Instanzen; Placement-Einträge 1251→1238, deklarierte Instanzsumme 16.001). Sichtprüfung G1/G3/G4/G6: keine Baldness/Lücken, Weg frei. Bench `tuft-entfernt` valid, aber Budget weiterhin verletzt: ground 57.99/21.77 FPS, max 66.9 ms, Dreiecke max 4.168.620; flight 58.32/18.87, max 200.1 ms. Gegenüber `p41-opt-clean` nur leichte Verbesserung (1%-lows +1.2/+1.9 FPS, Frames >50 ms ground 12→10/flight 18→9, Textur -1.33 MiB); Dreieckspeak praktisch unverändert — der Altbestand war nicht der Haupt-Dreieckstreiber. Nächste Perf-Ursache separat analysieren. GATE-REV-E: **boulder_chalk_c APPROVED**. 6 Assets brauchen Meshy-Regenerierung statt Texture-Patches (log/stump/acacia_b/baobab/slab/monument) — Budget prüfen vorher. Approved-neu gesamt: bush_lush_a + boulder_chalk_c warten auf Export. ALTSTAND: GATE-R3: **bush_lush_a APPROVED** (erste Vegetation durchs Tor!), Bäume weiter rejected, oak knapp. SCHLÜSSELMETRIK vom Mesh-Scan: Karten-Komponenten 1.2-1.6m = sichtbare Regale, bush 0.63m = dicht. Nächste Runde: Karten unter ~0.7m verkleinern/staffeln + TIP_CAP_CONFIG für oak/beech/ancient aktivieren. ALTSTAND: R3-Rebuild committed (geometrisch: Tochterkarten/Flares/Kragen/Kappen), Gate-Review-R3 läuft (ec7c0cd7). Gras-Perf committed 314499f (95/95 Tests, Dreiecke 382k statt 697k an G3) — sauberer Bench p41-opt-clean sobald Blender frei. Meshy-Reparatur läuft noch. ALTSTAND: Gate-Re-Review Runde 2 = **0/6 approved** (geometrische Kernmängel bleiben). Laufende Subagenten: Vegetation-Tiefen-Rebuild R3 (bush→fern→oak), Gras-Perf-Optimierung (Build-Hitches/Dreiecke), Meshy-Reparatur 7 Assets. Gras-Perf-Daten: 1%low 21.9 statt ≥45, Dreiecke 4.6M>4M; grass_tuft-Doppelbestand (64k Instanzen parallel zum GPU-Gras) ist der große Hebel. Capture p2-r16 erst nach Stabilisierung.
- Verifikation: **98/98 Explorer-Tests grün**, `tsc --noEmit` sauber, `vr.py check` grün (34 Assets).
- Bench p2-r16 (sauberer Lauf, unbeladene Maschine): ground 59,79 FPS mean / 47,71 1%-low, flight 59,94 / 59,48, 0 Budget-Verletzungen, max 245 Draws, 896 MiB Textur. Der ursprüngliche r16-Fail (29er 1%-lows) war Load-Rauschen paralleler Blender-Jobs.
- Meshy-Kostenbuch: **369 / 2000 Credits** verbraucht (Antigravity +228 für 10 Klasse-B-Modelle, 2 Bilder, 2 Klasse-A-Multiview), Kontostand 2791. Stopp bei 1800.
- **Neue Regel von Mark (ersetzt die Spar-Regel in MESHY.md):** Bildgenerierung wieder über Meshy erlaubt (nicht mehr zwingend lokal/Grok); Bäume/Gras/Wasser/AAA-Assets kommen bevorzugt aus dem Fantasy-open-world-Projekt (siehe `docs/grafik/FANTASY_OPEN_WORLD_REUSE.md`), Meshy-Credits bleiben für andere wichtige Assets.

- **Erkenntnis Ladezeiten:** die App braucht in dieser Umgebung 2–4 min bis `__vr.ready` (Wasserstufe allein ~90 s — `surfaceData` lädt viele Höhenkacheln; kein Deadlock!). Smoke-Tests brauchen Timeout ≥ 300 s. Dev-Server für QA immer mit `VR_GATE_CACHE_MS=30000 npm run dev` starten, sonst serialisiert der Gate-Check jede Kachel-Anfrage (~1 s × 256 Kacheln). Dev-Server nach größeren Edits/Gate-Flips neu starten — HMR-Zustand kann korrupt sein.
- **Tree-Import abgeschlossen (Subagent):** 6 Fantasy-Bäume in `blender_review` (tree_oak/beech/ancient/willow, bush_lush, fern_lush), Export-Smoke-Test Oak ≈ 2,29 MB vs ~17 MB alte broadleaf — klarer Ersatz für Massenbewuchs. Offene Pipeline-Punkte: Canopy-LOD fehlt für meshy_class B (export_asset.py:244), exakt duplizierte Faces in Templates (4–8 je Baum), KTX2-Initialpfad nutzt ETC1S statt UASTC für Vegetation. Diese Assets + die 4 von Builder-a (scree/shore/arch/monument) brauchen noch unabhängige Gate-Reviews.
- **Vegetations-Reparaturpaket fertig (Builder, noch uncommitted):** alle 6 zuvor abgelehnten Vegetations-Assets wurden topologieerhaltend überarbeitet (gekräuselte/gekippte Alpha-Karten, geglättete Rinden-Normalen, teilweise zugespitzte freie Stiel-/Astenden, aufgehelltes Laub-Albedo, niedrigerer Alpha-Cutoff, emissionsbasierter Anti-Schwarz-Floor; Farn zusätzlich unregelmäßig geschichtet/UV-komprimiert/Wurzelkrone verkleinert). `vr.py check` grün (34 Assets), finale Sheets in allen `review/` Ordnern, aber nur **32 statt 64 Cycles-Samples**. Status bewusst weiterhin `blender_review`, `review=null`: kein Self-Review, kein Export, keine Platzierung. Nächster Schritt: unabhängiges Gate-Review. Ausführlicher ehrlicher Bericht: `C:\Users\Mark Waldeis\devin-screenshots\violet-reach\tree-revision\VEGETATION_REVISION_REPORT.md`.

### Offene Arbeiten (in dieser Reihenfolge)

1. **Neue Bush/Boulder-Platzierungen später visuell prüfen:** Export und kleine Testplatzierungen sind erledigt. Sobald keine schweren R4-/Meshy-/Blenderjobs laufen, G2/G4/G7 capturen und Bench-Wirkung prüfen; kein Massenersatz von `shrub_round_a` ohne A/B.
2. **Baum-Runde 4 mit 0,7-m-Kartenmetrik:** Oak/Beech/Ancient/Willow Karten deutlich verkleinern/staffeln, `TIP_CAP_CONFIG` für oak/beech/ancient aktivieren und Willow-Enden besser erfassen; Farn separat wegen Speerrosette. Scan-Skript-Percentile-Bug vorher korrigieren; unabhängiges Review, kein Self-Review.
3. **Meshy-Regenerierung der 6:** log/stump/acacia_b/baobab/slab/monument. Budget objektiv grün: Modellkosten 105 Credits, konservativ mit allen neuen Referenzbildern 159; rework dann 159/320, total 528/2000, weit unter Stopp 1800. Vor jedem bezahlten Call Ledger-Reserve; neue Modelle zuerst roh prüfen, alte modellspezifische build.py-Reparaturen nicht blind weiterlaufen lassen.
4. **Performance-Ursache nach grass_tuft-Entfernung neu analysieren:** Budgetverletzungen bleiben trotz entfernter 64k Instanzen. 1%-lows und lange Frames sind Hauptproblem; Dreieckspeak ~4.17M liegt weiter über dem 4M-Richtwert. Erst Ursache messen, dann gezielt optimieren.
5. **Capture-Lauf p2-r16 NEU fahren:** `node tools/qa/capture.mjs --run p2-r16` + Bench erst nach Stabilisierung der obigen Punkte; keine Captures parallel zu Edits/Blender.
6. **3 blinde Reviews** der finalen Lesezeichen (G1, G5, F1, F2, H1 >= 8) -> Phase-2-Sign-off.
7. **Danach:** Fantasy-Bäume gegen alte broadleaf-Bäume tauschen, Phasen 5-6 fortsetzen.

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
