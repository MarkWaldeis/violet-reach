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

PR #8 head `7f5f57f` approves all seven imported vegetation assets; each is exported through the gate. The slice contains 237 mixed broadleaf trees in fourteen groves of 10–20 plus scattered singles, 624 shrubs around group edges and above the wet shore, 1,150 fern clusters beneath the tree footprints, 3,510 reed clusters in 98 shallow shoreline beds and 60,000 meadow grass tufts. Two-scale clump noise breaks up the grass; every instance has deterministic scale, yaw and subtle colour variation.

Scatter entries can select a `surface` profile (`meadow`, `land`, or `shore`) and a nonnegative `path_clearance` in metres. Deterministic surface filtering combines terrain slope, finer soil/grass noise, local hollows, interpolated water height and distance from paths. Land plants avoid sand and wet banks. Reed beds follow the actual R16 waterline rather than the outer hydrology envelope; roots lie between 0.3 m below and 0.03 m above water. Reeds grow upright with their contact skirts submerged; grass and ferns follow the ground normal.

Optional `slice.json.asset_options` records set per-asset `maxDistance` (metres), `lodScale` (screen-space transition multiplier), `lodRatio` (spacing between transitions), `maxLOD` (coarsest permitted LOD), `shadowLODs` (number of near LODs casting shadows) and `tintVariation`. Defaults preserve existing assets. Mixed trees retain LOD1 canopies farther out and use LOD2 to 1,600 m; only LOD0 casts shadows. Shrubs, ferns, reeds and grass cut off at 160, 70, 12 and 24 metres respectively. The reed re-export retains the approved source and 1024² texture specification, with 5,846 / 1,746 / 348 triangles instead of the old 14.5k floor. Disconnected micro-detail is pruned before collapse when its component floor prevents the target; native joined face-material IDs are preserved. Vegetation base colour, roughness and emission bake directly from those materials; normal and AO still project from SOURCE. Other categories retain source projection for every channel. Lit and isolated-albedo inspection shows no black reed wedges. All seven foliage exports are opaque and double-sided; no alpha-test workaround is used. All placements share instanced batches, chunk culling and per-instance frustum culling; shadow casters retain conservative chunk visibility. Loading status includes pending terrain LOD refinement.

The three tree re-exports retain their approved sources and texture sizes. Their LOD triangles are 59,098 / 14,302 / 2,317 (A), 43,970 / 11,308 / 1,925 (B), and 29,177 / 7,346 / 1,352 (C). Component pruning stops when the component floor has enough collapse headroom, rather than deleting foliage until the unsimplified mesh meets the target. A high-detail connected trunk plus disconnected two-colour leaves exercises this case. Lit and isolated-albedo inspection covers LOD0 and LOD2. Shrub, fern and grass exports remain unchanged.

### Shore gate and ruined colonnade (Step M)

`gate_white_a` from approved PR #13 head `84ecc13` stands at `(522,1510)`, yaw `-2.35619449`, scale `1`, offset `0.005`. Its source geometry has a quarter-turn before export; the runtime yaw follows the exported axes. The shore path loops around the upstream pier, passes through the opening and curves along the slope toward the stair's upper terrace at `(593.869,1490.652)`. The dead uphill spur ending at `(550,1460)`, which produced the pale rectangle behind the gate, is removed. No terrain or approved gate geometry was reshaped.

Both complete pier footprints occupy the flat, dry inlet bank. A ray survey against the actual exported LOD0 finds the stone bases embedded approximately 4.6–4.9 cm, while the threshold foundation is below terrain and its upper surface remains exposed.

Three approved PR #12 `column_white_a` instances stand irregularly off the path at `(528,1445)`, `(516,1436)` and `(534,1457)`, with varied yaw, scales `1`, `0.88`, `0.97` and combined tilts of approximately 9–11°. Exported-mesh footprint rays seat their bases into the soil, burying up to 1.93 m. There is no fallen instance. Single placements accept optional finite `pitch`/`roll` radians, composed locally in YXZ order before terrain-normal alignment. The shared `vrcolumn.py` geometry helper and its material/palette dependencies participate in approval hashes.
