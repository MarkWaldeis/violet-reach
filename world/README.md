# Weltentwurf — Violet Reach

Reproduzierbar mit Blender 5.3 (eingebautes NumPy, keine Pip-Pakete):

```sh
blender -b --python tools/world/build_world.py
# Schnelle Vorschau: grobe Berechnung, weiterhin runtimekompatible Exportmaße
blender -b --python tools/world/build_world.py -- --draft
python3 tools/world/test_world.py
```

Fester Seed **73129**. 8192 × 8192 m, 4097² Höhenwerte, 2 m Raster.
Blender: X Osten, Y Norden, Z oben. **Runtime: X Osten, Y oben, Z Süden**;
`runtime.z = -blender.y`. JSON-Koordinaten und die Zeilen der Regionskarte
folgen den Runtime-Achsen (oben = Norden).

`terrain/runtime/manifest.json` beschreibt 16 × 16 Kacheln à 512 m.
`<x>_<z>.r16`: je 257² rohe uint16-Werte, little-endian, zeilenweise +Z,
Spalten +X; gemeinsame Randwerte sind identisch.
`h = minHeight + v / 65535 * (maxHeight - minHeight)`.
`terrain/terrain.json` enthält zusätzliche Herkunfts- und Wasserstandsmetadaten.
Keine PNG-Höhenkacheln: das R16-Format ist der vereinbarte Runtime-Handoff.

`regions/regions.png` ist eine 8-Bit-Indexkarte (1025²); IDs, Zentren,
Begrenzungsrechtecke, Charakter und geplante Landmarken stehen in
`regions/regions.json`. Die verrauschten Regionsgrenzen teilen die gesamte Welt:

1. **Lyrenschlucht** — eingesenkte, klippenumschlossene Schlucht mit 44 steilen Felspfeilern und zerklüfteten Plateaukappen.
2. **Aschgrat-Canyon** — breiter, tief gewundener Einschnitt mit gestuften Kalkwänden im nördlichen Plateau.
3. **Dornengang** — schmaler Pass zwischen steilen Parallelgraten.
4. **Weißwall** — rund 490 m hohe, durchgehende Abbruchkante eines breiten westlichen Hochlands mit Weißfall-Übergang.
5. **Mondsichel** — sichelförmiger Grat um ein geschütztes Tal.
6. **Spiegelsee** — unregelmäßiges Seebecken mit eingeschnittenen Buchten, Landzungen, Strand- und Schilfzonen, Wiesen und sanftem Wanderstart.

`hydrology.json`: Flusslinien `[x,z,water_y,width]`, Seen mit `water_y` und
Uferpolygon `[x,z]`. Uferpolygone liegen am trockenen äußeren Ufersaum, die
sichtbare Wasserfläche etwas innerhalb; Flussmündungen unterbrechen den Saum.
Wasserstände flussabwärts monoton.
Die Wasserfallstelle ist markiert; ausgearbeitete Wasserfall- und Landmarken-
Assets gehören in spätere Phasen. Ebenso sind dunkle Waldflächen hier eine
Materialmaske, noch keine platzierten Bäume.

Das Skript kombiniert domain-verzerrtes fraktales Rauschen, explizite regionale
Formen, zwei konservative Hangtransport-Durchgänge, breite erodierte Täler
und weich mäandrierende Gerinne mit breiten Mündungsfächern. Stetige, absenkende
Segmentprofile werden per Minimum kombiniert: kein späterer Zufluss hebt ein
vorheriges Flussbett an. An der 2,5 m tiefen Sohle schließt ein flacher Nasssaum
an; die Böschung geht innerhalb der ersten 100 m weich auf rund 21° über und
schließt außerhalb dieses Uferkorridors an die vorhandenen Bergflanken an.
Seeufer werden bei Bedarf sanft angehoben, damit niedrige Canyonböden nicht
durch den trockenen Ufersaum brechen. Die Seebecken nutzen dieselben
Böschungen und stärker gegliederte, mit 384 Punkten exportierte Uferkonturen.
Flache Mündungsabschnitte werden über eine 60-m-Smooth-Union in das Seebecken
eingebunden. Höhenfeld, Uferpolygon und Review-Wasser lesen dieselbe gerundete
Distanzfunktion; dadurch treffen Fluss und See nicht als rechtwinklige Flächen aufeinander.
Dies ist künstlerische Makroerosion, keine
vollständige hydrodynamische Simulation. Der Bergrand bleibt innerhalb der
Weltgrenze. `--draft` interpoliert die grobe Vorschau ins gleiche Exportformat;
für die endgültige Welt ohne diesen Schalter bauen.

`review/overview.jpg` (beschriftet), `overview_plain.jpg` und `oblique.jpg`
werden mit **Cycles CPU** erzeugt. Die Schrägansicht liegt innerhalb des
Bergrands auf Überflughöhe; die Übersicht zeigt geglättete, interpolierte
Maskenkonturen statt Pixelkanten. `terrain.blend` ist lokal regenerierbar
und nicht versioniert. Die Mesh-Vorschau hat 1025² Vertices; die Runtime-
Höhenfelder behalten volle Auflösung. Die Render zeigen den Weltentwurf,
nicht die spätere Vegetations- und Monumentproduktion.

## Erster Brückenübergang im Slice

`bridge_arch_a` steht einmal bei `(480, 1504)`, Maßstab `1`, Yaw `0.785398`.
Die freigegebene Geometrie bleibt unverändert: 25 m lichte Öffnung,
40,94 m Gesamtlänge einschließlich Flügel und Landungen. Weißfall und
Dornbach sind im Slice bereits mindestens rund 42 m breit und passen nicht
unter diesen Bogen. Der Generator formt deshalb eine örtliche, gekrümmte
Einbuchtung am Nordufer: rund 20 m breit unter dem Bogen, nach Nordwesten
verjüngt und nach Südosten mit dem See verbunden. Ihr flacher Boden liegt
0,65 m unter dem 180-m-Seespiegel. Sanfte Ufer gehen in niedrige, trockene
Uferterrassen über; beide vollständigen Landungsflächen stehen darauf.
Seeumriss, Review-Wasser und R16 verwenden dieselbe deterministische Form.
Das ist kein Übergang über den ganzen Fluss und keine Laufzeit-Verformung.

`y_offset: 0.75` setzt den Ursprung bei rund 180,10 m; die unteren Stufen
schließen an die rund 180,14 m hohen Uferterrassen an. Der bestehende Fußpfad
führt bis zur südwestlichen Landung, ein zweiter kurzer Abschnitt von der
nordöstlichen Landung zurück in die Wiese. Die Laufkamera folgt weiterhin dem
Gelände, nicht der Brückentreppe; Objektkollision ist noch nicht implementiert.

## Freigegebenes Ufermodul

`lake_shore_a` liegt einmal bei `(626.5187, 1540.5455)`, Maßstab `1`,
Yaw `0.705398`, `y_offset: 0.03238`. Die rund 21,2 × 7,68 m große
Sand-, Kies- und Grasbank folgt dem Nordufer; die Wasserseite zeigt nach
Südost. Ihr Ursprung liegt bei 180,03 m, die tiefste Kante unter Wasser.
Die Platzierung ist gegenüber der ersten Probe etwas seewärts versetzt.
Ein Höhenvergleich mit dem tatsächlichen exportierten LOD0-Mesh hält das
Gelände unter der inneren Strandfläche; der auslaufende Grasrand bleibt
zum Anschluss an die natürliche Böschung eingebettet. Keine Geländeänderung,
keine gestreckten Achsen und kein Insel-Asset.

### Approved vegetation (Step L)

PR #8 head `7f5f57f` approves all seven imported vegetation assets; each is exported through the gate. The slice contains 360 mixed broadleaf trees, including 140 added in nine spawn-visible groves of 12–18 above the near and east/west shores, with open meadows between groups. Group edges and shaded interiors carry 1,148 shrubs and 2,075 fern clusters. There are 12,384 reeds in 216 irregular shallow shoreline beds and 64,120 meadow grass tufts, including the crystal accents' grass patches. Two-scale clump noise breaks up the grass; every instance has deterministic scale, yaw and subtle colour variation.

Scatter entries can select a `surface` profile (`meadow`, `land`, or `shore`) and a nonnegative `path_clearance` in metres. Deterministic surface filtering combines terrain slope, finer soil/grass noise, local hollows, interpolated water height and distance from paths. Land plants avoid sand and wet banks. Reed beds follow the actual R16 waterline rather than the outer hydrology envelope; roots lie between 0.3 m below and 0.03 m above water. Reeds grow upright with their contact skirts submerged; grass and ferns follow the ground normal.

Optional `slice.json.asset_options` records set per-asset `maxDistance` (metres), `lodScale` (screen-space transition multiplier), `lodRatio` (spacing between transitions), `aerialLODScale` (intermediate-LOD distance multiplier above the ground), `maxLOD` (coarsest permitted LOD), `shadowLODs` (number of near LODs casting shadows) and `tintVariation`. Defaults preserve existing assets. Mixed trees use LOD2 to 1,600 m. Ground-level distances, LOD0/shadow range and the far cutoff are unchanged by the aerial boost; only LOD0 casts tree shadows. Shrubs, ferns, reeds and grass cut off at 260, 70, 12 and 20 metres respectively. The reed re-export retains the approved source and 1024² texture specification, with 5,846 / 1,746 / 348 triangles instead of the old 14.5k floor. Disconnected micro-detail is pruned before collapse when its component floor prevents the target; native joined face-material IDs are preserved. Vegetation base colour, roughness and emission bake directly from those materials; normal and AO still project from SOURCE. Other categories retain source projection for every channel. Lit and isolated-albedo inspection shows no black reed wedges. All placements share instanced batches, chunk culling and per-instance frustum culling; shadow casters retain conservative chunk visibility. Loading status includes pending terrain LOD refinement.

Trees A/B preserve individual leaves as projected albedo/alpha/AO cards in LOD1 where the budget permits; LOD2 clusters them into three-axis atlas cards with a separate wood budget, using 65% of the metadata's maximum triangle allowance. Foliage uses double-sided alpha MASK (cutoff 0.35), not transparent blending; alpha-to-coverage is off. LOD0, source models and gate rules are unchanged; other vegetation remains opaque. A/B use aerialLODScale 2.0; C retains 2.5. Blender coverage/export regression: `blender -b --factory-startup --python-exit-code 1 --python tools/blender/test_canopy_lod.py`.

A/B re-exports retain their approved sources and texture sizes. Their LOD triangles are 59,098 / 14,892 / 1,808 (A) and 43,970 / 11,964 / 1,555 (B). C retains its committed export at 29,177 / 7,346 / 1,352. Known issue: the experimental canopy exporter collapses C's LOD2 trunk into a wedge, so C is excluded from this rollout and exporter path. The synthetic coverage fixture does not establish native trunk quality; side-by-side real-tree review remains required. Shrub, fern and grass exports remain unchanged.

The terrain refresh uses finer, lower-contrast ground variation, grass on flats, slope-driven soil, aspect/curvature breakup and a lighter wet-bank transition. Deterministic, bounded bends and width variation soften the southern Dornbach and Weißfall reaches without moving the bridge inlet. A full seed-73129 rebuild (`draft=False`) took 991.7 seconds. The inlet regression still verifies wet ground under the arch and complete dry, level landing footprints. The lake-shore mesh retains at least 6.2 cm sampled clearance above the terrain; the three column sites are unchanged. The gate is sunk another 21 cm to ground its entire apron. Scatter invalidated by the changed bank profile is removed, and 216 regenerated reed beds sit at 0–0.3 m depth or on the immediate wet bank.

`crystal_cluster_b` is imported alone from PR #14's approved c4c0cd0 record and exported at its specified 2048². Three differently yawed, tilted and scaled accents at (542,1447), (560,1470) and (530,1450) are sunk 1.40, 1.05 and 1.55 m into the grassy slope near the columns. Two small clumped-grass patches surround them. The three `crystal_violet_cluster_a` proof placements are removed. The energy-core asset remains excluded.

`crystal_spire_a` is separately approved at PR #14 record `3dc1277` (all six criteria 8). Only its folder is imported and exported at 2048², with 10,299 / 3,699 / 1,149 LOD triangles. One intended-size landmark stands on the open rise at `(424,1412)`, yaw `0.8`, pitch `7°`, roll `9°`, `y_offset: -0.25293`. Its lower-foot mesh samples are buried 3.5–42.0 cm, following the slope without a floating collar. The site is about 18 m off the shore path and 28 m from the nearest tree, with a clear terrain sightline from the fly spawn. A 1,200 m cutoff keeps it visible from the fly spawn; only LOD0 casts shadows.

### Shore gate and ruined colonnade (Step M)

`gate_white_a` from approved PR #13 head `84ecc13` stands at `(522,1510)`, yaw `-2.35619449`, scale `1`, offset `-0.20869`. Its source geometry has a quarter-turn before export; the runtime yaw follows the exported axes. The shore path loops around the upstream pier, passes through the opening and curves along the slope toward the stair's upper terrace at `(593.869,1490.652)`. The dead uphill spur ending at `(550,1460)`, which produced the pale rectangle behind the gate, is removed. No terrain or approved gate geometry was reshaped. The current full-apron seating supersedes the initial 0.005 m offset.

Both complete pier footprints occupy the flat, dry inlet bank. A ray survey against the actual exported LOD0 finds the stone bases embedded approximately 4.6–4.9 cm, while the threshold foundation is below terrain and its upper surface remains exposed.

Three approved PR #12 `column_white_a` instances stand off the path at `(528,1445)`, `(516,1436)` and `(552,1448)`: two are 15 m apart, with the third 24–38 m away. Each combines pitch and roll into a 7.8° tilt, with varied yaw and lean direction. Exported-mesh footprint rays seat their bases into the hillside, with minimum burial 4.5 cm. There is no fallen instance. Single placements accept optional finite `pitch`/`roll` radians, composed locally in YXZ order before terrain-normal alignment. The shared `vrcolumn.py` geometry helper and its material/palette dependencies participate in approval hashes.

### Shore stair seating (Step K)

The approved 4096² `stair_terrace_a` export stands at `(600,1500)`, yaw `-1.107137`, scale `1`, offset `-3.1824`. Following the lead's burial-first instruction, it is lowered 22.5 cm from the provisional fit; the construction rule in `docs/SESSIONS.md` limits source geometry below its origin, not runtime placement offsets. No berm or generator change is made, so terrain and the prior full rebuild remain unchanged. A pinned-source contact fixture contains 415 actual exported LOD0 front-apron samples. The runtime regression checks support and bounded burial (2.4–43.0 cm). A 0.7 LOD scale retains complete masonry in close three-quarter views; all three exported LODs remain in use. Bridge landing/inlet, shore-module clearance, gate-footprint and spire-foot support are rechecked against the unchanged terrain.

### Lakeside sandstone arch, scree and wet shore rocks (Step N)

The approved `arch_sandstone_a` (2048², 28,000 / 9,000 / 2,500 LOD triangles, 40.7 × 11.2 × 27.5 m) stands once at `(700,1456)`, yaw `-1.287`, scale `1`, `y_offset: 0`, in the shallow water of the eastern shore below the Mittelrücken. The span runs perpendicular to the viewing direction from the north-shore walking area, so the opening faces the gate/beach side; the northeast abutment rests on the waterline bank (ground 180.2 m) while the southwest abutment stands in about 1.3 m of water. Both 1.8 m embed edges stay buried at every sampled foot point; the centre lakebed lies at 179.7 m. The arch is inside the G3 frame and visible along the whole north shore. It is not yet part of the planar-reflection layer set.

Six `scree_pile_a` singles form the talus of the Mittelrücken cliff band: two in the flat accumulation pocket at `(708,1207)` / `(720,1213)` next to the `boulder_chalk_a` group, four as a merging apron along the southern foot at `(685,1230)`, `(698,1248)`, `(706,1270)` and `(698,1274)`. All sit on ground of at most 7° slope, with small individual pitch/roll and `y_offset` between -0.08 and -0.15 m; the 35 cm embed edge covers the remaining micro-relief.

Seven `shore_rocks_wet_a` singles straddle the 180 m waterline in three groups: three along the north-bay beach near G5 at `(562,1546)`, `(578,1552)` and `(594,1558)`, two continuing the `lake_shore_a` bank eastward into the lake at `(641,1532)` and `(644,1538)`, and two in the shallow water beside the sandstone arch at `(688,1450)` and `(682,1462)`. Ground at the centres ranges from 179.6 to 180.0 m, so the bases are submerged 3-45 cm and the baked wet/dry roughness line meets actual water.
