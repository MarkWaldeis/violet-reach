# Meshy-Pipeline — Kalibrierung und Produktionsregeln (Phase 3)

Dieses Dokument hält die Ergebnisse der Phase-3-Kalibrierung (`GRAFIK_PLAN.md`, Abschnitt 7, 8 und Phase 3) anhand der drei Pilot-Assets `boulder_chalk_a`, `trunk_acacia_a` und `ruin_wall_a` fest und definiert die verbindlichen Regeln für die Serienproduktion in Phase 4 und 5.

Alle Rohdaten, Prüfblätter und Kostenbelege liegen außerhalb des Repositories in `C:\Users\Mark Waldeis\Desktop\Violet Reach Meshy\` (`VR_MESHY_DIR`).

---

## 1. Kalibrierung Bildmodell & neue Regel zur Bildbeschaffung

### 1.1 Vergleich `nano-banana-2-lite` (v1, 3 Credits) vs. `gpt-image-2-5-flare` (v2, 9 Credits)

Beide Bildmodelle wurden mit exakt demselben Prompt je Pilot-Asset sowie `--aspect-ratio 1:1 --remove-background true` getestet (siehe Vergleichsbild `C:\Users\Mark Waldeis\devin-screenshots\violet-reach\meshy-pilot\images_v1v2.jpg` und `<asset>/image_qa.json`):

| Asset | `v1`: `nano-banana-2-lite` (3 Cr.) | `v2`: `gpt-image-2-5-flare` (9 Cr.) | Auswirkung auf 3D-Rohmodell |
|---|---|---|---|
| `boulder_chalk_a` | **Pass (mit Abstrichen):** Kalkig-stufig, aber eher rundlich-knollige Gesamtform, leichte Abdunklung an der Unterseite. | **Pass:** Klar quaderförmig-kantiger Block mit deutlichen waagrechten Schichtbändern, senkrechten Bruchrissen und Poren. | `B-v1` (aus `v1`) reißt das Höhen-/Breitenverhältnis (`H/B = 0,812` statt Soll `0,615`, Abweichung Faktor `1,32 > 1,30` -> `aspect_mismatch`) und hat deutlich flauere Texturdetails (`HF = 0,089`). `B-v2` (aus `v2`) trifft die Zielproportionen (`H/B = 0,600`, `T/B = 0,638`) und liefert fast doppelten Mikro-Kontrast (`HF = 0,151`). |
| `trunk_acacia_a` | **Fail (Checkliste Punkt 7):** Ignoriert `"no thin twigs"` und erzeugt oben ein dichtes Geflecht feiner Zweige; Stamm zu dünn, kaum Wurzelanlauf. | **Pass:** Kräftiger, leicht geneigter Stamm mit ausgeprägtem Wurzelanlauf (`root flare`), 4 dicke Hauptäste in sauberer Schirmform; nur vereinzelte dünne Zweigspitzen ganz oben. | Das feine Zweiggeflecht aus `v1` verschmilzt in `image-to-3d` zu geschlossenen Klumpen. `v2` ergibt ein sauberes Astgerüst (`B-v2`), bei dem lediglich 4 winzige Zweigspitzen (`z_min_rel >= 0,928`) als lose Inseln abfallen und in Blender per `drop_loose` entfernt werden. |
| `ruin_wall_a` | **Weak:** Wirkt wie eine frisch gemauerte, scharfkantige Neubau-Treppe ohne Verwitterung; 11 % halbtransparenter Alpha-Saum (`alpha fringe`). | **Pass:** Verwitterter elfenbeinfarbener Kalkstein mit Poren, angeschlagenen Kanten, unregelmäßig abgetreppter Bruchkrone, klar sichtbarer Mauerdicke an der Stirnseite und geradem Fuß. | `A-v2` (aus `v2`) liefert ein maßhaltiges, wasserdichtes Mauerstück (`T/B = 0,178` vs. Soll `0,175`) mit glaubwürdiger Quaderstruktur und Verwitterung. |

**Technisches Fazit zu den Meshy-Bildmodellen:**
`nano-banana-2-lite` hat im Piloten nur 1 von 3 Assets bestanden (und selbst dort im 3D-Schritt zu `aspect_mismatch` und schwächerer Texturschärfe geführt). Negative Formvorgaben (`no thin twigs`) und subtile Oberflächenzustände (historische Verwitterung statt Neubau) setzt `gpt-image-2-5-flare` (3 von 3 bestanden) zuverlässig um.

### 1.2 Verbindliche Regel für zukünftige Referenzbilder (**Marks Entscheidung 24.11.: Meshy, nicht Grok**)

1. **Referenzbilder kommen aus Meshy (`gpt-image-2-5-flare`, 9 Credits, `--remove-background true`):**
   Mark hat am 24.11. entschieden, dass die Bildgenerierung wieder über Meshy läuft und **nicht** mehr lokal über Grok/Antigravity. Begründung: Die AAA-Bäume, das Gras- und das Wasser-System kommen ohne Meshy-Credits aus der Wiederverwendung von *Fantasy open world* (`docs/grafik/FANTASY_OPEN_WORLD_REUSE.md`), dadurch steht das Meshy-Budget für die übrigen wichtigen Assets frei — und `gpt-image-2-5-flare` hat die Bild-Checkliste im Piloten 3:0 gegen `nano-banana-2-lite` und die lokale Grok-Generierung gewonnen. Die frühere Credit-Sparregel (Grok zuerst) ist damit **aufgehoben**.
2. **Pflichtprüfung vor 3D:**
   Jedes `chosen.png` durchläuft vor dem 3D-Aufruf zwingend die 7-Punkte-Checkliste aus `GRAFIK_PLAN.md` 7.2 (1 Objekt, >= 10 % Rand, sauberer Alphakanal ohne Saum/Löcher, flaches bedecktes Licht ohne Schlagschatten/Boden, 3D-taugliche Tiefe ohne dünne Zweig-/Laubnester, Palettenfarbe, Brief-Proportionen) und wird mit seinem SHA-256 in `image_qa.json` sowie `meshy.json` festgehalten.
3. **Multiview für Klasse-A-Heroes:**
   Für Hero-Monumente und große Klippen (`A-multiview`, `multi-image-to-3d`) werden mehrere Ansichten desselben Objekts generiert (`--generate-multi-view true`), je Ansicht mit eigener Checklisten-Prüfung (`image_qa_view_N.json`).

### 1.3 Bewährte Prompt-Bausteine für Referenzbilder

Das im Piloten validierte Prompt-Gerüst wird für alle weiteren Assets beibehalten:

```text
<Gegenstand, genaue Bau-/Wuchsform, Maße in Metern, Material, Schicht-/Fugenstruktur, Verwitterungsgrad>.
single isolated object, whole object visible, nothing cropped, at least 10 percent empty margin on all sides,
three-quarter view from slightly above, centered, fills about 80 percent of the frame,
flat even overcast lighting, no cast shadows, no rim light, no ground plane, no grass,
plain neutral light grey background, photorealistic, matte surface, fine surface detail,
no text, no watermark, no people.
```

Zusatzregeln aus dem Piloten:
- **Bäume/Stämme (`trunk_*`):** Immer explizit `"with no leaves at all, only the trunk and main branches, ... split into thick branches, no foliage, no thin twigs"` fordern.
- **Felsen (`boulder_*`, `cliff_*`):** Immer `"blocky angular shape with stepped horizontal sedimentary layers and vertical fracture cracks, flat underside"` fordern, um glatte Kiesel zu verhindern.
- **Mauern/Architektur (`ruin_*`, `monument_*`):** Immer `"solid and thick with visible depth, straight flat base"` und die Dicke in Metern nennen, damit die Drei-Viertel-Ansicht die Stirnseite zeigt (verhindert flache Kulissenwände).

---

## 2. Kalibrierung 3D-Klasse: Klasse B (`smart-topology`) vs. Klasse A (`standard`)

Anhand von `boulder_chalk_a` wurde dasselbe Referenzbild `chosen_v2.png` einmal als **Klasse B** (15 Credits) und einmal als **Klasse A** (30 Credits) durch `image-to-3d` geschickt und zusammen mit `B-v1` aus 3 m Entfernung (Augenhöhe 1,7 m, 35 mm Brennweite, skaliert auf Zielhöhe 1,6 m) verglichen (`boulder_chalk_a/model_qa/compare.jpg`):

| Merkmal | `B-v1` (Klasse B, Bild `v1`) | `B-v2` (Klasse B, Bild `v2`) | `A-v2` (Klasse A, Bild `v2`) |
|---|---|---|---|
| **Meshy-Flags** | `--model-type smart-topology --target-polycount 30000` | `--model-type smart-topology --target-polycount 30000` | `--model-type standard` |
| **Kosten** | **15 Credits** | **15 Credits** | **30 Credits** |
| **Dreiecke / Vertices (verschweißt)** | 31 256 / 15 632 | 31 597 / 15 804 | 1 521 176 / 760 562 |
| **Dateigröße `model.glb`** | 24,1 MB | 28,6 MB | 74,1 MB |
| **Lose Teile / Schwebeteile** | 1 Teil (100 %) / 0 | 1 Teil (100 %) / 0 | 1 Teil (100 %) / 0 |
| **Randkanten / Löcher (`holes`)** | 42 Randkanten in 9 Löchern (max. 9,05 % Diag.) | 63 Randkanten in 12 Löchern (max. 15,47 % Diag.) | **0 Randkanten / 0 Löcher** (wasserdicht) |
| **Nicht-mannigfaltige Kanten** | 0 | 0 | 0 |
| **Seitenverhältnisse `T/B` · `H/B` (Soll `0,769` · `0,615`)** | `0,863` · `0,812` (`aspect_mismatch`) | `0,638` · `0,600` (OK) | `0,757` · `0,669` (OK) |
| **UV-Belegung / Texeldichte** | 65,2 % / 929 px/m | 60,0 % / 663 px/m | 69,4 % / 794 px/m |
| **Texturschärfe (`Detail 4K/2K` · `HF full`)** | `1,25` · `0,0888` | `1,08` · `0,1512` | `1,33` · `0,1829` |
| **Lichtgefälle (`oben/unten` · `Seiten max/min`)** | `0,98` · `1,12` | `0,99` · `1,10` | `1,03` · `1,08` |
| **Grundfarbe Ø / Rauheit Ø** | `#989386` / `0,67` | `#ABA59C` / `0,64` | `#A7A298` / `0,65` |

### Befund aus `compare.jpg` (3 m Kameraabstand, Lesezeichen G7)

1. **Optischer Eindruck aus 3 m:**
   In der 3-m-Vollansicht (obere Zeile in `compare.jpg`) sind `B-v2` und `A-v2` in Silhouette, Schichtbänken, Bruchkanten und Schattierung praktisch nicht zu unterscheiden. Erst in der 2×-Ausschnittvergrößerung (untere Zeile) zeigt `A-v2` minimal schärfere Mikroporen (`HF = 0,183` vs. `0,151`). Da Requisiten im Spiel auf `1024²` KTX2 komprimiert werden und im Nahbereich ohnehin die dreiseitig projizierte Detailtextur der Materialklasse (`rock_chalk`) darüberliegt, verschwindet dieser Unterschied zur Laufzeit vollständig.
2. **Geometrie und Topologie:**
   - **Klasse A (`standard`, 30 Credits)** liefert ein extrem dichtes, komplett wasserdichtes Sculpt-Mesh (1,52 Mio. Dreiecke bei `boulder_chalk_a`, 366k Dreiecke bei `ruin_wall_a`) ohne ein einziges Loch (`boundary_edges = 0`). Es kann nicht direkt als Spiel-LOD0 genutzt werden, sondern dient als High-Poly-Quelle für Dezimation und Texture-Baking in `export_asset.py`.
   - **Klasse B (`smart-topology`, 15 Credits)** liefert für den **halben Preis** ein sauberes ~31,6k-Dreiecke-Netz, dessen UVs und 4K/2K-PBR-Texturen direkt als LOD0 (ohne Neu-Bake) taugen. Typische Eigenheit von `smart-topology` sind kleine unverschlossene Randkanten-Schleifen (je 4–8 Kanten, bei `boulder_chalk_a` 12 kleine Löcher, bei `trunk_acacia_a` 26 kleine Öffnungen an Astspitzen). Sie erzeugen keine nicht-mannigfaltigen Kanten (`non_manifold_edges = 0`) und sind aus 3 m unsichtbar.
3. **Verbindliche Klassenregel:**
   - **Klasse B (15 Credits)** ist Pflicht für alle vielfach platzierten Requisiten: Felsbrocken (`boulder_*`, `rock_slab_a`, `scree_pile_a`, `shore_rocks_wet_a`), Baumstämme (`trunk_*`, `snag_*`, `log_*`, `stump_*`), Trümmer (`column_broken_a`, `ruin_blocks_*`, `capital_fallen_a`, `stair_fragment_a`), Kristalle (`crystal_*`) und kleine Himmelskörper (`skyship_pod_b`, `floating_rock_b`).
   - **Klasse A (30 Credits)** bleibt reserviert für große Hero-Objekte, Klippen (`cliff_*`, `rock_pillar_*`, `arch_sandstone_a`) und Architektur/Monumente (`ruin_wall_a/b`, `monument_*`, `pavilion_shore_a`, `rib_base_ornament_a`, `energy_core_a`, `skyship_pod_a`, `floating_rock_a`), wo scharfe Werksteinkanten, große ebene Flächen und High-to-Low-Baking entscheidend sind.

---

## 3. Tatsächliche Kosten laut `ledger.csv` und Budgetstatus

Alle 11 bezahlten Aufrufe der Phase 3 wurden über `ledger.csv` abgerechnet und gegen die Meshy-Preisliste geprüft:

| Schritt | Anzahl & Modell | Erwartet | Tatsächlich | Befund |
|---|---|---:|---:|---|
| Bildgenerierung `v1` | 3 × `text-to-image` (`nano-banana-2-lite`, `--remove-background true`) | 3 × 3 = 9 | **9 Credits** | Preis exakt laut Liste; **Freistellen (`--remove-background true`) kostet 0 Credits Aufpreis**. |
| Bildgenerierung `v2` | 3 × `text-to-image` (`gpt-image-2-5-flare`, `--remove-background true`) | 3 × 9 = 27 | **27 Credits** | Preis exakt laut Liste; Freistellen inklusive. Kontostand danach: **3124 Credits**. |
| 3D-Modelle Klasse B | 3 × `image-to-3d` (`smart-topology`, `30000`, `meshy-7`, PBR, 4K) | 3 × 15 = 45 | **45 Credits** | `boulder_chalk_a` (`B-v1`, `B-v2`), `trunk_acacia_a` (`B-v2`). Je **15 Credits** inkl. 4K-PBR. |
| 3D-Modelle Klasse A | 2 × `image-to-3d` (`standard`, `meshy-7`, PBR, 4K) | 2 × 30 = 60 | **60 Credits** | `boulder_chalk_a` (`A-v2`), `ruin_wall_a` (`A-v2`). Je **30 Credits** inkl. 4K-PBR. |
| **Gesamt Phase 3** | **11 Tasks (6 Bilder, 5 Modelle)** | **141 Credits** | **141 Credits** | Unter dem Phase-3-Budget von 150 Credits. **Restguthaben: 3019 Credits** (Start: 3160). |

**Textur-Lieferumfang von Meshy (`meshy-7`, `--enable-pbr true --texture-resolution 4k`):**
Jedes `model.glb` (sowohl Klasse A als auch Klasse B) enthält ein `Material_0` mit exakt 3 eingebetteten Texturen:
- `Image_0` (`base_color`, RGB, **4096 × 4096**, `sRGB`)
- `Image_1` (ORM-gepackt, **2048 × 2048**, `Non-Color`): Kanal **G** = `roughness`, Kanal **B** = `metallic` (Mittelwert ~`0,0017–0,0020`, wird in Blender abgetrennt und auf `0,0` geklemmt)
- `Image_2` (`normal`, RGB, **4096 × 4096**, `Non-Color`)

---

## 4. Rohmodell-Diagnose der 3 Pilot-Assets & Blender-Aufbereitung (`vrmeshy.py`)

Alle Meshy-Rohmodelle werden in `assets/<kategorie>/<id>/build.py` deterministisch über `tools/blender/vrmeshy.py` aufbereitet. Die Originaldateien in `VR_MESHY_DIR` bleiben unverändert; `load_raw()` verifiziert vor dem Import den SHA-256-Hash aus `meshy.json`.

### 4.1 Standard-Reihenfolge in `build.py` mit `tools/blender/vrmeshy.py`

1. **`objs = vrmeshy.load_raw(ASSET_DIR)`** — Prüft den SHA-256 von `model.glb` gegen `meshy.json`, importiert das GLB und entfernt Nicht-Mesh-Hilfsobjekte.
2. **`vrmeshy.drop_loose(objs, min_fraction=...)`** — Verschweißt zunächst gesplittete glTF-Vertices (`remove_doubles`, `dist=1e-4`), ermittelt zusammenhängende Komponenten und löscht alle losen/schwebenden Fragmente unterhalb von `min_fraction` der Gesamtdreiecke (die größte Komponente bleibt immer erhalten).
3. **`vrmeshy.normalize(objs, size_m=(L, W, H), height=H, yaw_deg=...)`** — Skaliert von Meshy-Einheiten (~0,8–1,9 m) auf echte Meter laut `brief.md`, dreht die Hauptachse um `yaw_deg`, zentriert XY auf der Bounding-Footprint-Mitte und setzt `z_min = 0` (`transform_apply`).
4. **`vrmeshy.delight_basecolor(objs, radius_frac=0.25)`** — Teilt die Luminanz der BaseColor-Textur durch ihren tiefpassgefilterten Verlauf (Box-Blur mit `0,25 ×` Bildkante, normiert auf den Median), sodass großflächig eingebackene Helligkeitsgradienten verschwinden, feine Risse, Poren und Fugen aber voll erhalten bleiben.
5. **`vrmeshy.grade_basecolor(objs, target_hex, strength=...)`** — Misst den zirkulären Mittelwert des Farbtons (Hue) sowie die Mediane von Sättigung und Helligkeit (HSV) aller deckenden Texel und verschiebt die gesamte Textur um `strength` Richtung Ziel-Hexwert aus `art/palette.json`.
6. **`vrmeshy.clamp_material(objs, roughness_min=..., metallic=0.0)`** — Trennt die `Image_1`-Verbindung am `Metallic`-Eingang des Principled BSDF ab, setzt `Metallic = 0.0` und klemmt den `Roughness`-Bildkanal pixelweise auf `>= roughness_min` laut `brief.md`.
7. **`vrmeshy.burial_skirt(objs, depth=...)`** — Schneidet den Fuß knapp über `z_min` (`z0`) waagrecht an (`_bisect_floor`), extrudiert die Schnittfläche um `depth` Meter nach unten und löscht die innenliegende Deckfläche (damit keine nicht-mannigfaltigen Innenkanten die spätere LOD-Dezimation blockieren). Verhindert Schwebe-Spalten am Hang.
8. **`vrmeshy.fix_normals(objs)`** & **`vrmeshy.link_source(objs)`** — Richtet alle Flächennormalen konsistent nach außen und verschiebt das fertige Quellmodell in die `SOURCE`-Collection für `export_asset.py`.

---

### 4.2 Diagnose & Aufbereitungsrezept je Pilot-Asset

#### 1. `boulder_chalk_a` — Kreidefels-Brocken (Gewählt: `model/B-v2/model.glb`, Klasse B)

- **Rohmodell-Diagnose (`boulder_chalk_a/model_qa/B-v2/qa.json` & `sheet.jpg`):**
  - **Geometrie:** 31 597 Dreiecke, 15 804 verschweißte Vertices, 1 zusammenhängendes Teil (100 % Anteil, 0 Schwebeteile), 0 nicht-mannigfaltige Kanten, 0 degenerierte Dreiecke.
  - **Randkanten/Löcher:** Flag `holes = true` (63 Randkanten in 12 kleinen Schleifen zu je 4–8 Kanten; größtes Loch bei `z_rel = 0,007` an der Unterseite mit 15,5 % Diag.-Umfang).
  - **Maße & Proportionen:** Orientierte Box `0,964 × 0,615 × 0,579` (`yaw_deg = +0,34°`). Verhältnisse `T/B = 0,638` (Soll `0,769`), `H/B = 0,600` (Soll `0,615`) -> `aspect_mismatch = false`. Gute, flache Unterseite (`bottom_flat_area_rel_footprint = 0,582`).
  - **Farbe, Licht & Material:** Kein eingebackenes Licht (`top/bottom = 0,988`, `sides_max/min = 1,102`). Mittlere Grundfarbe `#ABA59C` (etwas kühler und grauer als Zielpalette `canyon_chalk` `#BCB296`). Mittlere Rauheit `0,644` (nur `0,0086 %` der Texel `< 0,5`), Metall `0,0018`.
- **Konkrete Aufbereitung in `build.py`:**
  1. `objs = vrmeshy.load_raw(ASSET_DIR)` (`boulder_chalk_a/model/B-v2/model.glb`)
  2. `vrmeshy.drop_loose(objs, min_fraction=0.002)`
  3. `vrmeshy.normalize(objs, size_m=(2.6, 2.0, 1.6), yaw_deg=-0.34)` (skaliert auf `~2,60 × 1,66 × 1,56 m`)
  4. `vrmeshy.delight_basecolor(objs, radius_frac=0.25)`
  5. `vrmeshy.grade_basecolor(objs, "#BCB296", strength=0.60)` (wärmt `#ABA59C` Richtung `canyon_chalk` `#BCB296` auf, erhält den Kontrast zwischen hellen Bruchflächen `#E8DABE` und dunklen Schichtbändern `#9B8E7E`)
  6. `vrmeshy.clamp_material(objs, roughness_min=0.60, metallic=0.0)`
  7. `vrmeshy.burial_skirt(objs, depth=0.30)` (schneidet dabei das bodennahe Loch bei `z_rel = 0,007` direkt weg und erzeugt einen 30 cm tiefen Eingrabe-Sockel)
  8. `vrmeshy.fix_normals(objs)` -> `vrmeshy.link_source(objs)`
  9. **Export:** Klasse B (LOD0 übernimmt Meshy-UVs und Texturen direkt ohne Neu-Bake; LOD1 ~8 000, LOD2 ~2 000, LOD3 ~400 mit erhaltenen UV-Nähten; Texturbudget Requisite `1024²` KTX2; Materialklasse `rock_chalk`).

#### 2. `trunk_acacia_a` — Schirmakazie, Stamm ohne Laub (Gewählt: `model/B-v2/model.glb`, Klasse B)

- **Rohmodell-Diagnose (`trunk_acacia_a/model_qa/B-v2/qa.json` & `sheet.jpg`):**
  - **Geometrie & Schwebeteile:** 31 636 Dreiecke, 15 821 verschweißte Vertices, 0 nicht-mannigfaltige Kanten. **Flags `many_loose_parts = true` und `floating_parts = true`:** Das Netz besteht aus **5 Komponenten**:
    - Hauptstamm: 30 794 Dreiecke (`97,34 %`, `z_min_rel = 0,0`)
    - 4 schwebende Zweigfragmente am oberen Kronendach (`z_min_rel = 0,928` bis `0,974`): **316 Dreiecke (`0,999 %`)**, **252 Dreiecke (`0,797 %`)**, **220 Dreiecke (`0,695 %`)** und **54 Dreiecke (`0,171 %`)** — zusammen 842 Dreiecke (`2,66 %`).
  - **Randkanten/Löcher:** Flag `holes = true` (112 Randkanten in 26 kleinen Schleifen zu je 4–8 Kanten, fast alle an den oberen Astspitzen bei `z_rel = 0,81–0,95`, plus eine 5-Kanten-Öffnung an der Wurzelunterseite bei `z_rel = 0,010`).
  - **Maße & Proportionen:** Orientierte Box `0,903 × 0,781 × 0,814` (`yaw_deg = -18,3°`). Verhältnisse `T/B = 0,866` (Soll `1,000`), `H/B = 0,902` (Soll `0,955`) -> `aspect_mismatch = false`. Kleine Standfläche unten durch auslaufende Wurzelspitzen (`bottom_flat_area_rel_footprint = 0,0656`).
  - **Farbe, Licht & Material:** Sehr gleichmäßiges Licht (`top/bottom = 0,961`, `sides_max/min = 1,053`). Mittlere Grundfarbe `#574D46` (graubraun, heller als Zielpalette `bark` `#41321D`). Mittlere Rauheit `0,670` -> Info-Flag **`roughness_below_brief = true`** (Brief fordert `roughness_min = 0,70`).
- **Konkrete Aufbereitung in `build.py`:**
  1. `objs = vrmeshy.load_raw(ASSET_DIR)` (`trunk_acacia_a/model/B-v2/model.glb`)
  2. **`vrmeshy.drop_loose(objs, min_fraction=0.02)`** — **Achtung:** Der Standardwert `0.002` (`0,2 %`) reicht hier nicht, da drei der vier schwebenden Zweiginseln zwischen `0,695 %` und `0,999 %` der Dreiecke besitzen! Mit `min_fraction=0.02` (`2 %`) werden alle vier Schwebeteile (842 Dreiecke) sauber entfernt und nur der zusammenhängende Stamm (30 794 Dreiecke) behalten.
  3. `vrmeshy.normalize(objs, height=10.5, yaw_deg=18.3)` (skaliert mit Faktor `12,90` auf exakt `10,5 m` Höhe -> Ausladung `11,64 × 10,08 × 10,50 m`, richtet Gierachse auf `0°` aus)
  4. `vrmeshy.delight_basecolor(objs, radius_frac=0.25)`
  5. `vrmeshy.grade_basecolor(objs, "#41321D", strength=0.65)` (verschiebt `#574D46` auf den satten, dunklen Rindenton `bark` `#41321D`)
  6. `vrmeshy.clamp_material(objs, roughness_min=0.70, metallic=0.0)` (behebt `roughness_below_brief`, hebt alle Roughness-Werte auf `>= 0,70`)
  7. `vrmeshy.burial_skirt(objs, depth=0.35)` (kappt die untersten Wurzelspitzen auf eine stabile Schnittfläche, schließt die Öffnung bei `z_rel = 0,010` und extrudiert den Wurzelfuß 35 cm in den Boden)
  8. `vrmeshy.fix_normals(objs)`
  9. **Laubkrone in Blender aufsetzen (Phase 4):** Auf die flache Schirmebene der oberen Astenden (`z ≈ 8,0–10,5 m`) platziert Blender die Schirmkrone aus Astbüschel-Karten (gemeinsamer `2048²`-Laub-Atlas, nach außen/oben gekippte Normalen für weiches Gegenlicht-Durchlicht, Verdeckung im Kroneninneren, Windgewichte für Stamm/Ast/Blatt). Die Laubkarten verdecken zugleich die kleinen offenen Randkanten an den Astspitzen vollständig.
  10. `vrmeshy.link_source(objs)` -> **Export:** Klasse B für den Stamm (`1024²` KTX2, Materialklasse `bark`) kombiniert mit Laubkrone (`foliage`), LOD0 ≤ 30 000, LOD1 ~9 000, LOD2 ~2 500, LOD3 als 8×8-Impostor-Fernbild.

#### 3. `ruin_wall_a` — Ruinenmauer aus Kalkstein (Gewählt: `model/A-v2/model.glb`, Klasse A)

- **Rohmodell-Diagnose (`ruin_wall_a/model_qa/A-v2/qa.json` & `sheet.jpg`):**
  - **Geometrie:** 366 570 Dreiecke, 183 149 verschweißte Vertices, 1 Teil (100 %), 0 Schwebeteile, **0 Randkanten / 0 Löcher** (vollständig wasserdicht, `signed_volume = 0,682`), 0 nicht-mannigfaltige Kanten. **Alle Pflicht- und Info-Flags sind grün (`false`).**
  - **Maße & Proportionen:** Orientierte Box `1,903 × 0,340 × 1,375` (`yaw_deg = 0,0°`). Wandstärke zu Länge `T/B = 0,1784` trifft exakt das Brief-Verhältnis `1,4 / 8,0 = 0,175` (Abweichung `1,019`). Höhe zu Länge `H/B = 0,7224` vs. Soll `4,5 / 8,0 = 0,5625` (Faktor `1,284 < 1,30`, Mauer ist im Verhältnis zur Höhe etwas kompakter: bei Skalierung auf `4,50 m` Höhe misst sie `6,23 × 1,11 × 4,50 m`). Nahezu perfekt ebene Standfläche (`bottom_flat_area_rel_footprint = 0,957`, `base_slice_extent_rel = [0,990, 0,995]`).
  - **Farbe, Licht & Material:** Leichtes Helligkeitsgefälle an der abgetreppten Oberkante (`top/bottom = 0,837`, `lum_lin top = 0,406` vs. Längsseiten `±Y = 0,539 / 0,522`, `sides_max/min = 1,167`), da die aufgebrochenen Fugen auf der Mauerkrone dunkler verwittert sind. Mittlere Grundfarbe `#C6BAA8` (etwas graubeiger als `monument_white` `#E8DABE` und `stone_weathered` `#DCCDB1`). Mittlere Rauheit `0,633` (`0 % < 0,5`, über dem Brief-Minimum `0,55`), Metall `0,0017`.
- **Konkrete Aufbereitung in `build.py`:**
  1. `objs = vrmeshy.load_raw(ASSET_DIR)` (`ruin_wall_a/model/A-v2/model.glb`)
  2. `vrmeshy.drop_loose(objs, min_fraction=0.002)`
  3. `vrmeshy.normalize(objs, size_m=(8.0, 1.4, 4.5), yaw_deg=0.0)` (bindet über die Höhe auf `4,50 m` bzw. bei Vorgabe `height=4.5` auf `6,23 × 1,11 × 4,50 m`, zentriert XY, setzt Fuß auf `z = 0`)
  4. `vrmeshy.delight_basecolor(objs, radius_frac=0.25)` (gleicht den großflächigen Helligkeitsunterschied zwischen Krone `0,406` und Seitenwänden `0,539` aus, erhält aber die feinen dunklen Quaderfugen `#AAA9A4`)
  5. `vrmeshy.grade_basecolor(objs, "#DCCDB1", strength=0.65)` (hebt `#C6BAA8` in den warmen Kalksteinton `stone_weathered` `#DCCDB1` / `monument_white` `#E8DABE`)
  6. `vrmeshy.clamp_material(objs, roughness_min=0.55, metallic=0.0)`
  7. `vrmeshy.burial_skirt(objs, depth=0.35)` (extrudiert den geraden Mauerfuß um 35 cm nach unten für schräge Hanglagen im Ruinenfeld)
  8. `vrmeshy.fix_normals(objs)` -> `vrmeshy.link_source(objs)`
  9. **Export:** Klasse A über `export_asset.py` (High-Poly-Quelle mit 366k Dreiecken wird auf Spiel-LOD0 ~20 000, LOD1 ~6 000, LOD2 ~1 500 reduziert; BaseColor, Normalen, Rauheit und AO werden vom Quellnetz auf `2048²` KTX2 gebacken; Materialklasse `stone_white`).
